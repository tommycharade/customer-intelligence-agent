import json
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from customer_intelligence.main import create_app


class FakeSecrets:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def set(self, name, value):
        self.values[name] = value

    def status(self):
        return {name: {"configured": bool(self.get(name)), "environment": False} for name in ["openrouter"]}


@pytest.fixture
def secrets():
    return FakeSecrets()


@pytest.fixture
def app(tmp_path: Path, secrets):
    return create_app(tmp_path, auth_token="local-test-token", secret_store=secrets)


@pytest.fixture
def client(app):
    with TestClient(
        app, base_url="http://127.0.0.1:8765", headers={"Origin": "http://127.0.0.1:8765"}
    ) as client:
        client.get("/auth?token=local-test-token")
        yield client


@pytest.fixture
def demo(client):
    client.post("/api/demo")
    return client.get("/api/accounts?demo=true").json()[0]


@pytest.fixture
def catalogue():
    from customer_intelligence.models import now
    from customer_intelligence.routing import ModelCatalogue

    data = json.loads((Path(__file__).parent / "fixtures/model_catalogue.json").read_text())
    result = ModelCatalogue()
    result.items = {item["id"]: item for item in data["models"]}
    for endpoint in data["endpoints"]:
        result.endpoints.setdefault(endpoint["model_id"], []).append(endpoint)
    result.fetched_at, result.loaded_at = now(), time.monotonic()
    return result
