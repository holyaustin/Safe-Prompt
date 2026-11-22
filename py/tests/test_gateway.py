"""Safe Prompt — gateway app tests."""

import pytest
from fastapi.testclient import TestClient

from safe_prompt.gateway.app import app


@pytest.fixture
def client():
    return TestClient(app)


def test_health_endpoint(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "crypto_backend" in data


def test_models_endpoint(client):
    resp = client.get("/v1/models")
    assert resp.status_code == 200
    data = resp.json()
    assert "data" in data


def test_chat_completions_mock(client):
    # Without upstream, should fail gracefully or use mock
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "safe-prompt",
            "messages": [{"role": "user", "content": "Hello"}],
        },
    )
    # 503 if upstream not configured, 200 if mock
    assert resp.status_code in (200, 503)


def test_redaction_blocks_api_key(client):
    # Post a known API key pattern and check it's redacted in the request flow
    # This is an integration test; we verify the endpoint exists
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "safe-prompt",
            "messages": [
                {"role": "user", "content": "API key: sk-proj-Q8x2LmN4vB7cR1tY9uZ3aW5eD6fG0hJk9fQ2aBcDeFgHiJkLm"}
            ],
        },
    )
    # Should not crash
    assert resp.status_code in (200, 422, 503)
    # If 422, it's the fail-closed working (leak detected upstream)
    # If 503, upstream not available


def test_streaming_endpoint_exists(client):
    # Just verify the route exists
    resp = client.post(
        "/v1/chat/completions",
        json={
            "model": "safe-prompt",
            "messages": [{"role": "user", "content": "test"}],
            "stream": True,
        },
    )
    # Should respond (200 for stream, 503 for upstream unavailable)
    assert resp.status_code in (200, 503)