import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.adapters.infrastructure.routers.github_webhook import (
    create_github_webhook_router,
    verify_github_signature,
)

SECRET = "test-secret"


def signed_headers(body: bytes, delivery: str = "delivery-1") -> dict[str, str]:
    signature = hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    return {
        "X-Hub-Signature-256": f"sha256={signature}",
        "X-GitHub-Event": "workflow_run",
        "X-GitHub-Delivery": delivery,
        "Content-Type": "application/json",
    }


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("GITHUB_WEBHOOK_SECRET", SECRET)
    app = FastAPI()
    app.include_router(create_github_webhook_router())
    return TestClient(app)


def test_verify_signature_accepts_valid_hmac():
    body = b'{"action":"completed"}'
    signature = "sha256=" + hmac.new(SECRET.encode(), body, hashlib.sha256).hexdigest()
    assert verify_github_signature(SECRET, body, signature)


def test_verify_signature_rejects_wrong_signature():
    assert not verify_github_signature(SECRET, b"{}", "sha256=" + "0" * 64)


def test_missing_secret_returns_service_unavailable(monkeypatch):
    monkeypatch.delenv("GITHUB_WEBHOOK_SECRET", raising=False)
    app = FastAPI()
    app.include_router(create_github_webhook_router())
    response = TestClient(app).post(
        "/v1/github/webhook",
        content=b"{}",
        headers={"X-GitHub-Event": "push", "X-GitHub-Delivery": "x"},
    )
    assert response.status_code == 503


def test_missing_required_headers_returns_400(client):
    assert client.post("/v1/github/webhook", content=b"{}").status_code == 400


def test_invalid_signature_returns_401(client):
    response = client.post(
        "/v1/github/webhook",
        content=b"{}",
        headers={
            "X-Hub-Signature-256": "sha256=" + "0" * 64,
            "X-GitHub-Event": "push",
            "X-GitHub-Delivery": "bad-signature",
        },
    )
    assert response.status_code == 401


def test_valid_delivery_is_accepted_and_duplicate_is_idempotent(client):
    body = json.dumps({"action": "completed"}).encode()
    headers = signed_headers(body)
    first = client.post("/v1/github/webhook", content=body, headers=headers)
    second = client.post("/v1/github/webhook", content=body, headers=headers)
    assert first.status_code == 200
    assert first.json()["ok"] is True
    assert second.status_code == 200
    assert second.json()["duplicate"] is True


def test_invalid_json_returns_400(client):
    body = b"{"
    response = client.post(
        "/v1/github/webhook", content=body, headers=signed_headers(body)
    )
    assert response.status_code == 400
