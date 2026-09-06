"""No paid calls: catalogue and completion responses are synthetic fixtures."""

import asyncio
import json
from copy import deepcopy

import httpx
import pytest
from pydantic import ValidationError

from customer_intelligence.models import MODEL_ROLES, OUTPUT_LIMITS, RoleModel, Settings, Verification
from customer_intelligence.providers import OpenRouter, StructuredOutputError
from customer_intelligence.routing import ServiceError, price_bounds
from customer_intelligence.store import BudgetExceeded, Store

FLASH = "z-ai/glm-5.3-flash"
REVIEW = "z-ai/glm-5.3"


def model_client(tmp_path, secrets, catalogue):
    store = Store(tmp_path)
    store.put("run", "test", {"settings": Settings().model_dump()})
    secrets.values["openrouter"] = "synthetic-test-key"
    client = OpenRouter(store, secrets)
    client.catalogue = catalogue
    return client, store


def mock_transport(monkeypatch, handler):
    original = httpx.AsyncClient
    monkeypatch.setattr(
        "customer_intelligence.providers.httpx.AsyncClient",
        lambda **kwargs: original(transport=httpx.MockTransport(handler), **kwargs),
    )


def completion(cost=0.02, content='{"supported":true,"issues":[]}', finish="stop"):
    return httpx.Response(
        200,
        json={
            "id": "synthetic-generation",
            "model": "synthetic-actual-model",
            "provider": "Synthetic provider",
            "usage": {
                "cost": cost,
                "prompt_tokens": 240,
                "completion_tokens": 1400,
                "completion_tokens_details": {"reasoning_tokens": 1200},
            },
            "choices": [{"finish_reason": finish, "message": {"content": content}}],
        },
    )


def test_defaults_and_legacy_resolution_are_independent():
    defaults = Settings()
    assert [getattr(defaults.models, role).model for role in MODEL_ROLES] == [FLASH, FLASH, REVIEW]
    assert [getattr(defaults.models, role).reasoning_effort for role in MODEL_ROLES] == ["low", "low", "high"]
    legacy = {"model": "anthropic/claude-sonnet-4.6", "model_budget": 3}
    migrated = Settings.model_validate(legacy)
    assert legacy == {"model": "anthropic/claude-sonnet-4.6", "model_budget": 3}
    assert all(value["reasoning_effort"] is None for value in migrated.models.model_dump().values())
    migrated.models.extraction.model = FLASH
    assert migrated.models.research.model == legacy["model"]
    with pytest.raises(ValidationError):
        Settings.model_validate({"model": FLASH, "models": defaults.models.model_dump()})


def test_compatibility_uses_zdr_endpoints_and_reasoning(catalogue):
    assert "zero-data-retention" in catalogue.eligible("qwen/qwen3.7-flash", "extraction")[1]
    assert catalogue.eligible("fixture/json-only", "extraction", "low")[0]
    # Model-level metadata advertises structured output; its sole ZDR endpoint does not.
    assert not catalogue.eligible("fixture/json-only", "research")[0]
    assert not catalogue.eligible("fixture/json-only", "review")[0]
    assert not catalogue.eligible(FLASH, "extraction", "none")[0]
    endpoint = catalogue.endpoints[FLASH][0]
    endpoint["max_completion_tokens"] = 4096
    assert catalogue.eligible(FLASH, "extraction")[0]
    assert not catalogue.eligible(FLASH, "research")[0]
    endpoint["status"] = 1
    assert not catalogue.eligible(FLASH, "extraction")[0]


def test_context_tiers_cache_and_reasoning_prices_are_reserved(catalogue):
    pricing = {
        "prompt": "0.000001",
        "completion": "0.000002",
        "overrides": [
            {
                "min_prompt_tokens": 10000,
                "prompt": "0.000002",
                "completion": "0.000004",
                "input_cache_write": "0.000003",
                "internal_reasoning": "0.000005",
            },
            {"min_prompt_tokens": 200000, "prompt": "0.1", "completion": "0.2"},
        ],
    }
    assert price_bounds(pricing, 5000) == (0.000001, 0.000002, 0.000001, 0.000002)
    assert price_bounds(pricing, 12000) == (0.000002, 0.000004, 0.000003, 0.000005)
    catalogue.endpoints[FLASH][0]["pricing"] = pricing
    route = catalogue.route(RoleModel(model=FLASH, reasoning_effort="low"), "research", 12000)
    assert route["reservation"] == pytest.approx(12000 * 0.000003 + 8192 * 0.000005)
    assert not catalogue.eligible(FLASH, "review", "high", input_bound=300000)[0]


@pytest.mark.parametrize(
    "pricing",
    [
        {"prompt": "nan", "completion": "0"},
        {"prompt": "-1", "completion": "0"},
        {"prompt": "0", "completion": "inf"},
        {"prompt": "0", "completion": "0", "request": "1"},
    ],
)
def test_unbounded_or_unaccounted_prices_disable_endpoint(catalogue, pricing):
    catalogue.endpoints[FLASH][0]["pricing"] = pricing
    assert not catalogue.eligible(FLASH, "extraction")[0]


async def test_calls_route_roles_enforce_limits_and_record_provider_usage(
    tmp_path, secrets, catalogue, monkeypatch
):
    model, store = model_client(tmp_path, secrets, catalogue)
    requests = []

    def handler(request):
        requests.append((json.loads(request.content), request.extensions["timeout"]["read"]))
        return completion()

    mock_transport(monkeypatch, handler)
    for role in MODEL_ROLES:
        result = await model.structured("test", Verification, "Check evidence.", {}, role=role)
        assert result._call_id and "_call_id" not in result.model_dump()
    for (body, timeout), role in zip(requests, MODEL_ROLES):
        assert body["model"] == getattr(Settings().models, role).model
        assert body["reasoning"] == {"effort": "high" if role == "review" else "low", "exclude": True}
        assert body["max_tokens"] == OUTPUT_LIMITS[role]
        assert timeout == (600 if role == "review" else 300)
        assert body["provider"]["zdr"] and body["provider"]["require_parameters"]
        assert body["provider"]["only"]
        assert body["provider"]["max_price"] == {"prompt": 0.1, "completion": 0.5}
        assert body["response_format"]["json_schema"]["strict"]
    assert store.costs("test")["model_usd"] == 0.06
    for call in store.all("model_call"):
        assert call["provider"] == "Synthetic provider"
        assert call["usage"]["reasoning_tokens"] == 1200
        assert call["usage"]["completion_tokens"] == 1400  # already includes reasoning, no double charge
        assert call["verdict"] == {"supported": True, "issues": []}
        assert store.costs("test")["by_role"][call["role"]]["model_usd"] == 0.02


async def test_json_extraction_is_locally_validated_and_review_cannot_downgrade(
    tmp_path, secrets, catalogue, monkeypatch
):
    model, store = model_client(tmp_path, secrets, catalogue)
    settings = Settings()
    settings.models.extraction.model = "fixture/json-only"
    store.patch("run", "test", settings=settings.model_dump())
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return completion(content='{"unsupported_field":true}')

    mock_transport(monkeypatch, handler)
    with pytest.raises(StructuredOutputError):
        await model.structured("test", Verification, "Extract.", {}, role="extraction")
    assert requests[0]["response_format"] == {"type": "json_object"}
    assert store.all("model_call")[0]["status"] == "invalid_output"
    settings.models.review.model = "fixture/json-only"
    store.patch("run", "test", settings=settings.model_dump())
    with pytest.raises(ServiceError, match="No available ZDR"):
        await model.structured("test", Verification, "Review.", {}, role="review")
    assert len(requests) == 1


async def test_reasoning_exhaustion_is_charged_and_withheld(tmp_path, secrets, catalogue, monkeypatch):
    model, store = model_client(tmp_path, secrets, catalogue)
    mock_transport(monkeypatch, lambda request: completion(finish="length"))
    with pytest.raises(StructuredOutputError, match="including reasoning"):
        await model.structured("test", Verification, "Review.", {}, role="review")
    assert store.costs("test")["model_usd"] == 0.02
    assert store.all("model_call")[0]["verdict"] is None


async def test_price_refresh_changes_next_reservation_and_fails_closed(
    tmp_path, secrets, catalogue, monkeypatch
):
    model, store = model_client(tmp_path, secrets, catalogue)
    data = {
        "models": list(catalogue.items.values()),
        "endpoints": [e for group in catalogue.endpoints.values() for e in group],
    }
    requests = []
    fail_refresh = False

    def handler(request):
        if request.method == "GET":
            if fail_refresh:
                return httpx.Response(503)
            return httpx.Response(
                200, json={"data": data["models" if request.url.path.endswith("/models") else "endpoints"]}
            )
        requests.append(json.loads(request.content))
        return completion()

    mock_transport(monkeypatch, handler)
    await model.structured("test", Verification, "Review.", {}, role="review")
    initial = store.all("model_call")[0]["reserved_usd"]
    data["endpoints"][1]["pricing"] = {"prompt": "0.000002", "completion": "0.000005"}
    await model.prepare(Settings())
    await model.structured("test", Verification, "Review.", {}, role="review")
    assert store.all("model_call")[0]["reserved_usd"] > initial
    assert requests[-1]["provider"]["max_price"] == {"prompt": 2, "completion": 5}
    fail_refresh = True
    with pytest.raises(ServiceError, match="Could not refresh"):
        await model.prepare(Settings())
    assert len(requests) == 2


async def test_shared_budget_charges_all_roles_repairs_and_chat_before_sending(
    tmp_path, secrets, catalogue, monkeypatch
):
    model, store = model_client(tmp_path, secrets, catalogue)
    # A synthetic $5/M output endpoint reserves materially more than each settled call.
    for endpoints in catalogue.endpoints.values():
        endpoints[0]["pricing"]["completion"] = "0.000005"
    requests = []

    def handler(request):
        requests.append(request)
        return completion(cost=0.05)

    mock_transport(monkeypatch, handler)
    settings = Settings(model_budget=0.3)
    store.patch("run", "test", settings=settings.model_dump())
    for role in ["extraction", "research", "review", "research", "research"]:
        await model.structured("test", Verification, "Synthetic assessment, repair or chat.", {}, role=role)
    with pytest.raises(BudgetExceeded):
        await model.structured("test", Verification, "Chat review.", {}, role="review")
    assert len(requests) == 5
    assert store.costs("test")["model_usd"] == 0.25
    assert sum(value["model_usd"] for value in store.costs("test")["by_role"].values()) == 0.25


async def test_cancelled_request_retains_reservation_and_legacy_run_choices(
    tmp_path, secrets, catalogue, monkeypatch
):
    model, store = model_client(tmp_path, secrets, catalogue)
    legacy = {"model": "anthropic/claude-sonnet-4.6", "model_budget": 5}
    store.patch("run", "test", settings=legacy)
    sent = []

    async def handler(request):
        sent.append(json.loads(request.content))
        raise asyncio.CancelledError

    mock_transport(monkeypatch, handler)
    with pytest.raises(asyncio.CancelledError):
        await model.structured("test", Verification, "Review.", {}, role="review")
    assert sent[0]["model"] == legacy["model"] and "reasoning" not in sent[0]
    assert store.get("run", "test")["settings"] == legacy
    call = store.all("model_call")[0]
    assert call["actual_usd"] is None and call["status"] == "cancelled"
    assert store.costs("test")["model_usd"] > 0 and store.costs("test")["has_estimates"]


def test_settings_snapshot_api_usage_and_exports(client, app, demo, catalogue, monkeypatch):
    model = app.state.research.model
    model.catalogue = catalogue
    refreshes = []

    async def refresh(force=False):
        refreshes.append(force)

    monkeypatch.setattr(catalogue, "refresh", refresh)
    store = app.state.store
    legacy = {"model": "anthropic/claude-sonnet-4.6", "model_budget": 5}
    store.patch("run", demo["run_id"], settings=deepcopy(legacy))
    normalized = client.get(f"/api/runs/{demo['run_id']}").json()
    assert all(config["model"] == legacy["model"] for config in normalized["settings"]["models"].values())
    assert store.get("run", demo["run_id"])["settings"] == legacy
    settings = Settings().model_dump()
    settings["models"]["extraction"]["model"] = "fixture/json-only"
    assert client.put("/api/settings", json=settings).status_code == 200
    assert refreshes == [True]
    assert client.get("/api/bootstrap").json()["settings"] == settings
    assert store.get("run", demo["run_id"])["settings"] == legacy
    settings["models"]["review"]["model"] = "qwen/qwen3.7-flash"
    assert client.put("/api/settings", json=settings).status_code == 422
    assert client.get("/api/models?refresh=true").json()["fetched_at"]
    charge = store.reserve(
        demo["run_id"],
        "OpenRouter",
        0.2,
        5,
        metadata={
            "role": "review",
            "model": legacy["model"],
            "reasoning_effort": None,
            "purpose": "Verification",
        },
    )
    store.settle(
        charge,
        0.07,
        provider="Synthetic provider",
        usage={"reasoning_tokens": 200},
        verdict={"supported": True, "issues": []},
    )
    calls = client.get(f"/api/runs/{demo['run_id']}/model-calls").json()
    assert calls[0]["provider"] == "Synthetic provider"
    for suffix in ("", "?format=csv"):
        exported = client.get(f"/api/accounts/{demo['id']}/export{suffix}").text
        assert (
            legacy["model"] in exported
            and "Synthetic provider" in exported
            and "reasoning_tokens" in exported
        )
    assert "model_call" in client.get("/api/export").text
    assert (
        client.get("/api/export").json()["run_costs"][demo["run_id"]]["by_role"]["review"]["model_usd"]
        == 0.07
    )
