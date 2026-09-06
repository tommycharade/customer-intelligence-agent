import json

from fastapi.testclient import TestClient

from customer_intelligence.models import Source


def test_requires_local_authenticated_session(app):
    with TestClient(app, base_url="http://127.0.0.1:8765") as client:
        assert client.get("/api/bootstrap").status_code == 401
        assert client.get("/auth?token=incorrect").status_code == 403
        assert client.get("/health", headers={"Host": "hostile.example"}).status_code == 403
        client.get("/auth?token=local-test-token")
        assert client.post("/api/demo", headers={"Origin": "https://other.example"}).status_code == 403
        assert client.post("/api/demo").status_code == 403


def test_empty_workspace_and_setup_gate(client):
    assert client.get("/api/accounts").json() == []
    assert client.get("/api/bootstrap").json()["profile"] is None
    assert client.post("/api/runs", json={}).status_code == 422


def test_demo_is_explicit_idempotent_and_excluded_from_metrics(client, demo):
    assert demo["is_demo"]
    client.post("/api/demo")
    assert len(client.get("/api/accounts?demo=true").json()) == 3
    assert client.get("/api/accounts").json() == []
    assert client.get("/api/metrics").json() == []
    assert client.get("/api/runs?demo=true").json()[0]["costs"]["model_usd"] == 0


def test_demo_brief_chat_and_exports(client, demo):
    result = client.post(f"/api/accounts/{demo['id']}/chat", json={"message": "Why does it fit?"})
    assert result.status_code == 200
    assert "synthetic" in result.json()["answer"]
    markdown = client.get(f"/api/accounts/{demo['id']}/export").text
    for heading in ["Why this account fits", "Why now", "Who matters", "What could help", "Evidence"]:
        assert heading in markdown
    assert "Synthetic demonstration" in markdown
    assert "Hypothesis" in markdown
    assert (
        client.get(f"/api/accounts/{demo['id']}/export?format=csv")
        .headers["content-type"]
        .startswith("text/csv")
    )


def test_outcome_metric_counts_unique_live_accounts(client, demo, app):
    live = demo | {"id": "live-test-account", "is_demo": False}
    app.state.store.put("account", live["id"], live)
    for _ in range(2):
        response = client.put(
            "/api/accounts/live-test-account/outcome",
            json={
                "status": "relevant_conversation",
                "note": "Confirmed the workflow with the platform owner.",
            },
        )
        assert response.status_code == 200
    metrics = client.get("/api/metrics").json()[0]
    assert metrics["recommended"] == metrics["relevant"] == 1
    assert metrics["conversion"] == 1
    assert (
        client.put(
            "/api/accounts/live-test-account/outcome", json={"status": "rejected", "note": ""}
        ).status_code
        == 422
    )


def test_import_preview_does_not_save(client):
    response = client.post(
        "/api/imports/preview", files={"file": ("notes.txt", b"Customer reports repeated ownership checks.")}
    )
    assert response.status_code == 200
    assert client.get("/api/sources").json() == []
    draft = response.json()[0] | {"account_domain": "www.customer.com", "source_type": "interview"}
    result = client.post("/api/imports", json={"sources": [draft]}).json()
    assert result[0]["account_domain"] == "customer.com"
    client.post("/api/imports", json={"sources": [draft]})
    assert len(client.get("/api/sources").json()) == 1
    assert len(client.get("/api/sources?query=ownership").json()) == 1


def test_import_cannot_overwrite_demo_or_public_records(client, demo):
    draft = Source(
        id=demo["source_ids"][0],
        title="Imported",
        text="An independently supplied interview note.",
        is_demo=True,
        origin="public",
        url="https://example.com",
    ).model_dump()
    saved = client.post("/api/imports", json={"sources": [draft]}).json()[0]
    assert saved["id"] != draft["id"]
    assert saved["origin"] == "upload" and not saved["is_demo"] and saved["url"] is None


def test_invalid_batch_is_not_partially_saved(client):
    drafts = [
        Source(title="Valid", text="Valid text.").model_dump(),
        Source(title="Bad", text="").model_dump(),
    ]
    assert client.post("/api/imports", json={"sources": drafts}).status_code == 422
    assert client.get("/api/sources").json() == []


def test_delete_data_clears_evidence_history_but_preserves_settings(client, demo):
    settings = client.get("/api/bootstrap").json()["settings"]
    client.put("/api/settings", json=settings)
    assert client.delete("/api/data").status_code == 200
    assert client.get("/api/accounts?demo=true").json() == []
    assert client.get("/api/sources?demo=true").json() == []
    assert client.get("/api/bootstrap").json()["settings"] == settings


def test_secrets_not_returned_or_exported(client):
    key = "test-secret-must-not-be-exported"
    assert client.put("/api/credentials/openrouter", json={"value": key}).status_code == 200
    assert key not in client.get("/api/bootstrap").text
    assert key not in client.get("/api/export").text


def test_finished_sse_has_resumable_run_state(client, demo):
    response = client.get("/api/runs/demo-research/events")
    data = json.loads(response.text.split("data: ")[1].split("\n\n")[0])
    assert data["run"]["status"] == "completed"
    assert len(data["run"]["account_ids"]) == 3
