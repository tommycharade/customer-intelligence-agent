import asyncio
import csv
import hashlib
import hmac
import html
import io
import json
import secrets as random_secrets
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
from pydantic import BaseModel, Field

from .config import Secrets, data_directory
from .demo import seed_demo
from .evidence import canonical_domain, rank_key
from .imports import MAX_UPLOAD, preview
from .models import ChatRequest, Outcome, Profile, Settings, Source, now, uid
from .providers import ServiceError
from .research import Research
from .store import BudgetExceeded, Store


class SaveInputs(BaseModel):
    sources: list[Source] = Field(min_length=1, max_length=500)


class Credential(BaseModel):
    value: str = Field(max_length=1000)


class NewRun(BaseModel):
    target_domain: str | None = None


class RunBudget(BaseModel):
    model_budget: float = Field(ge=0.1, le=100)
    search_budget: int = Field(ge=1, le=1000)


def create_app(directory=None, auth_token=None, secret_store=None):
    store = Store(directory or data_directory())
    credentials = secret_store or Secrets()
    launch_token = auth_token or random_secrets.token_urlsafe(32)
    session_token = random_secrets.token_urlsafe(32)

    @asynccontextmanager
    async def lifespan(app):
        async with AsyncSqliteSaver.from_conn_string(str(store.directory / "checkpoints.sqlite3")) as saver:
            await saver.setup()
            await saver.conn.execute("PRAGMA secure_delete=ON")
            app.state.research = Research(store, credentials, saver)
            for run in store.all("run"):
                if run["status"] == "running":
                    store.patch("run", run["id"], status="interrupted", stage="Restarted; ready to resume")
            yield
            tasks = list(app.state.research.tasks.values())
            for task in tasks:
                task.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)

    app = FastAPI(
        title="Customer Intelligence Agent", version="0.1.0", lifespan=lifespan, docs_url=None, redoc_url=None
    )
    app.state.store, app.state.launch_token = store, launch_token

    @app.middleware("http")
    async def local_session(request, call_next):
        host = request.headers.get("host", "").split(":")[0]
        if host not in {"127.0.0.1", "localhost"}:
            return JSONResponse({"detail": "Only local requests are accepted."}, status_code=403)
        try:
            content_length = int(request.headers.get("content-length", "0"))
        except ValueError:
            return JSONResponse({"detail": "Invalid request size."}, status_code=400)
        if content_length > 20 * 1024 * 1024:
            return JSONResponse({"detail": "This request exceeds the 20 MB limit."}, status_code=413)
        if request.url.path not in {"/auth", "/health"}:
            if not hmac.compare_digest(request.cookies.get("ci_session", ""), session_token):
                if request.url.path.startswith("/api/"):
                    return JSONResponse(
                        {"detail": "Session expired. Open the app using its launcher."}, status_code=401
                    )
                return HTMLResponse(
                    "<h1>Open Customer Intelligence from its launcher</h1><p>Your local session has expired. Run scripts/start.sh or double-click Start Customer Intelligence.command.</p>",
                    status_code=401,
                )
            origin = request.headers.get("origin")
            if (
                request.method not in {"GET", "HEAD", "OPTIONS"}
                and origin != f"http://{request.headers['host']}"
            ):
                return JSONResponse({"detail": "A same-origin local session is required."}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; font-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
        )
        return response

    @app.get("/health")
    async def health():
        return {"status": "ok", "version": "0.1.0"}

    @app.get("/auth")
    async def authenticate(token: str = ""):
        if not hmac.compare_digest(token, launch_token):
            raise HTTPException(403, "Use the authenticated URL printed by the launcher.")
        response = RedirectResponse("/", status_code=303)
        response.set_cookie("ci_session", session_token, httponly=True, samesite="strict", max_age=86400 * 7)
        return response

    def require(kind, id):
        value = store.get(kind, id)
        if value is None:
            raise HTTPException(404, "This record could not be found.")
        return value

    def settings():
        return Settings.model_validate(store.get("config", "settings") or {})

    def run_view(run):
        return run | {"costs": store.costs(run["id"])}

    @app.get("/api/bootstrap")
    async def bootstrap():
        return {
            "profile": store.get("config", "profile"),
            "settings": settings().model_dump(),
            "credentials": credentials.status(),
            "data_directory": str(store.directory),
        }

    @app.put("/api/profile")
    async def save_profile(profile: Profile):
        return store.put("config", "profile", profile)

    @app.put("/api/settings")
    async def save_settings(value: Settings):
        value.allowed_domains = [canonical_domain(domain) for domain in value.allowed_domains]
        value.blocked_domains = [canonical_domain(domain) for domain in value.blocked_domains]
        return store.put("config", "settings", value)

    @app.put("/api/credentials/{name}")
    async def save_credential(name: str, value: Credential):
        if name not in Secrets.NAMES:
            raise HTTPException(404, "Unknown credential")
        try:
            credentials.set(name, value.value.strip())
        except Exception as error:
            raise HTTPException(
                503,
                "macOS Keychain could not save this key. Unlock your login Keychain and try again, or configure an environment override.",
            ) from error
        return credentials.status()

    @app.get("/api/models")
    async def models():
        try:
            return await app.state.research.model.models()
        except Exception as error:
            raise HTTPException(503, "Could not load the model catalogue. Check your connection.") from error

    @app.post("/api/check-connections")
    async def check_connections():
        result = {"openrouter": "missing", "tavily": "missing"}
        import httpx

        async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
            for name, url in [
                ("openrouter", "https://openrouter.ai/api/v1/key"),
                ("tavily", "https://api.tavily.com/usage"),
            ]:
                if key := credentials.get(name):
                    try:
                        response = await client.get(url, headers={"Authorization": f"Bearer {key}"})
                        result[name] = (
                            "connected"
                            if response.is_success
                            else f"HTTP {response.status_code} — check key and account access"
                        )
                    except httpx.HTTPError:
                        result[name] = "unavailable — check network and TLS certificates"
        return result

    @app.post("/api/imports/preview")
    async def preview_import(file: UploadFile = File(...)):
        content = await file.read(MAX_UPLOAD + 1)
        try:
            parsed = await asyncio.to_thread(preview, Path(file.filename or "input.txt").name, content)
            return [source.model_dump(mode="json") for source in parsed]
        except Exception as error:
            raise HTTPException(
                400,
                str(error)
                if isinstance(error, ValueError)
                else "This file could not be parsed. Export a text copy and retry.",
            ) from error

    @app.post("/api/imports")
    async def save_inputs(inputs: SaveInputs):
        result = []
        for source in inputs.sources:
            if (
                not source.title.strip()
                or not source.text.strip()
                or len(source.text) > 150000
                or len(source.title) > 300
            ):
                raise HTTPException(422, "Each input needs a title and 1–150,000 characters of text.")
            source.origin, source.is_demo, source.url = "upload", False, None
            source.account_domain = canonical_domain(source.account_domain) if source.account_domain else None
            if source.published_at:
                try:
                    datetime.fromisoformat(source.published_at)
                except ValueError as error:
                    raise HTTPException(
                        422, "Use an ISO date such as 2026-09-06, or leave the source date blank."
                    ) from error
            source.content_hash = hashlib.sha256(source.text.encode()).hexdigest()
            source.id = hashlib.sha256(
                (source.content_hash + str(source.account_domain) + source.source_type).encode()
            ).hexdigest()[:32]
            result.append(source.model_dump())
        for source in result:
            store.put("source", source["id"], source)
        return result

    @app.get("/api/sources")
    async def list_sources(query: str = "", demo: bool = False):
        sources = store.search_sources(query) if query else store.all("source")
        return [
            source | {"text": source["text"][:500], "characters": len(source["text"])}
            for source in sources
            if source["is_demo"] == demo
        ]

    @app.get("/api/sources/{id}")
    async def get_source(id: str):
        return require("source", id)

    @app.delete("/api/sources/{id}")
    async def delete_source(id: str):
        require("source", id)
        if app.state.research.active() or any(not run["is_demo"] for run in store.all("run")):
            raise HTTPException(
                409,
                "Research history may retain this input. Use Settings → Delete research data to remove inputs, briefs and checkpoints together.",
            )
        store.delete("source", id)
        return {"deleted": True}

    @app.post("/api/runs", status_code=201)
    async def new_run(body: NewRun):
        if app.state.research.active():
            raise HTTPException(409, "Another run or chat is active. Wait for it or cancel the run.")
        profile = store.get("config", "profile")
        if not profile:
            raise HTTPException(422, "Complete your customer profile before starting research.")
        if not all(credentials.get(name) for name in Secrets.NAMES):
            raise HTTPException(422, "Add your OpenRouter and Tavily keys in Settings.")
        domain = canonical_domain(body.target_domain) if body.target_domain else None
        run = {
            "id": uid(),
            "created_at": now(),
            "completed_at": None,
            "is_demo": False,
            "status": "running",
            "stage": "Preparing research",
            "profile": profile,
            "settings": settings().model_dump(),
            "candidate_count": 0,
            "processed": 0,
            "account_ids": [],
            "error": None,
            "target_domain": domain,
            "input_review": {"observations": [], "hypotheses": []},
        }
        store.put("run", run["id"], run)
        app.state.research.start(run["id"])
        return run_view(run)

    @app.get("/api/runs")
    async def list_runs(demo: bool = False):
        return [run_view(run) for run in store.all("run") if run["is_demo"] == demo]

    @app.get("/api/runs/{id}")
    async def get_run(id: str):
        return run_view(require("run", id))

    @app.get("/api/runs/{id}/events")
    async def run_events(id: str, request: Request):
        require("run", id)

        async def stream():
            last = None
            while not await request.is_disconnected():
                run = store.get("run", id)
                if not run:
                    return
                payload = json.dumps(
                    {
                        "run": run_view(run),
                        "events": [event for event in reversed(store.all("event")) if event["run_id"] == id],
                    }
                )
                if payload != last:
                    yield f"event: progress\ndata: {payload}\n\n"
                    last = payload
                else:
                    yield ": keepalive\n\n"
                if run["status"] != "running":
                    return
                await asyncio.sleep(1)

        return StreamingResponse(
            stream(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"}
        )

    @app.post("/api/runs/{id}/cancel")
    async def cancel_run(id: str):
        require("run", id)
        task = app.state.research.tasks.get(id)
        if task and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        if store.get("run", id)["status"] == "running":
            store.patch("run", id, status="cancelled", stage="Stopped; progress saved")
        return run_view(require("run", id))

    @app.post("/api/runs/{id}/resume")
    async def resume_run(id: str):
        run = require("run", id)
        if run["is_demo"] or run["status"] not in {"paused", "cancelled", "interrupted"}:
            raise HTTPException(409, "Only interrupted, paused or cancelled live runs can resume.")
        try:
            app.state.research.start(id, resume=True)
        except ValueError as error:
            raise HTTPException(409, str(error)) from error
        return {"resumed": True}

    @app.put("/api/runs/{id}/budget")
    async def update_budget(id: str, budget: RunBudget):
        run = require("run", id)
        if app.state.research.active() or run["is_demo"]:
            raise HTTPException(409, "Stop active work before changing a live run's budget.")
        return store.patch("run", id, settings=run["settings"] | budget.model_dump())

    @app.get("/api/accounts")
    async def accounts(demo: bool = False, run_id: str | None = None):
        values = store.all("snapshot") if run_id else store.all("account")
        return sorted(
            [
                account
                for account in values
                if account["is_demo"] == demo and (not run_id or account["run_id"] == run_id)
            ],
            key=rank_key,
            reverse=True,
        )

    @app.get("/api/accounts/{id}")
    async def get_account(id: str):
        return require("account", id)

    @app.put("/api/accounts/{id}/outcome")
    async def save_outcome(id: str, outcome: Outcome):
        account = require("account", id)
        record = outcome.model_dump() | {
            "updated_at": now(),
            "relevant_conversation_at": now() if outcome.status == "relevant_conversation" else None,
        }
        if outcome.status == "relevant_conversation" and account["outcome"].get("relevant_conversation_at"):
            record["relevant_conversation_at"] = account["outcome"]["relevant_conversation_at"]
        store.put("outcome_event", uid(), {"account_id": id, **record})
        return store.patch("account", id, outcome=record)

    @app.get("/api/accounts/{id}/chat")
    async def get_chat(id: str):
        require("account", id)
        return [item for item in reversed(store.all("chat")) if item["account_id"] == id]

    @app.post("/api/accounts/{id}/chat")
    async def chat(id: str, body: ChatRequest):
        account = require("account", id)
        research = app.state.research
        if research.active():
            raise HTTPException(409, "Wait for the active research or chat to finish.")
        task_id = "chat:" + uid()
        research.tasks[task_id] = asyncio.current_task()
        try:
            return await research.chat(account, body.message)
        except (ServiceError, BudgetExceeded) as error:
            raise HTTPException(422, str(error)) from error
        finally:
            research.tasks.pop(task_id, None)

    @app.get("/api/metrics")
    async def metrics():
        cohorts = {}
        for account in store.all("account"):
            if account["is_demo"]:
                continue
            day = datetime.fromisoformat(account["first_recommended_at"]).date()
            week = (day - timedelta(days=day.weekday())).isoformat()
            cohort = cohorts.setdefault(
                week,
                {
                    "week": week,
                    "recommended": 0,
                    "contacted": 0,
                    "relevant": 0,
                    "uncontacted": 0,
                    "rejected": 0,
                },
            )
            status = account["outcome"]["status"]
            cohort["recommended"] += 1
            cohort["contacted"] += status in {"contacted", "conversation", "relevant_conversation"}
            cohort["relevant"] += status == "relevant_conversation"
            cohort["uncontacted"] += status in {"unreviewed", "shortlisted"}
            cohort["rejected"] += status == "rejected"
        return sorted(
            [
                cohort | {"conversion": cohort["relevant"] / cohort["recommended"]}
                for cohort in cohorts.values()
            ],
            key=lambda cohort: cohort["week"],
            reverse=True,
        )

    @app.post("/api/demo")
    async def demo():
        return {"run_id": seed_demo(store)}

    @app.get("/api/export")
    async def export_data():
        with store.connect() as db:
            records = [
                dict(row) | {"data": json.loads(row["data"])} for row in db.execute("SELECT * FROM objects")
            ]
            charges = [dict(row) for row in db.execute("SELECT * FROM charges")]
        return Response(
            json.dumps(
                {"version": 1, "exported_at": now(), "records": records, "charges": charges}, indent=2
            ),
            media_type="application/json",
            headers={"Content-Disposition": 'attachment; filename="customer-intelligence.json"'},
        )

    @app.get("/api/accounts/{id}/export")
    async def export_account(id: str, format: str = "markdown"):
        account = require("account", id)
        brief = account["brief"]
        if format == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(
                [
                    "company",
                    "domain",
                    "fit",
                    "why_fits",
                    "why_now",
                    "stakeholders",
                    "what_could_help",
                    "evidence",
                    "outcome",
                    "synthetic",
                ]
            )
            values = [
                account["name"],
                account["domain"],
                brief["fit"],
                json.dumps(brief["why_fits"]),
                json.dumps(brief["why_now"]),
                json.dumps(brief["who_matters"]),
                json.dumps(brief["what_could_help"]),
                json.dumps([store.get("source", id) for id in account["source_ids"]]),
                account["outcome"]["status"],
                str(account["is_demo"]),
            ]
            writer.writerow(
                [
                    "'" + value if value.startswith(("=", "+", "-", "@", "\t", "\r")) else value
                    for value in values
                ]
            )
            return Response(
                output.getvalue(),
                media_type="text/csv",
                headers={"Content-Disposition": 'attachment; filename="account-brief.csv"'},
            )
        lines = [
            f"# {account['name']}",
            "Synthetic demonstration — not a real prospect.\n" if account["is_demo"] else "",
            f"Domain: {account['domain']}",
            "\n## Why this account fits",
        ]
        lines += [f"- **{claim['kind'].title()}:** {claim['text']}" for claim in brief["why_fits"]]
        lines += [
            "\n## Why now",
            brief["why_now"]["text"] if brief["why_now"] else "no timing signal found.",
            "\n## Who matters",
        ]
        lines += [
            f"- {person['role']}: {person['name'] or person['title']} ({person['confidence']} confidence). {person['basis']['text']}"
            for person in brief["who_matters"]
        ]
        lines += ["\n## What could help"] + [
            f"- {item['title']} ({item['kind']}): {item['reason']}" for item in brief["what_could_help"]
        ]
        lines += ["\n## Evidence"]
        claims = (
            brief["why_fits"]
            + [person["basis"] for person in brief["who_matters"]]
            + ([brief["why_now"]] if brief["why_now"] else [])
        )
        for claim in claims:
            lines += [f"\n**{claim['kind']}: {claim['text']}**"]
            for link in claim["evidence"]:
                source = store.get("source", link["source_id"])
                if source:
                    lines += [
                        f"> {link['quote']}",
                        f"Source: {source['title']} | {source['url'] or 'Imported/synthetic material'} | published: {source['published_at'] or 'unknown'} | retrieved: {source['retrieved_at']}",
                    ]
        return Response(
            "\n".join(lines),
            media_type="text/markdown",
            headers={"Content-Disposition": 'attachment; filename="account-brief.md"'},
        )

    @app.delete("/api/data")
    async def delete_data():
        if app.state.research.active():
            raise HTTPException(409, "Stop the active run or chat before deleting research data.")
        with store.connect() as db:
            db.execute("PRAGMA secure_delete=ON")
            db.execute("DELETE FROM objects WHERE kind != 'config'")
            db.execute("DROP TABLE source_search")
            db.execute("CREATE VIRTUAL TABLE source_search USING fts5(id UNINDEXED,title,text)")
            db.execute("DELETE FROM charges")
        saver = app.state.research.checkpointer
        await saver.conn.execute("DELETE FROM checkpoints")
        await saver.conn.execute("DELETE FROM writes")
        await saver.conn.commit()
        await saver.conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        with store.connect() as db:
            db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return {"deleted": True, "retained": "Profile, settings and Keychain credentials"}

    @app.exception_handler(ValueError)
    async def value_error(request, error):
        return JSONResponse({"detail": str(error)}, status_code=422)

    @app.get("/docs", response_class=HTMLResponse)
    async def api_docs():
        rows = "".join(
            f"<tr><td>{html.escape(method.upper())}</td><td>{html.escape(path)}</td><td>{html.escape(operation.get('summary', ''))}</td></tr>"
            for path, methods in app.openapi()["paths"].items()
            for method, operation in methods.items()
        )
        return f'<html><title>Local API</title><body style="font:16px system-ui;padding:32px"><h1>Customer Intelligence API</h1><p>Authenticated, local session required. Mutations require a matching Origin header.</p><a href="/openapi.json">OpenAPI schema</a><table cellpadding="10">{rows}</table></body></html>'

    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="frontend")
    else:

        @app.get("/", response_class=HTMLResponse)
        async def missing_frontend():
            return "<h1>Build the interface first</h1><p>Run scripts/setup.sh, then restart the app.</p>"

    return app
