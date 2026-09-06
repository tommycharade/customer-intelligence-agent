import os
from pathlib import Path

from ..config import data_directory
from ..models import Settings, Source
from ..routing import ServiceError
from ..sources import SourceUnavailable
from .common import ToolError, mcp_call
from .schemas import ToolContext, WebEvidence


class GatewayClient:
    def __init__(self, store):
        self.store = store
        self.url = os.environ.get("RESEARCH_GATEWAY_URL", "http://127.0.0.1:8767/mcp")

    def credential(self):
        direct = os.environ.get("GATEWAY_MCP_TOKEN")
        path = Path(os.environ.get("GATEWAY_MCP_TOKEN_FILE", data_directory() / "gateway.token"))
        try:
            value = direct or path.read_text().strip()
            if len(value) < 32:
                raise ValueError
            return value
        except (OSError, ValueError) as error:
            raise ServiceError(
                "Start the self-hosted research stack with make up, then run make connect-native for this Mac app."
            ) from error

    async def health(self):
        try:
            return await mcp_call(self.url, self.credential(), "research_health", {}, timeout=15)
        except (ServiceError, ToolError) as error:
            return {"ok": False, "ready": False, "message": str(error), "paid_escalation": "disabled"}

    async def call(self, run_id, tool, request):
        settings = Settings.model_validate(self.store.get("run", run_id)["settings"])
        context = ToolContext(
            graph_run_id=run_id,
            allowed_domains=settings.allowed_domains,
            blocked_domains=settings.blocked_domains,
            max_search_queries=settings.max_search_queries,
            max_pages_fetched=settings.max_pages_fetched,
            browser_fallback=settings.browser_fallback,
        )
        try:
            result = await mcp_call(
                self.url, self.credential(), tool, {"request": request, "context": context.model_dump()}
            )
        except ToolError as error:
            raise ServiceError(error.message) from error
        self.store.put(
            "tool_call",
            context.request_id,
            {
                "id": context.request_id,
                "run_id": run_id,
                "tool": tool,
                "ok": bool(result.get("ok")),
                "cached": bool(result.get("cached")),
                "degraded": bool(result.get("degraded")),
                "error": result.get("error"),
            },
        )
        if not result.get("ok") or result.get("degraded"):
            self.store.patch("run", run_id, degraded=True)
        if not result.get("ok"):
            raise ServiceError(result.get("error", {}).get("message", "Research service unavailable."))
        if result.get("degraded"):
            self.store.event(
                run_id, "Research returned partial results; some sources or search engines were unavailable."
            )
        return result

    async def search(self, run_id, query):
        result = await self.call(run_id, "search_web", {"query": query, "max_results": 6})
        return [{**hit, "content": hit["snippet"]} for hit in result["results"]]

    async def read(self, run_id, url, domain):
        try:
            result = await self.call(run_id, "fetch_page", {"url": url, "account_domain": domain})
            page = WebEvidence.model_validate(result["evidence"])
            self.store.put("web_evidence", page.evidence_id, page)
            return Source(
                title=page.title,
                text=page.content,
                account_domain=domain,
                origin="public",
                source_type="website",
                url=page.source_url,
                published_at=page.published_at,
                retrieved_at=page.retrieved_at,
                content_hash=page.content_hash,
                provenance=page.model_dump(exclude={"content", "links"}),
            )
        except ServiceError as error:
            raise SourceUnavailable(str(error)) from error
