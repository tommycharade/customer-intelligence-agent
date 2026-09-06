import asyncio
import hashlib
import os
import time
from urllib.parse import urlparse

from pydantic import ValidationError

from ..sources import PublicReader, SourceUnavailable
from .common import Ledger, ToolError, cache_key, mcp_call, token
from .crawl import source_policy
from .schemas import SearchHit, WebEvidence


class ResearchGateway:
    def __init__(self, ledger=None, call=mcp_call):
        self.ledger = ledger or Ledger(os.environ.get("RESEARCH_DATA_DIR", "/data"))
        self.call = call
        self.semaphore = asyncio.Semaphore(4)
        self.failures = {}

    async def upstream(self, service, tool, arguments):
        failures, until = self.failures.get(service, (0, 0))
        if until > time.monotonic():
            raise ToolError(
                "circuit_open", f"{service.title()} is temporarily unavailable; retry in 30 seconds.", True
            )
        url = os.environ.get(service.upper() + "_MCP_URL", f"http://{service}-mcp:8000/mcp")
        try:
            result = await self.call(url, token(service.upper() + "_MCP_TOKEN"), tool, arguments)
            if not result.get("ok"):
                error = result.get("error", {})
                raise ToolError(
                    error.get("code", "upstream_error"),
                    error.get("message", "Research tool failed."),
                    error.get("retryable", False),
                )
            self.failures[service] = (0, 0)
            return result
        except ToolError as error:
            if error.retryable:
                failures += 1
                self.failures[service] = (failures, time.monotonic() + 30 if failures >= 3 else 0)
            raise

    async def dispatch(self, tool, args, context):
        started = time.monotonic()
        decision, count, cached = "denied", 0, False
        summary = (
            {"query_sha256": hashlib.sha256(args.query.encode()).hexdigest()}
            if hasattr(args, "query")
            else {"domain": urlparse(args.url).hostname}
        )
        try:
            service = "search" if tool.startswith("search_") else "crawl"
            self.ledger.count("search_requests_total" if service == "search" else "crawl_requests_total")
            reader = PublicReader(source_policy(context))
            if hasattr(args, "url"):
                await reader.address(args.url)
            amount = getattr(args, "max_pages", 1)
            resource = "search_queries" if service == "search" else "pages_fetched"
            self.ledger.consume(context.graph_run_id, resource, amount, getattr(context, "max_" + resource))
            key = cache_key(tool, args.model_dump(), context.model_dump())
            result = self.ledger.get(key)
            if result is None:
                async with self.semaphore:
                    result = await self.upstream(
                        service, tool, {"request": args.model_dump(), "context": context.model_dump()}
                    )
                # Validate independently of the backing service. No upstream-supplied
                # credentials, instructions or arbitrary metadata enter the evidence store.
                if service == "search":
                    accepted = []
                    for raw in result.get("results", [])[: args.max_results]:
                        hit = SearchHit.model_validate(raw)
                        try:
                            await reader.address(hit.url)
                        except SourceUnavailable:
                            continue
                        accepted.append(hit.model_dump())
                    result = {
                        "ok": True,
                        "results": accepted,
                        "degraded": bool(result.get("degraded")),
                        "warnings": result.get("warnings", [])[:5],
                    }
                else:
                    extracted = result.get("extracted", [])
                    records = result.get("evidence", [])
                    if isinstance(records, dict):
                        records = [records]
                    validated = []
                    for raw in records[:amount]:
                        record = WebEvidence.model_validate(raw)
                        await reader.address(record.source_url)
                        if hashlib.sha256(record.content.encode()).hexdigest() != record.content_hash:
                            raise ToolError("provenance_invalid", "Content did not match its evidence hash.")
                        record.source_domain = urlparse(record.source_url).hostname
                        record.account_domain = args.account_domain
                        record.trust_level = (
                            "first_party"
                            if args.account_domain
                            and (
                                record.source_domain == args.account_domain
                                or record.source_domain.endswith("." + args.account_domain)
                            )
                            else "unknown"
                        )
                        validated.append(record.model_dump())
                        self.ledger.evidence(record.model_dump())
                    self.ledger.count("pages_fetched_total", len(validated))
                    result = {
                        "ok": True,
                        "evidence": validated if tool == "crawl_site" else validated[0],
                        "degraded": bool(result.get("degraded")),
                        "errors": result.get("errors", [])[:20],
                    }
                    if tool == "extract_structured":
                        result["extracted"] = [
                            {key: str(row.get(key, ""))[:4000] for key in args.fields}
                            for row in extracted[:20]
                        ]
                ttl = int(
                    os.environ.get(
                        "SEARCH_CACHE_TTL" if service == "search" else "PAGE_CACHE_TTL",
                        "900" if service == "search" else "21600",
                    )
                )
                if not result.get("degraded"):
                    self.ledger.put(key, result, max(0, min(ttl, 86400)))
            else:
                cached = True
            count = (
                len(result["results"])
                if service == "search"
                else len(result["evidence"])
                if isinstance(result["evidence"], list)
                else 1
            )
            decision = "allowed"
            return result | {"request_id": context.request_id, "cached": cached, "untrusted": True}
        except SourceUnavailable as error:
            self.ledger.count("crawl_blocked_total")
            return ToolError("policy_denied", str(error)).result()
        except (ValidationError, ValueError, KeyError, IndexError, TypeError):
            return ToolError("invalid_response", "The research service returned invalid evidence.").result()
        except ToolError as error:
            return error.result()
        finally:
            self.ledger.audit(
                request_id=context.request_id,
                graph_run_id=context.graph_run_id,
                tool=tool,
                arguments_summary=summary,
                decision=decision,
                duration_ms=round((time.monotonic() - started) * 1000),
                result_count=count,
                cached=cached,
            )

    async def health(self):
        status = {}
        for service in ("search", "crawl"):
            try:
                status[service] = await self.upstream(service, "research_health", {})
            except ToolError as error:
                status[service] = error.result()
        return {
            "ok": True,
            "services": status,
            "ready": all(item.get("ok") for item in status.values()),
            "paid_escalation": "disabled",
            "metrics": self.ledger.metrics,
        }
