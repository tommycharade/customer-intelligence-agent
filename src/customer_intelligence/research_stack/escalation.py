"""Optional research providers never sit on the default search path."""

from typing import Protocol

from .common import ToolError


class ResearchProvider(Protocol):
    async def search(self, query: str, max_results: int = 10) -> dict: ...
    async def research(self, company: str, gaps: list[str]) -> dict: ...


class NullPaidResearchProvider:
    async def search(self, query, max_results=10):
        raise ToolError(
            "paid_research_disabled",
            "Paid research is disabled. Use self-hosted discovery or supply more evidence.",
        )

    async def research(self, company, gaps):
        return {"enabled": False, "status": "disabled", "remaining_gaps": gaps}
