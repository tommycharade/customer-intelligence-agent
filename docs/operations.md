# Running the research stack

Requirements: Docker Desktop with Compose, at least 4 GB available Docker memory, and outbound access to image/package registries and public search engines. The native application additionally needs Python/uv; rebuilding its UI needs Node 22+. Initial image/browser downloads take several minutes.

From a fresh clone:

```bash
docker compose up -d
make open
```

Compose builds the application and MCP services and starts SearXNG, Crawl4AI, the gateway and the Docker UI. The one-shot init service generates independent gateway/search/crawl credentials into private volumes; it does not print them. All long-running services have health checks. There is no paid search account to create.

The Docker UI is at port 8766; `make open` opens an authenticated session. Enter your customer profile and OpenRouter key in Settings. Alternatively copy `.env.example` to `.env` and configure `OPENROUTER_API_KEY` before starting. Do not commit `.env`. The UI may save a key into the private Docker application volume; it is not encrypted by the app. Disk encryption and Docker/Desktop access controls remain your responsibility.

To keep using the existing native Mac UI and data:

```bash
make up
make connect-native
./scripts/start.sh
```

`make connect-native` copies only the gateway's scoped token to the existing private application data directory with mode 0600. It does not copy source data or API keys. Native inference keys stay in Keychain. The browser-based Settings connection check tests MCP readiness without running paid research.

For a specific company, first set the customer profile and OpenRouter credentials in the Docker UI, then:

```bash
make research DOMAIN=example.com
```

This starts a real, budgeted run, prints progress and outputs verified Markdown briefs. It does not send outreach. `python scripts/research_stack.py research --domain example.com --company-name 'Example Ltd'` also accepts a display name. Use the Research runs UI to cancel, resume or adjust limits. The CLI operates on the Docker application's separate database.

## Commands and configuration

- `make up`: build changed code and start the stack.
- `make down`: stop containers, retaining volumes and evidence.
- `make test`: run backend tests (including the real Crawl4AI fixture test) and frontend checks.
- `make lint` / `make format`: check or format Python.
- `docker compose ps`: inspect health.
- `docker compose logs --tail=100 gateway`: inspect redacted tool audits.
- `SEARCH_CACHE_TTL` / `PAGE_CACHE_TTL`: seconds; zero disables useful caching, maximum 86,400.
- `CIA_DOCKER_PORT` / `RESEARCH_GATEWAY_PORT`: published loopback ports; defaults 8766/8767.
- Native `RESEARCH_GATEWAY_URL` and `GATEWAY_MCP_TOKEN_FILE` override the gateway address/token location.

Compose publishes only the gateway and application on 127.0.0.1. Search, crawler and SearXNG ports remain on the Docker network. Gateway-to-service tokens are separate from the application-to-gateway token. Static credentials are scoped by service exposure, not by tenant; this stack is single-user. To rotate a token, stop the stack, replace only its private token-volume file with a cryptographically random value of at least 32 characters, preserve its owner/mode, restart and repeat `make connect-native` if the gateway token changed. Back up the application and gateway volumes together using your normal local backup process. Do not run `docker compose down -v` unless deliberately deleting all Docker research data and keys.

SearXNG is pinned by image digest, Crawl4AI/MCP by `uv.lock`. Update these deliberately, then rerun the fixture and browser checks. The SearXNG settings template is applied only when its configuration volume is created; updating an existing engine configuration requires replacing that volume's settings file while preserving its generated secret. General discovery enables DuckDuckGo, Bing and Brave; news uses Google News. Search availability depends on the upstream engines and their public access rules.

## Degraded operation and recovery

An unavailable engine may produce partial results. If every engine fails, search returns an explicit degraded error. Check service health and retry later; the app does not silently buy search results. You can also supply known company URLs or import evidence. A crawler outage or blocked page preserves already fetched sources and records an incomplete step. A site requiring authentication or human verification is not bypassed.

Per-run query/page limits count reserved attempts conservatively, including failures. Crawl-site calls reserve their requested maximum before executing. Resumes reuse the application's saved search/fetch results; they do not reset quotas. Cache expiry is separate from durable evidence retention. The gateway records request IDs and argument hashes/domain summaries, not query contents, tokens or page bodies, in logs. Evidence and cache databases necessarily contain researched content and query provenance.

The gateway exposes process metrics through authenticated `research_health`; the application exposes model/run totals at authenticated `/api/observability`. Gateway audits/counters are durable, while its aggregate cache/request metrics reset on restart. These are operational metrics, separate from the product's relevant-conversation conversion measure.

## Validation and v0.2

CI uses deterministic search/browser fixtures with mocked OpenRouter responses. It exercises the actual MCP transport and Crawl4AI browser, so no model credits or live search are needed. Install Chromium with `uv run playwright install --with-deps chromium` before local browser tests. A separate installation smoke check can verify live public search and retrieval without model calls.

v0.2 candidates: independently authorised security assessment; stronger OS/network isolation and credential rotation automation; PDF/media ingestion through the gateway; paid adapters with explicit spending consent; selective audit retention/backup UI; signed provenance across separately trusted hosts. No CRM writes, cold email, LinkedIn automation or agent swarm is planned in this release.
