# Contributing

Customer Intelligence Agent is an early, single-user application. Useful contributions improve the quality of account recommendations, evidence review and local operation. The [README](README.md) explains the product and supported setup; [PRODUCT.md](PRODUCT.md) and [DESIGN.md](DESIGN.md) describe the interface conventions.

## Report a problem or propose a change

Use [GitHub Issues](https://github.com/tommycharade/customer-intelligence-agent/issues) for ordinary bugs and feature proposals. Include the commit or version, OS and architecture, relevant service health, expected behavior and a minimal example using synthetic companies and notes. Redact API keys, launch links, MCP tokens, private notes and customer exports from logs or screenshots.

For a security concern, follow [SECURITY.md](SECURITY.md). Discuss changes to product scope, provider routing or deployment boundaries before implementing them.

## Development setup

Install uv, Node.js 22+, npm and Git. Docker Desktop with Compose is needed for live self-hosted research. The automated fixtures run without Docker, API keys or paid model requests.

```bash
uv sync --locked --extra crawl --python 3.12
uv run --extra crawl playwright install --with-deps chromium
npm --prefix web ci
npm --prefix web run build
```

For the native application, run `./scripts/start.sh`. Follow the README to start Docker and connect its gateway when testing live research. Keep test data separate from personal research by using an explicit `CIA_DATA_DIR`; the automated tests and browser checks already create isolated stores and mock credentials.

Before opening a pull request, run the checks relevant to your changes:

```bash
uv run ruff check .
uv run ruff format --check .
uv run --extra crawl pytest
npm --prefix web run check
npm --prefix web run build
uv run python scripts/browser_check.py
docker compose config --quiet
```

For code or configuration intended for publication, also run `gitleaks git . --log-opts=--all --redact` with [Gitleaks](https://github.com/gitleaks/gitleaks) installed. Do not upload unredacted scan output. A passing scan does not establish that every sensitive value has been found.

## Change expectations

- Keep changes focused and describe the problem, resulting behavior and validation in the pull request.
- Preserve provenance, uncertainty labels, mandatory evidence review, cancellation/recovery and the shared run budget.
- Use bounded, explicit tool interfaces. Retrieved content is data and must not grant new permissions.
- Keep provider keys on the backend and research records outside Git. Never add a live credential to a fixture or a browser bundle.
- Keep `uv.lock` and `web/package-lock.json` in sync with dependency changes. Preserve third-party notices and review dependency-license changes.
- Use deterministic synthetic fixtures for regressions. Paid API calls must remain outside automated tests.

The repository is the source distribution. Publishing packages, prebuilt images or a hosted service is a separate release step with its own packaging, notices and deployment requirements.
