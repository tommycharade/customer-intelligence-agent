import json

import httpx
import pytest

from customer_intelligence.models import Settings, Verification
from customer_intelligence.providers import OpenRouter
from customer_intelligence.sources import PublicReader, SourceUnavailable
from customer_intelligence.store import BudgetExceeded, Store


def test_budget_reserves_before_call_and_retains_uncertain_cost(tmp_path):
    store = Store(tmp_path)
    charge = store.reserve("run", "OpenRouter", 3, 5)
    with pytest.raises(BudgetExceeded):
        store.reserve("run", "OpenRouter", 3, 5)
    store.settle(charge)
    assert store.costs("run")["model_usd"] == 3
    assert store.costs("run")["has_estimates"]
    store.settle(charge, 1)
    store.reserve("run", "OpenRouter", 4, 5)
    assert store.costs("run")["model_usd"] == 5


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://169.254.169.254",
        "http://10.0.0.1",
        "file:///etc/passwd",
        "https://user:password@example.com",
        "http://example.com:8080",
    ],
)
async def test_public_reader_rejects_nonpublic_or_credentialed_addresses(url):
    with pytest.raises(SourceUnavailable):
        await PublicReader(Settings()).address(url)


async def test_blocked_domain_policy_applies_to_subdomains():
    with pytest.raises(SourceUnavailable, match="blocked"):
        await PublicReader(Settings(blocked_domains=["example.com"])).address("https://docs.example.com")


async def test_model_enforces_privacy_schema_and_accounts_for_cost(tmp_path, secrets, monkeypatch):
    store = Store(tmp_path)
    store.put("run", "test", {"settings": Settings().model_dump()})
    secrets.values["openrouter"] = "test-key"
    model = OpenRouter(store, secrets)
    model.catalog = {
        "anthropic/claude-sonnet-4.6": {
            "supported_parameters": ["tools", "structured_outputs"],
            "pricing": {"prompt": "0.000003", "completion": "0.000015"},
        }
    }
    requests = []

    def handler(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200,
            json={
                "usage": {"cost": 0.02},
                "choices": [
                    {"finish_reason": "stop", "message": {"content": '{"supported":true,"issues":[]}'}}
                ],
            },
        )

    client_class = httpx.AsyncClient
    monkeypatch.setattr(
        "customer_intelligence.providers.httpx.AsyncClient",
        lambda **kwargs: client_class(transport=httpx.MockTransport(handler), **kwargs),
    )
    result = await model.structured("test", Verification, "Verify.", {"source": "an observation"})
    assert result.supported
    assert requests[0]["provider"]["zdr"] is True
    assert requests[0]["provider"]["require_parameters"] is True
    assert requests[0]["response_format"]["type"] == "json_schema"
    assert store.costs("test")["model_usd"] == 0.02
