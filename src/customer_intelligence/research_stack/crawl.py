import asyncio
import hashlib
import json
from collections import deque
from urllib.parse import urljoin, urlparse

from ..models import Settings
from ..sources import MAX_BYTES, USER_AGENT, PublicReader, SourceUnavailable
from .common import ToolError
from .schemas import PageArgs, WebEvidence, normalize_url


def source_policy(context):
    return Settings(
        allowed_domains=context.allowed_domains,
        blocked_domains=context.blocked_domains,
        browser_fallback=context.browser_fallback,
    )


class CrawlService:
    def __init__(self):
        self.semaphore = asyncio.Semaphore(2)

    async def fetch(self, args, context, fields=None):
        from crawl4ai import AsyncWebCrawler, BrowserConfig, CacheMode, CrawlerRunConfig
        from crawl4ai.extraction_strategy import JsonCssExtractionStrategy

        reader = PublicReader(source_policy(context))
        final_url = args.url
        count, transferred = 0, 0
        failure = None
        try:
            await reader.address(args.url)
            # Requests are fulfilled through the pinned HTTP transport. Any Chromium
            # traffic that bypasses interception hits a closed proxy, not the network.
            browser_config = BrowserConfig(
                headless=True,
                verbose=False,
                accept_downloads=False,
                java_script_enabled=context.browser_fallback,
                user_agent=USER_AGENT,
                proxy_config={"server": "http://127.0.0.1:9"},
                extra_args=[
                    "--disable-quic",
                    "--disable-background-networking",
                    "--proxy-bypass-list=<-loopback>",
                ],
            )
            async with self.semaphore, asyncio.timeout(50):
                async with AsyncWebCrawler(config=browser_config) as crawler:

                    async def guard(page, context, **kwargs):
                        async def request(route):
                            nonlocal final_url, count, transferred, failure
                            req = route.request
                            count += 1
                            if (
                                count > 60
                                or req.method != "GET"
                                or req.resource_type
                                not in {"document", "script", "stylesheet", "xhr", "fetch"}
                            ):
                                await route.abort()
                                return
                            try:
                                status, content_type, body, resolved = await reader.raw(req.url)
                                transferred += len(body)
                                if transferred > 16 * 1024 * 1024:
                                    raise SourceUnavailable("Page resource bytes exceeded their limit.")
                                if req.is_navigation_request() and req.frame == page.main_frame:
                                    final_url = resolved
                                # Cookies, auth, redirect headers and all response policy headers
                                # are deliberately not forwarded to this throwaway browser.
                                await route.fulfill(
                                    status=status, body=body, headers={"content-type": content_type}
                                )
                            except Exception:
                                if req.is_navigation_request() and req.frame == page.main_frame:
                                    failure = (
                                        "The page was blocked by source policy or could not be retrieved."
                                    )
                                await route.abort()

                        await context.route("**/*", request)
                        await context.route_web_socket("**/*", lambda socket: socket.close())
                        return page

                    crawler.crawler_strategy.set_hook("on_page_context_created", guard)
                    extraction = None
                    if fields:
                        extraction = JsonCssExtractionStrategy(
                            {
                                "name": "Approved text extraction",
                                "baseSelector": "body",
                                "fields": [
                                    {"name": name, "selector": selector, "type": "text"}
                                    for name, selector in fields.items()
                                ],
                            }
                        )
                    result = await crawler.arun(
                        url=args.url,
                        config=CrawlerRunConfig(
                            cache_mode=CacheMode.DISABLED,
                            page_timeout=35000,
                            wait_until="domcontentloaded",
                            delay_before_return_html=0.5,
                            word_count_threshold=1,
                            extraction_strategy=extraction,
                            verbose=False,
                            capture_network_requests=False,
                            capture_console_messages=False,
                            process_iframes=False,
                            remove_forms=True,
                        ),
                    )
                    if not result.success or failure:
                        raise SourceUnavailable(failure or "Crawl4AI could not retrieve this page.")
                    if len(result.html.encode()) > MAX_BYTES:
                        raise SourceUnavailable("Rendered content exceeded the page limit.")
                    content = result.markdown.raw_markdown if result.markdown else ""
                    if len(content.strip()) < 100:
                        raise SourceUnavailable("This page has insufficient readable evidence.")
                    if any(
                        phrase in content[:500].lower()
                        for phrase in (
                            "verify you are human",
                            "checking your browser",
                            "enable javascript and cookies",
                        )
                    ):
                        raise SourceUnavailable("This page requires human verification.")
                    content = content[:60000]
                    links = []
                    for group in (result.links or {}).values():
                        for link in group:
                            try:
                                value = normalize_url(urljoin(final_url, link["href"]))
                                if value not in links:
                                    links.append(value)
                            except (KeyError, TypeError, ValueError):
                                continue
                    domain = urlparse(final_url).hostname
                    metadata = result.metadata or {}
                    evidence = WebEvidence(
                        account_domain=args.account_domain,
                        source_url=final_url,
                        source_domain=domain,
                        title=str(metadata.get("title") or domain)[:1000],
                        content=content,
                        content_hash=hashlib.sha256(content.encode()).hexdigest(),
                        request_id=context.request_id,
                        trust_level="first_party"
                        if args.account_domain
                        and (domain == args.account_domain or domain.endswith("." + args.account_domain))
                        else "unknown",
                        links=links[:100],
                    )
                    output = {"ok": True, "evidence": evidence.model_dump(), "network_requests": count}
                    if fields:
                        extracted = json.loads(result.extracted_content or "[]")
                        output["extracted"] = [
                            {key: str(row.get(key, ""))[:4000] for key in fields} for row in extracted[:20]
                        ]
                    return output
        except (SourceUnavailable, TimeoutError) as error:
            raise ToolError(
                "page_unavailable", str(error) or "The page exceeded its execution time limit."
            ) from error

    async def crawl(self, args, context):
        root = urlparse(args.url)
        queue, seen, evidence, errors = deque([(args.url, 0)]), set(), [], []
        try:
            async with asyncio.timeout(120):
                while queue and len(seen) < args.max_pages:
                    url, depth = queue.popleft()
                    if url in seen:
                        continue
                    seen.add(url)
                    try:
                        page = await self.fetch(
                            PageArgs(url=url, account_domain=args.account_domain), context
                        )
                        record = page["evidence"]
                        evidence.append(record)
                        if depth < args.max_depth:
                            for link in record["links"]:
                                parsed = urlparse(link)
                                if parsed.netloc == root.netloc and any(
                                    parsed.path == path or parsed.path.startswith(path.rstrip("/") + "/")
                                    for path in args.allowed_paths
                                ):
                                    queue.append((link, depth + 1))
                    except ToolError as error:
                        errors.append({"url": url, **error.result()["error"]})
        except TimeoutError:
            errors.append(
                {"code": "crawl_timeout", "message": "Crawl time limit reached; partial evidence retained."}
            )
        return {
            "ok": True,
            "evidence": evidence,
            "errors": errors,
            "pages_attempted": len(seen),
            "degraded": bool(errors),
        }
