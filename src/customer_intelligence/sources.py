import asyncio
import hashlib
import ipaddress
import json
import re
import socket
from io import BytesIO
from urllib import robotparser
from urllib.parse import urljoin, urlparse, urlunparse

import httpx
import trafilatura
from pypdf import PdfReader

from .models import Source

USER_AGENT = "CustomerIntelligenceAgent/0.1"
MAX_BYTES = 8 * 1024 * 1024


class SourceUnavailable(Exception):
    pass


class PublicReader:
    def __init__(self, settings):
        self.settings = settings
        self.robots = {}

    async def address(self, url):
        parsed = urlparse(url)
        host = parsed.hostname
        if parsed.scheme not in {"http", "https"} or not host or parsed.username or parsed.password:
            raise SourceUnavailable("Only public HTTP(S) pages without credentials are permitted.")
        try:
            port = parsed.port or (443 if parsed.scheme == "https" else 80)
        except ValueError as error:
            raise SourceUnavailable("Invalid source port.") from error
        if port not in {80, 443}:
            raise SourceUnavailable("Source uses a nonstandard port.")
        host = host.lower().rstrip(".")
        if re.fullmatch(r"(?:0[xX][0-9a-fA-F]+|[0-9]+)(?:\.(?:0[xX][0-9a-fA-F]+|[0-9]+)){0,3}", host):
            try:
                ipaddress.ip_address(host)
            except ValueError as error:
                raise SourceUnavailable("Noncanonical numeric IP addresses are blocked.") from error
        if any(host == domain or host.endswith("." + domain) for domain in self.settings.blocked_domains):
            raise SourceUnavailable("This domain is blocked in source preferences.")
        if self.settings.allowed_domains and not any(
            host == domain or host.endswith("." + domain) for domain in self.settings.allowed_domains
        ):
            raise SourceUnavailable("This domain is outside your permitted sources.")
        try:
            addresses = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except OSError as error:
            raise SourceUnavailable("Source hostname could not be resolved.") from error
        ips = list(dict.fromkeys(item[4][0] for item in addresses))
        if not ips or any(not ipaddress.ip_address(ip).is_global for ip in ips):
            raise SourceUnavailable("Local, private and reserved network addresses are blocked.")
        return parsed, host, ips[0]

    async def allowed_by_robots(self, url):
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        if origin not in self.robots:
            try:
                status, _, content, _ = await self.raw(origin + "/robots.txt", robots=False)
                parser = robotparser.RobotFileParser()
                if status in {401, 403} or status >= 429:
                    self.robots[origin] = False
                elif status >= 400:
                    self.robots[origin] = True
                else:
                    parser.parse(content.decode("utf-8", errors="replace").splitlines())
                    self.robots[origin] = parser
            except (SourceUnavailable, httpx.HTTPError):
                self.robots[origin] = False
        policy = self.robots[origin]
        return policy if isinstance(policy, bool) else policy.can_fetch(USER_AGENT, url)

    async def raw(self, url, robots=True):
        async with httpx.AsyncClient(timeout=18, trust_env=False) as client:
            for _ in range(6):
                parsed, host, ip = await self.address(url)
                if robots and not await self.allowed_by_robots(url):
                    raise SourceUnavailable(
                        "This source does not permit this crawler, or its crawler policy is unavailable."
                    )
                # Pin the verified public address to prevent a DNS rebinding between validation and connection.
                ip_host = f"[{ip}]" if ":" in ip else ip
                pinned = urlunparse(parsed._replace(netloc=ip_host, fragment=""))
                async with client.stream(
                    "GET",
                    pinned,
                    headers={"Host": host, "User-Agent": USER_AGENT},
                    extensions={"sni_hostname": host},
                ) as response:
                    if response.is_redirect:
                        url = urljoin(url, response.headers.get("location", ""))
                        continue
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > MAX_BYTES:
                            raise SourceUnavailable("This source exceeds the 8 MB page limit.")
                    return response.status_code, response.headers.get("content-type", ""), bytes(content), url
        raise SourceUnavailable("This source redirects too many times.")

    async def render(self, url):
        from playwright.async_api import async_playwright

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch()
            try:
                context = await browser.new_context(
                    service_workers="block", accept_downloads=False, user_agent=USER_AGENT
                )

                async def route_request(route):
                    request = route.request
                    if request.method != "GET" or request.resource_type in {"image", "media", "font"}:
                        await route.abort()
                        return
                    try:
                        status, content_type, body, _ = await self.raw(request.url)
                        await route.fulfill(status=status, body=body, headers={"content-type": content_type})
                    except Exception:
                        await route.abort()

                await context.route("**/*", route_request)
                await context.route_web_socket("**/*", lambda ws: ws.close())
                page = await context.new_page()
                await page.goto(url, wait_until="domcontentloaded", timeout=25000)
                await page.wait_for_timeout(1200)
                return await page.content()
            finally:
                await browser.close()

    async def read(self, url, domain):
        try:
            status, content_type, body, final_url = await self.raw(url)
            if status >= 400:
                raise SourceUnavailable(f"Source returned HTTP {status}.")
            if "application/pdf" in content_type:
                reader = PdfReader(BytesIO(body))
                if reader.is_encrypted:
                    raise SourceUnavailable("Password-protected PDFs cannot be read.")
                text = "\n".join(page.extract_text() or "" for page in reader.pages[:60])
                title, published = urlparse(final_url).path.split("/")[-1], None
            else:
                html = body.decode("utf-8", errors="replace")
                extracted = self.extract(html)
                if len(extracted.get("text", "")) < 150 and self.settings.browser_fallback:
                    html = await self.render(final_url)
                    extracted = self.extract(html)
                text, title, published = (
                    extracted.get("text", ""),
                    extracted.get("title") or urlparse(final_url).hostname,
                    extracted.get("date"),
                )
            if len(text.strip()) < 100:
                raise SourceUnavailable(
                    "This page has insufficient readable text. Upload a permitted copy if available."
                )
            if any(
                phrase in text[:500].lower()
                for phrase in (
                    "verify you are human",
                    "checking your browser",
                    "enable javascript and cookies",
                )
            ):
                raise SourceUnavailable("This page requires a human verification step.")
            return Source(
                title=title,
                text=text[:60000],
                origin="public",
                url=final_url,
                source_type="website",
                account_domain=domain,
                published_at=published,
                content_hash=hashlib.sha256(text.encode()).hexdigest(),
            )
        except SourceUnavailable:
            raise
        except Exception as error:
            raise SourceUnavailable(
                "The page could not be read. It may be unavailable or require an interactive session."
            ) from error

    @staticmethod
    def extract(html):
        output = trafilatura.extract(html, output_format="json", with_metadata=True, include_comments=False)
        return json.loads(output) if output else {}
