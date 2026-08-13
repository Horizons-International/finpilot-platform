from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["message"] == "Service is healthy."
    assert data["data"]["status"] == "healthy"
    assert data["errors"] is None
