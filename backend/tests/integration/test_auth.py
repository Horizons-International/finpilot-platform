from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_login_with_valid_credentials(test_user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_with_invalid_password(test_user):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "WrongPassword!",
        },
    )

    assert response.status_code == 401


def test_refresh_token(test_user):
    # First, log in to get a refresh token
    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "test@example.com",
            "password": "Password123!",
        },
    )

    assert login_response.status_code == 200

    refresh_token = login_response.json()["refresh_token"]

    # Use the refresh token to get a new access token
    response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": refresh_token,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_refresh_with_invalid_token():
    response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": "this-is-an-invalid-refresh-token",
        },
    )

    assert response.status_code == 401


def test_login_with_nonexistent_user():
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "doesnotexist@example.com",
            "password": "Password123!",
        },
    )

    assert response.status_code == 401
