from copy import deepcopy

import pytest
from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

from customer_intelligence.demo import seed_demo
from customer_intelligence.models import (
    Assessment,
    Candidate,
    Candidates,
    ChatAnswer,
    InputReview,
    ResearchGaps,
    Settings,
    Source,
    Verification,
    now,
)
from customer_intelligence.providers import ServiceError
from customer_intelligence.research import Research
from customer_intelligence.store import Store


async def configured_research(tmp_path, secrets, monkeypatch, saver, fail_once=False, supported=True):
    store = Store(tmp_path)
    seed_demo(store)
    template = store.get("account", "demo-account-0")["brief"]
    demo_sources = [store.get("source", id) for id in store.get("account", "demo-account-0")["source_ids"]]
    source_text = "\n".join(source["text"] for source in demo_sources)
    store.put(
        "run",
        "live-run",
        {
            "id": "live-run",
            "created_at": now(),
            "is_demo": False,
            "profile": store.get("run", "demo-research")["profile"],
            "settings": Settings().model_dump(),
            "status": "running",
            "account_ids": [],
            "processed": 0,
            "candidate_count": 0,
        },
    )
    research = Research(store, secrets, saver)
    calls = {"read": 0, "search": 0, "verify": 0, "roles": [], "preparations": []}

    async def read(run_id, url, domain):
        calls["read"] += 1
        return Source(
            title="Engineering handbook",
            text=source_text,
            account_domain=domain,
            origin="public",
            source_type="documentation",
            url=url,
            content_hash="fixed-content",
        )

    async def search(run_id, query):
        calls["search"] += 1
        return [
            {"title": "Northstar Labs", "url": "https://northstar.example/handbook", "content": source_text}
        ]

    async def prepare(settings):
        calls["preparations"].append(deepcopy(settings))

    async def structured(run_id, schema, instructions, data, **kwargs):
        role = kwargs["role"]
        expected = (
            "extraction"
            if schema in (Candidates, InputReview)
            else "review"
            if schema is Verification
            else "research"
        )
        assert role == expected
        calls["roles"].append(role)
        if schema is Candidates:
            return Candidates(
                accounts=[
                    Candidate(
                        name="Northstar Labs",
                        domain="northstar.example",
                        urls=["https://northstar.example/handbook"],
                    )
                ]
            )
        if schema is ResearchGaps:
            return ResearchGaps(
                sufficient=True,
                gaps=[],
                confidence=0.8,
                explanation="Synthetic fixture has sufficient evidence.",
            )
        if schema is InputReview:
            return InputReview(observations=[], hypotheses=[])
        if schema is Verification:
            calls["verify"] += 1
            if fail_once and calls["verify"] == 1:
                raise ServiceError("Provider temporarily unavailable")
            return Verification(
                supported=supported,
                issues=[] if supported else ["The claim is not entailed by the supplied quote."],
            )
        brief = deepcopy(template)

        def references(value):
            if isinstance(value, dict):
                if "source_id" in value:
                    value["source_id"] = data["sources"][0]["id"]
                for child in value.values():
                    references(child)
            elif isinstance(value, list):
                for child in value:
                    references(child)

        references(brief)
        return Assessment.model_validate(brief)

    research.search.read = read

    async def healthy():
        return {"ready": True}

    research.search.health = healthy
    research.search.search = search
    research.model.prepare = prepare
    research.model.structured = structured
    return research, store, calls


async def test_graph_delivers_a_verified_brief_with_bounded_candidates(tmp_path, secrets, monkeypatch):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, calls = await configured_research(tmp_path, secrets, monkeypatch, saver)
        await research.execute("live-run", False)
        run = store.get("run", "live-run")
        assert run["status"] == "completed"
        assert len(run["account_ids"]) == 1
        assert run["processed"] == 1
        account = store.get("account", run["account_ids"][0])
        assert not account["is_demo"]
        assert calls["verify"] == 1
        assert {"extraction", "research", "review"} <= set(calls["roles"])
        assert account["review"]["model"] == Settings().models.review.model
        assert account["brief"]["why_fits"][2]["kind"] == "hypothesis"


async def test_resume_reuses_completed_retrieval_and_preserves_account_identity(
    tmp_path, secrets, monkeypatch
):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, calls = await configured_research(
            tmp_path, secrets, monkeypatch, saver, fail_once=True
        )
        await research.execute("live-run", False)
        assert store.get("run", "live-run")["status"] == "paused"
        fetched, searched = calls["read"], calls["search"]
        await research.execute("live-run", True)
        assert store.get("run", "live-run")["status"] == "completed"
        assert len(store.get("run", "live-run")["account_ids"]) == 1
        assert calls["read"] == fetched
        assert calls["search"] == searched


async def test_semantically_unsupported_brief_is_withheld_after_one_repair(tmp_path, secrets, monkeypatch):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, calls = await configured_research(
            tmp_path, secrets, monkeypatch, saver, supported=False
        )
        await research.execute("live-run", False)
        assert store.get("run", "live-run")["status"] == "completed"
        assert store.get("run", "live-run")["account_ids"] == []
        assert calls["verify"] == 2


async def test_imported_account_exclusion_wins_over_profile_fit(tmp_path, secrets, monkeypatch):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, calls = await configured_research(tmp_path, secrets, monkeypatch, saver)
        source = Source(
            title="Existing customer",
            text="Do not prospect this account.",
            account_domain="northstar.example",
            source_type="exclusion",
        )
        store.put("source", source.id, source)
        await research.execute("live-run", False)
        assert store.get("run", "live-run")["account_ids"] == []
        assert calls["read"] == 0


async def test_replayed_save_retains_recommendation_after_checkpoint_gap(tmp_path, secrets, monkeypatch):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, _ = await configured_research(tmp_path, secrets, monkeypatch, saver)
        await research.execute("live-run", False)
        account_id = store.get("run", "live-run")["account_ids"][0]
        account = store.get("account", account_id)
        result = await research.save_account(
            {
                "run_id": "live-run",
                "accepted": [],
                "index": 0,
                "assessment": account["brief"],
                "review": account["review"],
                "source_ids": account["source_ids"],
            }
        )
        assert result["accepted"] == [account_id]
        assert len([item for item in store.all("account") if not item["is_demo"]]) == 1
        assert (
            store.get("snapshot", "live-run:" + account_id)["first_recommended_at"]
            == account["first_recommended_at"]
        )


async def test_contextual_chat_withholds_unsupported_facts(tmp_path, secrets, monkeypatch):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, _ = await configured_research(tmp_path, secrets, monkeypatch, saver)
        await research.execute("live-run", False)
        account = store.get("account", store.get("run", "live-run")["account_ids"][0])

        async def unsupported(run_id, schema, instructions, data, **kwargs):
            if schema is ChatAnswer:
                return ChatAnswer(answer="They have approved a purchase budget.", evidence=[])
            return Verification(supported=False, issues=["No source establishes an approved budget."])

        research.model.structured = unsupported
        with pytest.raises(ServiceError, match="could not be supported"):
            await research.chat(account, "Has their budget been approved?")
        assert store.all("chat") == []


async def test_resume_and_chat_prepare_original_legacy_settings(tmp_path, secrets, monkeypatch):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, calls = await configured_research(
            tmp_path, secrets, monkeypatch, saver, fail_once=True
        )
        legacy = Settings().model_dump()
        legacy.pop("models")
        legacy["model"] = "anthropic/claude-sonnet-4.6"
        store.patch("run", "live-run", settings=legacy)
        await research.execute("live-run", False)
        assert store.get("run", "live-run")["status"] == "paused"
        store.put("config", "settings", Settings())
        await research.execute("live-run", True)
        account = store.get("account", store.get("run", "live-run")["account_ids"][0])
        chat_calls = []

        async def answer(run_id, schema, instructions, data, **kwargs):
            chat_calls.append(kwargs["role"])
            assert run_id == "live-run"
            if schema is ChatAnswer:
                return ChatAnswer(answer="No budget information is provided.", evidence=[])
            return Verification(supported=True, issues=[])

        research.model.structured = answer
        await research.chat(account, "Is there a budget?")
        assert chat_calls == ["research", "review"]
        assert calls["preparations"] == [legacy, legacy, legacy]
        assert store.get("run", "live-run")["settings"] == legacy
        assert store.all("chat")[0]["review"]["model"] == legacy["model"]


async def test_old_save_checkpoint_cannot_skip_new_review_gate(tmp_path, secrets, monkeypatch):
    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, calls = await configured_research(tmp_path, secrets, monkeypatch, saver)
        await research.execute("live-run", False)
        account = store.get("account", store.get("run", "live-run")["account_ids"][0])
        previous_reviews = calls["verify"]
        await research.save_account(
            {
                "run_id": "live-run",
                "accepted": [],
                "index": 0,
                "assessment": account["brief"],
                "source_ids": account["source_ids"],
                "candidates": [{"domain": account["domain"], "name": account["name"]}],
            }
        )
        assert calls["verify"] == previous_reviews + 1


async def test_review_gets_original_sources_and_repairs_invalid_output_once(tmp_path, secrets, monkeypatch):
    from customer_intelligence.providers import StructuredOutputError

    async with AsyncSqliteSaver.from_conn_string(str(tmp_path / "checkpoints.sqlite3")) as saver:
        research, store, _ = await configured_research(tmp_path, secrets, monkeypatch, saver)
        await research.execute("live-run", False)
        account = store.get("account", store.get("run", "live-run")["account_ids"][0])
        source_id = account["source_ids"][0]
        source = store.get("source", source_id)
        source["text"] += "\n" + "x" * 12000 + "\nOriginal source ending."
        store.put("source", source_id, source)
        wrapped = research.model.structured
        counts = {"review": 0, "research": 0}

        async def review(run_id, schema, instructions, data, **kwargs):
            if schema is Verification:
                counts["review"] += 1
                assert data["sources"][0]["text"].endswith("Original source ending.")
                if counts["review"] == 1:
                    raise StructuredOutputError("Synthetic invalid review JSON")
            else:
                counts["research"] += 1
                if counts["research"] == 2:
                    assert "Synthetic invalid review JSON" in data["corrections_required"]
            result = await wrapped(run_id, schema, instructions, data, **kwargs)
            if schema is Assessment:
                result.why_now = None  # Missing timing is a valid, reviewed recommendation.
            return result

        research.model.structured = review
        result = await research.assess(
            {
                "run_id": "live-run",
                "index": 0,
                "source_ids": account["source_ids"],
                "candidates": [{"domain": account["domain"], "name": account["name"]}],
            }
        )
        assert counts == {"review": 2, "research": 2}
        assert result["review"]["supported"] and result["assessment"]["why_now"] is None
