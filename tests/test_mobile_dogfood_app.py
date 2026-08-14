from fastapi.testclient import TestClient

from app.core.config import settings
from app.mobile_dogfood import app


def test_mobile_dogfood_surface_exposes_health_and_authenticated_mobile_apis(
    monkeypatch,
):
    monkeypatch.setattr(settings, "mobile_dogfood_token", "local-test-token")
    client = TestClient(app)

    assert client.get("/health").status_code == 200
    assert client.get("/api/v1/today").status_code == 401
    assert client.get("/api/v2/me").status_code == 401
    assert client.get("/api/message").status_code == 404
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
