# Customer Intelligence Agent

A local account-research workspace. Find up to ten accounts worth your attention, inspect the evidence, and track relevant conversations.

## Start on your Mac

Prerequisites: Python 3.12–3.13 via [uv](https://docs.astral.sh/uv/), Node.js 22+ and npm. Git is required for development.

```bash
./scripts/setup.sh
./scripts/start.sh
```

Alternatively, double-click **Start Customer Intelligence.command** after setup. The launcher opens an authenticated local browser session at `http://127.0.0.1:8765`. Keep its terminal running; Ctrl+C stops the service. A sleeping Mac pauses work. Restart and choose **Resume** for interrupted runs.

First, use **Explore a demo** to try the workspace without API keys or charges. The three synthetic companies are labelled throughout and excluded from live outcome metrics. Then enter your offering, six customer-profile fields, OpenRouter key and Tavily key. Keys are stored in macOS Keychain; environment overrides `OPENROUTER_API_KEY` and `TAVILY_API_KEY` are also supported. Never put keys in a `VITE_` environment variable or Git.

## Data and access

| Tool or service | Job | Required access |
| --- | --- | --- |
| LangGraph | Research workflow and resumable checkpoints | Local application database |
| OpenRouter | Candidate extraction, briefs, independent evidence review and chat | Your API key, funded account and selected source excerpts |
| Tavily | Public company discovery and source search | Your API key and public profile-based queries |
| HTTPX and Trafilatura | Read and extract public websites, documentation, jobs and discussions | Outbound HTTPS to permitted public sources |
| Playwright Chromium | Render public pages that need JavaScript | An isolated browser; no personal browser profile or saved logins |
| pypdf, python-docx and standard text/email/CSV parsers | Preview enquiries, interview notes and useful assets | Only files you select or text you paste |
| SQLite and FTS5 | Store records, evidence, costs and searchable inputs | Read/write in the application data directory |
| macOS Keychain via keyring | Store service credentials | Your login Keychain |
| FastAPI and React | Local API, progress updates and browser interface | Loopback port 8765 and a launcher-authenticated session |
| Git and GitHub | Versioned application source and automated checks | Developer access to the private repository; no runtime GitHub token |
| uv, Node.js and npm | Install dependencies and build the UI | Package registries during setup; Node is unnecessary while serving the built UI |

Private data lives in `~/Library/Application Support/Customer Intelligence Agent` (override with `CIA_DATA_DIR`). SQLite stores extracted input text, citations, briefs, run snapshots, chat and outcomes. A separate SQLite file stores LangGraph checkpoints. Files selected for import are parsed locally; the editable extraction is saved only after you choose **Save inputs**. Original file binaries are not retained.

The app is local, but selected excerpts are sent to OpenRouter for inference. Every task requires zero-data-retention provider routing. Research and review require provider-enforced JSON schemas; extraction can use JSON output with local schema validation. Tavily receives public discovery queries; confidential input text is never used to construct search queries. The application does not send email or access your mailbox, CRM, personal browser sessions or shell through the model.

Public retrieval respects crawler directives, blocks private/reserved addresses, validates redirects, pins connections to validated public IPs and bounds response sizes. JavaScript fallback uses isolated Chromium with the same retrieval boundary. Pages requiring authentication or human verification are reported as unavailable. Allow/block domain preferences apply to retrieval and discovery.

## Research and spending

The graph reviews imported notes, discovers candidates, retrieves source pages, assesses fit, checks exact citations, performs a separate semantic verification, and saves qualified accounts. Exclusions win over ranking. All three fit criteria need evidence. Stakeholders and proposed assets retain their uncertainty. A timing signal needs an evidenced recent event date; missing timing is explicitly shown.

Defaults: one on-demand run at a time, ten recommendations maximum, 40 candidates, $5 OpenRouter cap and 100 Tavily search credits. Model calls reserve a conservative maximum using current published pricing and output bounds, then reconcile reported cost. Retries and contextual chat share the run's ledger. Requests with uncertain billing retain their reservation; the UI labels estimates. Search has a separate credit ledger. No paid requests happen in demo mode or automated tests.

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

Rates are read from OpenRouter, including promotional changes, rather than hardcoded. Qwen 3.7 Flash remains unavailable while it has no compatible endpoint on the [OpenRouter ZDR list](https://openrouter.ai/api/v1/endpoints/zdr). See [GLM Flash pricing](https://openrouter.ai/z-ai/glm-5.3-flash) and [provider routing](https://openrouter.ai/docs/guides/routing/provider-selection).

**Research runs → Models and spending** shows the saved choices, spending by task, each call's actual provider, usage (including reasoning when reported) and evidence-review verdict. All tasks, repairs and chat share the same $5 default model budget. Earlier calls without role metadata remain visible as unattributed spending.

## Inputs and outcomes

Import TXT, Markdown, text-based PDF (100 pages maximum), DOCX, EML and CSV, up to 10 MB per file. Scans and audio need text transcripts. CSV supports `company`, `domain` (or `company_domain`), `title`, `notes` and `exclude`; `exclude=true` creates an explicit account exclusion. Every preview can be edited and associated with a company domain. General interview notes inform research context but do not become evidence about an unrelated account.

The primary metric is unique recommended accounts leading to a user-confirmed relevant conversation, grouped by first-recommendation week. Unreviewed and uncontacted accounts stay visible. Demo records are excluded. Feedback informs subsequent runs; the agent does not rewrite your profile automatically.

Markdown/CSV exports include source references, model configuration, the account review and model-call records for its entire run (including other accounts and chat). JSON export includes all application records and usage charges, excluding credentials and raw LangGraph checkpoints. Source deletion is blocked when live research history could still reference it; **Delete research data** clears records and checkpoints together. Keychain credentials have separate removal controls. Local disk encryption and backups follow your Mac's settings; the app does not claim application-level database encryption.

## Development

```bash
uv sync --locked
uv run pytest
uv run ruff check .
npm --prefix web ci
npm --prefix web run check
npm --prefix web run build
uv run python scripts/browser_check.py
```

The Python server serves the production Vite build. GitHub Actions uses synthetic fixtures and mocked providers; research API keys are not required. Dependencies are locked in `uv.lock` and `web/package-lock.json`. Private data, credentials, build artifacts and browser screenshots are excluded from Git.

The local API is documented at `/docs` within an authenticated session. It supports profile/settings, import preview/save/search, research runs and SSE progress, account briefs, contextual chat, outcome recording, demo data, export and deletion. This is a single-user, loopback-only application; deployment to a LAN or public host requires a separate authentication and deployment design.
