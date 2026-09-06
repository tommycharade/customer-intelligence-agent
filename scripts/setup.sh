#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
uv sync --locked
npm --prefix web ci
npm --prefix web run build
uv run playwright install chromium
printf '\nReady. Run ./scripts/start.sh to open Customer Intelligence.\n'
