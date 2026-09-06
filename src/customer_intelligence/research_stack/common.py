import asyncio
import hashlib
import hmac
import json
import logging
import os
import sqlite3
import time
from collections import deque
from pathlib import Path

import httpx
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from starlette.responses import JSONResponse

from ..models import now

TOOLS = {"search_web", "search_news", "fetch_page", "crawl_site", "extract_structured", "research_health"}


class ToolError(Exception):
    def __init__(self, code, message, retryable=False):
        self.code, self.message, self.retryable = code, message, retryable
        super().__init__(message)

    def result(self):
        return {
            "ok": False,
            "error": {"code": self.code, "message": self.message, "retryable": self.retryable},
        }


def token(name):
    direct = os.environ.get(name)
    if direct:
        if len(direct.strip()) < 32:
            raise ToolError("not_configured", "A research service credential is invalid.")
        return direct.strip()
    path = os.environ.get(name + "_FILE")
    if not path:
        raise ToolError(
            "not_configured",
            "Research credentials are not configured. Start the Docker stack and connect the local app.",
        )
    try:
        value = Path(path).read_text().strip()
    except OSError as error:
        raise ToolError("not_configured", "The research service credential file is unavailable.") from error
    if len(value) < 32:
        raise ToolError("not_configured", "A research service credential is invalid.")
    return value


class ServiceAuth:
    """No anonymous MCP, bounded payloads, no cross-origin browser callers."""

    def __init__(self, app, credential, max_body=64000):
        self.app, self.credential, self.max_body = app, credential, max_body
        self.requests = deque()

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = dict(scope["headers"])
        if scope["path"] == "/health" and scope["method"] == "GET":
            return await JSONResponse({"status": "ok"})(scope, receive, send)
        if headers.get(b"origin") or not hmac.compare_digest(
            headers.get(b"authorization", b"").decode(), "Bearer " + self.credential
        ):
            return await JSONResponse({"error": "authentication_required"}, status_code=401)(
                scope, receive, send
            )
        current = time.monotonic()
        while self.requests and self.requests[0] < current - 60:
            self.requests.popleft()
        if len(self.requests) >= 180:
            return await JSONResponse({"error": "rate_limited"}, status_code=429)(scope, receive, send)
        self.requests.append(current)
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > self.max_body:
                return await JSONResponse({"error": "request_too_large"}, status_code=413)(
                    scope, receive, send
                )
            if not message.get("more_body"):
                break
        delivered = False

        async def bounded_receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, bounded_receive, send)


class BoundedStream(httpx.AsyncByteStream):
    def __init__(self, stream):
        self.stream = stream

    async def __aiter__(self):
        size = 0
        async for chunk in self.stream:
            size += len(chunk)
            if size > 2_000_000:
                raise ToolError("response_too_large", "The research response exceeded its byte limit.")
            yield chunk

    async def aclose(self):
        await self.stream.aclose()


class BoundedTransport(httpx.AsyncHTTPTransport):
    async def handle_async_request(self, request):
        response = await super().handle_async_request(request)
        response.stream = BoundedStream(response.stream)
        return response


async def mcp_call(url, credential, tool, arguments, timeout=150):
    if tool not in TOOLS:
        raise ToolError("tool_denied", "This research tool is not approved.")
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient(
                headers={"Authorization": "Bearer " + credential},
                timeout=timeout,
                trust_env=False,
                transport=BoundedTransport(trust_env=False),
            ) as http:
                async with streamable_http_client(url, http_client=http) as (read, write, _):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        result = await session.call_tool(tool, arguments)
                        if result.isError:
                            raise ToolError(
                                "invalid_tool_result", "The research service rejected the tool call."
                            )
                        data = result.structuredContent
                        if data is None:
                            data = json.loads(
                                next(block.text for block in result.content if block.type == "text")
                            )
                        if len(json.dumps(data)) > 2_000_000:
                            raise ToolError("response_too_large", "The research response exceeded its limit.")
                        return data
    except ToolError:
        raise
    except (Exception, TimeoutError) as error:
        # MCP transport task groups may wrap the original connection failure.
        raise ToolError(
            "service_unavailable",
            "The research service could not finish. Check Docker service health and retry.",
            True,
        ) from error


class Ledger:
    def __init__(self, directory):
        Path(directory).mkdir(parents=True, exist_ok=True)
        self.path = str(Path(directory) / "research.sqlite3")
        with self.connect() as db:
            db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS cache (id TEXT PRIMARY KEY, expires REAL, value TEXT);
            CREATE TABLE IF NOT EXISTS audit (id INTEGER PRIMARY KEY, data TEXT);
            CREATE TABLE IF NOT EXISTS counters (run_id TEXT, name TEXT, value INTEGER, PRIMARY KEY(run_id,name));
            CREATE TABLE IF NOT EXISTS evidence (id TEXT PRIMARY KEY, data TEXT);
            """)
        self.metrics = {}

    def connect(self):
        return sqlite3.connect(self.path, timeout=15)

    def count(self, name, amount=1):
        self.metrics[name] = self.metrics.get(name, 0) + amount

    def consume(self, run_id, name, amount, limit):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute(
                "SELECT value FROM counters WHERE run_id=? AND name=?", (run_id, name)
            ).fetchone()
            total = (row[0] if row else 0) + amount
            if total > limit:
                raise ToolError(
                    "resource_limit", f"The run's {name.replace('_', ' ')} limit has been reached."
                )
            db.execute(
                "INSERT INTO counters VALUES(?,?,?) ON CONFLICT(run_id,name) DO UPDATE SET value=excluded.value",
                (run_id, name, total),
            )

    def get(self, key):
        with self.connect() as db:
            row = db.execute(
                "SELECT value FROM cache WHERE id=? AND expires>?", (key, time.time())
            ).fetchone()
        self.count("cache_hits_total" if row else "cache_misses_total")
        return json.loads(row[0]) if row else None

    def put(self, key, value, ttl):
        with self.connect() as db:
            db.execute("DELETE FROM cache WHERE expires < ?", (time.time(),))
            db.execute(
                "INSERT OR REPLACE INTO cache VALUES(?,?,?)", (key, time.time() + ttl, json.dumps(value))
            )
            db.execute(
                "DELETE FROM cache WHERE id IN (SELECT id FROM cache ORDER BY expires DESC LIMIT -1 OFFSET 500)"
            )

    def evidence(self, evidence):
        with self.connect() as db:
            db.execute(
                "INSERT OR IGNORE INTO evidence VALUES(?,?)", (evidence["evidence_id"], json.dumps(evidence))
            )

    def audit(self, **entry):
        data = {"timestamp": now(), "caller": "intelligence", **entry}
        with self.connect() as db:
            db.execute("INSERT INTO audit(data) VALUES(?)", (json.dumps(data),))
        logging.getLogger("research.audit").info(json.dumps(data))


def cache_key(tool, arguments, context):
    safe = {key: value for key, value in context.items() if key not in {"request_id", "graph_run_id"}}
    return hashlib.sha256(json.dumps([tool, arguments, safe], sort_keys=True).encode()).hexdigest()
