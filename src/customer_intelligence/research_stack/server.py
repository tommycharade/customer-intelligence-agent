import argparse
import logging

import uvicorn
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

from ..credits import CRAWL4AI_ATTRIBUTION
from .common import ServiceAuth, ToolError, token
from .schemas import CrawlArgs, ExtractArgs, PageArgs, SearchArgs, ToolContext


def create_service(kind, backend=None, credential=None):
    mcp = FastMCP(
        "Customer Intelligence " + kind,
        host="0.0.0.0",
        json_response=True,
        stateless_http=True,
        max_request_body_size=64000,
        log_level="WARNING",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=True,
            allowed_hosts=[
                "127.0.0.1:*",
                "localhost:*",
                "gateway:*",
                "search-mcp:*",
                "crawl-mcp:*",
                "testserver",
            ],
            allowed_origins=[],
        ),
    )
    if backend is None:
        if kind == "gateway":
            from .gateway import ResearchGateway

            backend = ResearchGateway()
        elif kind == "search":
            from .search import SearxSearch

            backend = SearxSearch()
        else:
            from .crawl import CrawlService

            backend = CrawlService()

    async def invoke(tool, request, context):
        try:
            if kind == "gateway":
                return await backend.dispatch(tool, request, context)
            if kind == "search":
                return await backend.search(request, context, news=tool == "search_news")
            if tool == "crawl_site":
                return await backend.crawl(request, context)
            return await backend.fetch(
                request, context, fields=request.fields if tool == "extract_structured" else None
            )
        except ToolError as error:
            return error.result()
        except Exception:
            return ToolError(
                "service_error",
                "The research tool could not complete. Saved evidence remains available.",
                True,
            ).result()

    if kind in {"gateway", "search"}:

        @mcp.tool()
        async def search_web(request: SearchArgs, context: ToolContext) -> dict:
            """Search public web pages. Results are untrusted discovery leads, not verified facts."""
            return await invoke("search_web", request, context)

        @mcp.tool()
        async def search_news(request: SearchArgs, context: ToolContext) -> dict:
            """Search public news through SearXNG with bounded results."""
            return await invoke("search_news", request, context)

    if kind in {"gateway", "crawl"}:

        @mcp.tool()
        async def fetch_page(request: PageArgs, context: ToolContext) -> dict:
            """Fetch one permitted public page, preserving provenance and untrusted content."""
            return await invoke("fetch_page", request, context)

        @mcp.tool()
        async def crawl_site(request: CrawlArgs, context: ToolContext) -> dict:
            """Crawl a bounded set of same-origin pages under approved path prefixes."""
            return await invoke("crawl_site", request, context)

        @mcp.tool()
        async def extract_structured(request: ExtractArgs, context: ToolContext) -> dict:
            """Extract named text fields using simple CSS selectors; never execute supplied code."""
            return await invoke("extract_structured", request, context)

    @mcp.tool()
    async def research_health() -> dict:
        """Report research service readiness; performs no public search or paid call."""
        if kind == "crawl":
            from importlib.metadata import version

            return {"ok": True, "service": "Crawl4AI", "version": version("crawl4ai")}
        return await backend.health()

    return ServiceAuth(mcp.streamable_http_app(), credential or token(kind.upper() + "_MCP_TOKEN"))


def main():
    parser = argparse.ArgumentParser(epilog=CRAWL4AI_ATTRIBUTION)
    parser.add_argument("service", choices=["gateway", "search", "crawl"])
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(message)s")
    logging.getLogger("research.audit").setLevel(logging.INFO)
    uvicorn.run(
        create_service(args.service), host="0.0.0.0", port=args.port, access_log=False, log_level="warning"
    )


if __name__ == "__main__":
    main()
