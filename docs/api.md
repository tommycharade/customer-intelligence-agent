# Research tool interface

All research endpoints use the official MCP Streamable HTTP protocol at `/mcp`. Clients must provide `Authorization: Bearer <scoped-service-token>`. Secrets come from the private service volume or the native gateway token file; do not put them in browser JavaScript. Ordinary browser Origin requests are rejected. `/health` returns only process liveness without authentication.

The LangGraph application connects only to the gateway. Request examples are MCP `tools/call` arguments; use an MCP SDK to initialise sessions and perform protocol requests.

```json
{
  "name": "search_web",
  "arguments": {
    "request": {"query": "public company criteria", "max_results": 10, "language": "en", "time_range": null},
    "context": {"graph_run_id": "run-identifier", "request_id": "request-identifier", "allowed_domains": [], "blocked_domains": [], "max_search_queries": 60, "max_pages_fetched": 80, "browser_fallback": true}
  }
}
```

| Tool | Request fields | Return |
| --- | --- | --- |
| `search_web` | query, max_results 1–20, language, time_range null/day/week/month/year | URL, title, snippet, engine, retrieval date, rank and query provenance |
| `search_news` | Same | News discovery leads |
| `fetch_page` | public HTTP(S) url, optional account_domain | One untrusted WebEvidence object |
| `crawl_site` | url, account_domain, max_pages 1–20, max_depth 0–3, allowed_paths | Bounded same-origin evidence list and per-page errors |
| `extract_structured` | url, account_domain, fields mapping names to simple CSS selectors | Evidence plus extracted text fields; no LLM charges |
| `research_health` | No arguments | Dependency readiness, paid-provider state and gateway metrics |

Every result has `ok`. Failures carry `error.code`, `error.message` and `error.retryable`. Gateway responses also attach the current request ID, `cached` and `untrusted`. Cached evidence preserves its actual retrieval timestamp. Typical error codes include `policy_denied`, `resource_limit`, `page_unavailable`, `search_degraded`, `service_unavailable`, `circuit_open` and `provenance_invalid`. There is no configurable arbitrary proxy, browser script, executable extraction expression, filesystem path or infrastructure operation.

The existing application API remains available in the authenticated local `/docs`. New endpoints include `/api/research/health`, `/api/runs/{id}/research-tools` and `/api/observability`. `/api/runs` accepts optional `target_domain` and `company_name` to research a particular company under the saved customer profile. Run settings snapshot the model roles and research limits.

`Source.provenance` links saved excerpts to WebEvidence metadata. `Finding` records link interpretations back to evidence/source IDs and preserve three classifications. Application JSON exports include sources, WebEvidence, findings, model calls, tool calls and run snapshots. Markdown/CSV account exports preserve citations and model-use records. The gateway's separate private audit/cache database is operated through Docker volumes rather than exported through the public-source tools.
