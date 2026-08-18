from app.core.security import create_access_token
from app.models.audit_log import AuditLog
from app.models.user import UserRole
from tests.conftest import TestSessionLocal


def test_login_with_valid_credentials(client, create_test_user):
    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email="test-login@example.com",
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_login_with_invalid_password(client, create_test_user):
    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email="test-invalid-password@example.com",
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "WrongPassword!",
        },
    )

    assert response.status_code == 401


def test_refresh_token(client, create_test_user):
    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email="test-refresh@example.com",
    )

    login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert login_response.status_code == 200

    refresh_token = login_response.json()["data"]["refresh_token"]

    response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": refresh_token,
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert "access_token" in data
    assert data["token_type"] == "bearer"
    assert data["access_token"]


def test_refresh_with_invalid_token(client):
    response = client.post(
        "/api/v1/auth/refresh",
        json={
            "refresh_token": "this-is-an-invalid-refresh-token",
        },
    )

    assert response.status_code == 401


def test_login_with_nonexistent_user(client):
    email = "doesnotexist@example.com"

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 401

    db = TestSessionLocal()

    try:
        db.query(AuditLog).filter(AuditLog.email == email).delete(
            synchronize_session=False
        )

        db.commit()
    finally:
        db.close()


def test_login_rejects_invalid_email(client):
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": "not-an-email",
            "password": "Password123!",
        },
    )

    assert response.status_code == 422

    data = response.json()

    assert data["success"] is False
    assert data["message"] == "Validation failed."
    assert data["errors"]


def test_login_rejects_missing_password(client, create_test_user):
    _, user = create_test_user(
        role=UserRole.AUDITOR,
        email="test-missing-password@example.com",
    )

    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
        },
    )

    assert response.status_code == 422

    data = response.json()

    assert data["success"] is False
    assert data["errors"]


def test_invalid_user_status(client, create_test_user):
    _, admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email="admin-invalid-status@example.com",
    )

    token = create_access_token(
        data={
            "sub": str(admin.id),
            "email": admin.email,
            "role": admin.role,
        }
    )

    response = client.patch(
        "/api/v1/users/00000000-0000-0000-0000-000000000000/status",
        headers={
            "Authorization": f"Bearer {token}",
        },
        json={
            "status": "INVALID_STATUS",
        },
    )

    assert response.status_code == 422

    data = response.json()

    assert data["success"] is False
    assert data["message"] == "Validation failed."
    assert data["errors"]
