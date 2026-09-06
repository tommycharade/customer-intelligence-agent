# Customer Intelligence Agent

A local account-research workspace. Find up to ten accounts worth your attention, inspect the evidence, and track relevant conversations.

Each proposed account comes with a brief answering **why it fits**, **why now** (or “no timing signal found”), **who matters**, **what could help**, and **what evidence supports it**. Facts, supported inferences and hypotheses are labelled separately. The measure of success is relevant conversations, not database size.

**Status: v0.1, early release.** Developed and smoke-tested on an Apple silicon Mac. Linux CI tests the backend and browser UI with synthetic evidence and mocked models; live SearXNG search and Crawl4AI retrieval have also been checked. Prospect quality has not yet been validated through complete paid-model research runs. This is a single-user local application; public hosting needs a separate authentication and deployment design.

## Quick start

Install [Docker Desktop with Compose](https://docs.docker.com/desktop/), [uv](https://docs.astral.sh/uv/getting-started/installation/), Git and Make. The helper commands use `uv` to install the project's Python dependencies and a compatible Python 3.12–3.13 runtime when needed. Allow at least 4 GB of Docker memory and 15 GB of free disk space for the initial builds. Node.js is only needed for native setup or frontend development.

Clone the repository and start the complete Docker application:

```bash
git clone https://github.com/tommycharade/customer-intelligence-agent.git
cd customer-intelligence-agent
docker compose up -d
make open
```

The first build downloads dependencies and Chromium and can take several minutes. `make open` opens an authenticated browser session on port **8766**. A plain visit to the port does not create a session. If startup is still in progress, check `docker compose ps` and retry `make open` once the services are healthy.

1. Choose **See an example** to explore three clearly labelled synthetic accounts without API keys or charges.
2. Save your offering and customer profile: company type, technology, buyer role, problem, buying trigger and exclusions.
3. Add your OpenRouter API key in **Settings**, use **Check connections**, and check the three model selections. A funded OpenRouter account is needed for live inference; no paid search API key is needed.
4. Choose **Find accounts**. Review the evidence before acting on a recommendation, then record conversation outcomes in the account workspace.

### Native Mac UI

To run the UI/API directly on your Mac while keeping the research services in Docker, also install Node.js 22+ and npm. From the cloned repository:

```bash
./scripts/setup.sh
make up
make connect-native
./scripts/start.sh
```

The native UI uses port **8765**, the Docker UI uses **8766**, and both use the authenticated gateway on **8767**. The two UIs have separate databases and credentials; setup in one does not configure the other. [Operations and troubleshooting](docs/operations.md) explains startup, custom ports, storage and recovery.

Alternatively, double-click **Start Customer Intelligence.command** after setup. The launcher opens an authenticated local browser session at `http://127.0.0.1:8765`. Keep its terminal running; Ctrl+C stops the service. A sleeping Mac pauses work. Restart and choose **Resume** for interrupted runs.

The native app stores its inference key in macOS Keychain; the Docker app uses a private volume. `OPENROUTER_API_KEY` is an optional environment override. Never put keys in a `VITE_` environment variable or Git.

## Data and access

| Tool or service | Job | Required access |
| --- | --- | --- |
| LangGraph | Research workflow and resumable checkpoints | Local application database |
| OpenRouter | Candidate extraction, briefs, independent evidence review and chat | Your API key, funded account and selected source excerpts |
| SearXNG | Self-hosted discovery and news search | Public profile-based queries; outbound access to configured search engines |
| Research MCP gateway | Authenticated search/crawl tools, quotas, cache, provenance and audits | Automatically generated, scoped local service credentials |
| Crawl4AI with guarded HTTPX transport | Read, browse, crawl and extract permitted public content | Docker; outbound HTTP(S) through the public-address policy |
| Playwright Chromium | Render public pages that need JavaScript | An isolated browser; no personal browser profile or saved logins |
| pypdf, python-docx and standard text/email/CSV parsers | Preview enquiries, interview notes and useful assets | Only files you select or text you paste |
| SQLite and FTS5 | Store records, evidence, costs and searchable inputs | Read/write in the application data directory |
| macOS Keychain via keyring | Store service credentials | Your login Keychain |
| FastAPI and React | Local API, progress updates and browser interface | Loopback port 8765 and a launcher-authenticated session |
| Git and GitHub | Versioned application source and automated checks | Repository access for cloning and contributing; no runtime GitHub token |
| uv, Node.js and npm | Install dependencies and build the UI | Package registries during setup; Node is unnecessary while serving the built UI |

Native application data lives in `~/Library/Application Support/Customer Intelligence Agent` (override with `CIA_DATA_DIR`). Docker application data lives in the `customer-intelligence_app-data` volume; the shared gateway has a separate `customer-intelligence_gateway-data` volume for fetched evidence, cache and audits. SQLite stores extracted input text, citations, briefs, run snapshots, chat and outcomes. A separate SQLite file stores LangGraph checkpoints. Files selected for import are parsed locally; the editable extraction is saved only after you choose **Save input**. Original file binaries are not retained.

The app is local, but selected source excerpts and imported notes are sent to OpenRouter for inference. Every task requires zero-data-retention provider routing. Research and review require provider-enforced JSON schemas; extraction can use JSON output with local schema validation. SearXNG forwards discovery queries to its configured engines. Queries use profile fields and account domains, so keep profile text suitable for public search; imported interview and enquiry text is not inserted into search queries. The application does not send email or access your mailbox, CRM, personal browser sessions or shell through the model.

Public retrieval respects crawler directives, blocks private/reserved addresses, validates redirects, pins connections to validated public IPs and bounds response sizes. JavaScript fallback uses isolated Chromium with the same retrieval boundary. Pages requiring authentication or human verification are reported as unavailable. Allow/block domain preferences apply to retrieval and discovery.

## Research and spending

The graph reviews imported notes, discovers candidates, retrieves source pages, checks gaps with bounded follow-up research, drafts briefs, validates citations, performs independent evidence review, and saves qualified accounts. Exclusions win over ranking. Company type, technology and problem/workflow fit each need evidence. Stakeholders and proposed assets retain their uncertainty. A timing signal needs an evidenced recent event date; missing timing is explicitly shown. Weak evidence can produce fewer than ten recommendations, including none.

Defaults: one on-demand run at a time, ten recommendations maximum, 40 candidates, a $5 application model budget, 60 search attempts and 80 page attempts per run, up to three search rounds and five model calls per account. The initial account round includes several queries; a round is not a single query. The shared budget and evidence thresholds may stop a run before it reaches ten accounts. Model calls reserve a conservative maximum using current published pricing and output bounds, then reconcile reported cost. Retries and contextual chat share the run's ledger. Requests with uncertain billing retain their reservation; the UI labels estimates. Self-hosted search uses a query/page quota rather than a paid credit ledger. Historical search charges remain in older exports. No paid requests happen in demo mode or automated tests.

### Models by task

In **Settings → Models by task**, search and select a model and supported reasoning effort independently for each task. Incompatible choices are disabled with an explanation. **Refresh model list** reloads provider compatibility and current prices. **Restore defaults** changes the three selections; choose **Save research settings** to apply them.

| Task | Default model | Reasoning | Total output limit | Request timeout |
| --- | --- | --- | --- | --- |
| Candidate identification and input-note extraction | `z-ai/glm-5.3-flash` | Low | 4,096 tokens | 300 seconds |
| Account assessment, brief drafting, repairs and chat | `z-ai/glm-5.3-flash` | Low | 8,192 tokens | 300 seconds |
| Independent evidence review of briefs and chat | `z-ai/glm-5.3` | High | 16,384 tokens | 600 seconds |

Output limits include reasoning tokens. Every proposed recommendation and chat answer must pass independent review against the original stored sources, in addition to deterministic citation, exclusion and timing checks. A failed result gets one repair and another review; continued failure withholds it. Missing timing is acceptable. These checks reduce unsupported claims but do not replace your review of the evidence.

Each run snapshots the three model IDs and efforts. Saving settings affects future runs; resumes and account chat use the originating run's configuration. Older single-model settings and snapshots resolve that model across all three tasks, retaining provider-default reasoning and the stored historical snapshot.

The app refreshes eligible-provider pricing before each run, resume and live chat, and checks it again at most every five minutes during work. Reservations include reachable context-price tiers, the complete output allowance and reported cache-write/reasoning premiums. Provider maximum-price constraints and ZDR are sent on every inference request; fallback endpoints must fit the same reservation and format requirements. Unavailable or incompatible endpoints pause research with saved progress. Model timeouts and cancellation retain uncertain charges, so a resumed request cannot silently reuse that money.

These are configured defaults, not a guarantee of provider availability. Models need a compatible endpoint on the [OpenRouter ZDR list](https://openrouter.ai/api/v1/endpoints/zdr). Use **Refresh model list** to check availability and current prices; incompatible choices are disabled. Rates, including promotional changes, are read from OpenRouter. See [GLM Flash pricing](https://openrouter.ai/z-ai/glm-5.3-flash) and [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

**Research runs → Models and spending** shows the saved choices, spending by task, each call's actual provider, usage (including reasoning when reported) and evidence-review verdict. All tasks, repairs and chat share the same $5 default model budget. Earlier calls without role metadata remain visible as unattributed spending.

## Inputs and outcomes

Import TXT, Markdown, text-based PDF (100 pages maximum), DOCX, EML and CSV, up to 10 MB per file. Scans and audio need text transcripts. CSV supports `company`, `domain` (or `company_domain`), `title`, `notes` and `exclude`; `exclude=true` creates an explicit account exclusion. Every preview can be edited and associated with a company domain. General interview notes inform research context but do not become evidence about an unrelated account.

The primary metric is unique recommended accounts leading to a user-confirmed relevant conversation, grouped by first-recommendation week. Unreviewed and uncontacted accounts stay visible. Demo records are excluded. Feedback informs subsequent runs; the agent does not rewrite your profile automatically.

Markdown/CSV exports include source references, model configuration, the account review and model-call records for its entire run (including other accounts and chat). JSON export includes application records and usage charges, excluding credentials, raw LangGraph checkpoints and the separate gateway database. Exports may contain private imported notes: review them before sharing.

Source deletion is blocked when live research history could still reference it. **Delete research data** clears that application's research records and checkpoints. It retains the profile, settings and credentials, and does not erase the other UI's database or the shared gateway's public-page cache, evidence and audits. Credential removal is separate. See [storage and deletion](docs/operations.md#storage-and-deletion) for the Docker volumes. The app does not encrypt its databases or the Docker credential file; local disk encryption and backups follow your host's settings.

## Development

```bash
uv sync --locked --extra crawl --python 3.12
uv run --extra crawl playwright install --with-deps chromium
uv run --extra crawl pytest
uv run ruff check .
npm --prefix web ci
npm --prefix web run check
npm --prefix web run build
uv run python scripts/browser_check.py
```

The Python server serves the production Vite build. GitHub Actions uses synthetic fixtures and mocked providers and scans Git history with Gitleaks; research API keys are not required. Dependencies are locked in `uv.lock` and `web/package-lock.json`. Private data, credentials, build artifacts and browser screenshots are excluded from Git.

The local API is documented at `/docs` within an authenticated session. It supports profile/settings, import preview/save/search, research runs and SSE progress, account briefs, contextual chat, outcome recording, demo data, export and deletion. See [CONTRIBUTING.md](CONTRIBUTING.md) for development and [SECURITY.md](SECURITY.md) for reporting a security concern.

## Self-hosted research documentation

- [Architecture and assumptions](docs/architecture.md): gateway/MCP separation, evidence, bounded graph and optional paid-provider interface.
- [Operations](docs/operations.md): startup, `make research DOMAIN=example.com`, caching, recovery, keys and troubleshooting.
- [Research API](docs/api.md): approved tool schemas, typed errors and provenance.
- [Threat model](docs/threat-model.md): controls, tests and residual risks.

Paid-provider escalation is disabled. Exa/Parallel can be added behind the provider protocol later; neither is required in v0.1. No Tavily integration is used. Search engines can rate-limit or fail, and unsupported pages remain unavailable. The app reports these gaps rather than bypassing access restrictions or silently purchasing results.

## Third-party credits

This product includes software developed by UncleCode (https://x.com/unclecode) as part of the Crawl4AI project (https://github.com/unclecode/crawl4ai).

Search is provided by [SearXNG](https://github.com/searxng/searxng), running as a separate service under its own AGPL-3.0-or-later license. Dependencies retain their own licenses, including Crawl4AI's attribution requirement. See [third-party notices](THIRD_PARTY_NOTICES.md) for source and license references.
