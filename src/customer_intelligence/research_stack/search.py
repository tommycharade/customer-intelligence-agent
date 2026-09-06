import asyncio
import os

import httpx

from .common import ToolError
from .schemas import SearchHit, normalize_url


class SearxSearch:
    async def search(self, args, context, news=False):
        endpoint = os.environ.get("SEARXNG_URL", "http://searxng:8080").rstrip("/")
        for attempt in range(2):
            try:
                async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
                    response = await client.get(
                        endpoint + "/search",
                        params={
                            "q": args.query,
                            "format": "json",
                            "categories": "news" if news else "general",
                            "language": args.language,
                            "time_range": args.time_range or "",
                            "safesearch": 1,
                        },
                        headers={"X-Request-ID": context.request_id},
                    )
                    response.raise_for_status()
                    data = response.json()
                results, seen = [], set()
                for item in data.get("results", [])[:100]:
                    try:
                        url = normalize_url(item["url"])
                    except (ValueError, KeyError):
                        continue
                    if url in seen:
                        continue
                    seen.add(url)
                    results.append(
                        SearchHit(
                            title=item.get("title", "")[:1000],
                            url=url,
                            snippet=item.get("content", "")[:4000],
                            source="SearXNG: " + str(item.get("engine", "unknown"))[:170],
                            rank=len(results) + 1,
                            search_query=args.query,
                            request_id=context.request_id,
                        ).model_dump()
                    )
                    if len(results) >= args.max_results:
                        break
                unavailable = bool(data.get("unresponsive_engines"))
                if not results and unavailable:
                    raise ToolError(
                        "search_degraded",
                        "SearXNG's upstream engines returned no usable results. Retry later or supply company URLs.",
                        True,
                    )
                return {
                    "ok": True,
                    "results": results,
                    "degraded": unavailable,
                    "warnings": ["Some search engines were unavailable."] if unavailable else [],
                }
            except (httpx.HTTPError, ValueError, TypeError) as error:
                if attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                raise ToolError(
                    "search_unavailable",
                    "SearXNG is unavailable. Check Docker service health and retry.",
                    True,
                ) from error

    async def health(self):
        try:
            async with httpx.AsyncClient(timeout=5, trust_env=False) as client:
                response = await client.get(os.environ.get("SEARXNG_URL", "http://searxng:8080") + "/healthz")
                response.raise_for_status()
            return {"ok": True, "service": "SearXNG"}
        except httpx.HTTPError:
            return {"ok": False, "service": "SearXNG", "status": "unavailable"}
