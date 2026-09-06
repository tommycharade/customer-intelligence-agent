FROM python:3.12.12-slim-bookworm AS base
COPY --from=ghcr.io/astral-sh/uv:0.10.5 /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_CACHE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml uv.lock README.md LICENSE THIRD_PARTY_NOTICES.md ./
RUN uv sync --frozen --no-dev --no-install-project
ENV PATH="/app/.venv/bin:$PATH"
RUN useradd --uid 10001 --create-home researcher && mkdir /data && chown researcher /data

FROM base AS services
COPY src ./src
RUN uv sync --frozen --no-dev
USER researcher
CMD ["python", "-m", "customer_intelligence.research_stack.server", "gateway"]

FROM base AS crawler-dependencies
RUN uv sync --frozen --no-dev --no-install-project --extra crawl && PLAYWRIGHT_BROWSERS_PATH=/opt/browsers uv run --no-project playwright install --with-deps chromium && rm -rf /var/lib/apt/lists/*
ENV PLAYWRIGHT_BROWSERS_PATH=/opt/browsers

FROM crawler-dependencies AS crawler
COPY src ./src
RUN uv sync --frozen --no-dev --extra crawl
USER researcher
CMD ["python", "-m", "customer_intelligence.research_stack.server", "crawl"]

FROM node:22-bookworm-slim AS ui
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web ./
RUN npm run build

FROM base AS application
COPY src ./src
RUN uv sync --frozen --no-dev
COPY --from=ui /web/dist /app/web/dist
USER researcher
ENV CIA_DATA_DIR=/data CIA_SECRET_BACKEND=file
CMD ["python", "-m", "customer_intelligence.container_app"]
