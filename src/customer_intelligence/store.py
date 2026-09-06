import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from .models import now, uid


class BudgetExceeded(Exception):
    pass


class Store:
    def __init__(self, directory: Path):
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory = directory
        self.path = directory / "intelligence.sqlite3"
        with self.connect() as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS objects (
                    kind TEXT NOT NULL, id TEXT NOT NULL, data TEXT NOT NULL,
                    created_at TEXT NOT NULL, PRIMARY KEY(kind,id)
                );
                CREATE TABLE IF NOT EXISTS charges (
                    id TEXT PRIMARY KEY, run_id TEXT NOT NULL, service TEXT NOT NULL,
                    reserved REAL NOT NULL, actual REAL, status TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE VIRTUAL TABLE IF NOT EXISTS source_search USING fts5(id UNINDEXED,title,text);
                PRAGMA user_version=1;
            """)
        self.path.chmod(0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=20)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA secure_delete=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def get(self, kind, id):
        with self.connect() as db:
            row = db.execute("SELECT data FROM objects WHERE kind=? AND id=?", (kind, id)).fetchone()
            return json.loads(row[0]) if row else None

    def all(self, kind):
        with self.connect() as db:
            return [
                json.loads(row[0])
                for row in db.execute(
                    "SELECT data FROM objects WHERE kind=? ORDER BY created_at DESC", (kind,)
                )
            ]

    def put(self, kind, id, data):
        if hasattr(data, "model_dump"):
            data = data.model_dump(mode="json")
        with self.connect() as db:
            db.execute(
                """INSERT INTO objects VALUES(?,?,?,?) ON CONFLICT(kind,id)
                       DO UPDATE SET data=excluded.data""",
                (kind, id, json.dumps(data), now()),
            )
            if kind == "source":
                db.execute("DELETE FROM source_search WHERE id=?", (id,))
                db.execute("INSERT INTO source_search VALUES(?,?,?)", (id, data["title"], data["text"]))
        return data

    def patch(self, kind, id, **changes):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT data FROM objects WHERE kind=? AND id=?", (kind, id)).fetchone()
            if not row:
                raise KeyError(id)
            data = json.loads(row[0]) | changes
            db.execute("UPDATE objects SET data=? WHERE kind=? AND id=?", (json.dumps(data), kind, id))
        return data

    def delete(self, kind, id):
        with self.connect() as db:
            db.execute("DELETE FROM objects WHERE kind=? AND id=?", (kind, id))
            if kind == "source":
                db.execute("DELETE FROM source_search WHERE id=?", (id,))

    def search_sources(self, query, limit=20):
        words = [word.replace('"', "") for word in query.split() if word.strip('"')]
        if not words:
            return []
        match = " OR ".join('"' + word + '"' for word in words[:12])
        with self.connect() as db:
            rows = db.execute(
                "SELECT id FROM source_search WHERE source_search MATCH ? ORDER BY rank LIMIT ?",
                (match, limit),
            ).fetchall()
        return [source for row in rows if (source := self.get("source", row[0]))]

    def reserve(self, run_id, service, amount, limit, metadata=None):
        with self.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            used = db.execute(
                "SELECT COALESCE(SUM(COALESCE(actual,reserved)),0) FROM charges WHERE run_id=? AND service=?",
                (run_id, service),
            ).fetchone()[0]
            if used + amount > limit + 1e-9:
                raise BudgetExceeded(
                    f"{service} budget reached. Saved results are available; increase the run budget in Research runs to continue."
                )
            charge_id = uid()
            db.execute(
                "INSERT INTO charges VALUES(?,?,?,?,?,?,?)",
                (charge_id, run_id, service, amount, None, "reserved", now()),
            )
            if metadata is not None:
                record = {
                    **metadata,
                    "id": charge_id,
                    "run_id": run_id,
                    "at": now(),
                    "reserved_usd": amount,
                    "actual_usd": None,
                    "status": "reserved",
                    "provider": None,
                    "usage": {},
                    "verdict": None,
                }
                db.execute(
                    "INSERT INTO objects VALUES(?,?,?,?)",
                    ("model_call", charge_id, json.dumps(record), record["at"]),
                )
        return charge_id

    def settle(self, charge_id, actual=None, **metadata):
        with self.connect() as db:
            db.execute(
                "UPDATE charges SET actual=?,status=? WHERE id=?",
                (actual, "confirmed" if actual is not None else "estimated", charge_id),
            )
            row = db.execute(
                "SELECT data FROM objects WHERE kind='model_call' AND id=?", (charge_id,)
            ).fetchone()
            if row:
                record = json.loads(row[0]) | {
                    "actual_usd": actual,
                    "status": "completed" if actual is not None else "estimated",
                    **metadata,
                }
                db.execute(
                    "UPDATE objects SET data=? WHERE kind='model_call' AND id=?",
                    (json.dumps(record), charge_id),
                )

    def costs(self, run_id):
        result = {
            "model_usd": 0,
            "search_credits": 0,
            "search_queries": 0,
            "pages_fetched": 0,
            "has_estimates": False,
            "by_role": {
                role: {"model_usd": 0, "calls": 0, "has_estimates": False}
                for role in ("extraction", "research", "review")
            },
        }
        with self.connect() as db:
            for row in db.execute(
                "SELECT c.service,COALESCE(c.actual,c.reserved) amount,c.actual,m.data metadata FROM charges c LEFT JOIN objects m ON m.kind='model_call' AND m.id=c.id WHERE c.run_id=?",
                (run_id,),
            ):
                result["model_usd" if row["service"] == "OpenRouter" else "search_credits"] += row["amount"]
                result["has_estimates"] |= row["actual"] is None
                if row["service"] == "OpenRouter":
                    metadata = json.loads(row["metadata"]) if row["metadata"] else {}
                    role = metadata.get("role", "legacy")
                    group = result["by_role"].setdefault(
                        role, {"model_usd": 0, "calls": 0, "has_estimates": False}
                    )
                    group["model_usd"] += row["amount"]
                    group["calls"] += 1
                    group["has_estimates"] |= row["actual"] is None
        for call in self.all("tool_call"):
            if call["run_id"] == run_id:
                if call["tool"] in {"search_web", "search_news"}:
                    result["search_queries"] += 1
                elif call["tool"] in {"fetch_page", "extract_structured"}:
                    result["pages_fetched"] += 1
        result["model_usd"] = round(result["model_usd"], 6)
        for group in result["by_role"].values():
            group["model_usd"] = round(group["model_usd"], 6)
        return result

    def event(self, run_id, message, **extra):
        event = {"id": uid(), "run_id": run_id, "at": now(), "message": message, **extra}
        self.put("event", event["id"], event)
