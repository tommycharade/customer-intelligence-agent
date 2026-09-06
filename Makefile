.PHONY: up down test lint format research connect-native open
up:
	docker compose up -d --build

down:
	docker compose down

test:
	uv run --extra crawl pytest
	npm --prefix web run check

lint:
	uv run ruff check .
	uv run ruff format --check .

format:
	uv run ruff check . --fix
	uv run ruff format .

connect-native:
	uv run python scripts/research_stack.py connect-native

open:
	uv run python scripts/research_stack.py open

research:
	uv run python scripts/research_stack.py research --domain "$(DOMAIN)"
