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
        return {
            name: {"configured": bool(self.get(name)), "environment": False}
            for name in ["openrouter", "tavily"]
        }


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
