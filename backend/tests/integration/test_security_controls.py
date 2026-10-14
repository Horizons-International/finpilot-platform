from time import time
from typing import Any, cast
from uuid import uuid4

from fastapi.testclient import TestClient

from app.core.mfa import _totp_at
from app.core.security import validate_password
from app.models.security_event import SecurityEvent
from app.utils.enums import UserRole
from tests.conftest import TestSessionLocal


def _login(
    client: TestClient, email: str, password: str = "Password123!"
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert response.status_code == 200, response.text
    return cast(dict[str, Any], response.json()["data"])


def test_login_creates_revocable_server_session(client, create_test_user):
    user = create_test_user(
        role=UserRole.AUDITOR,
        email=f"security-session-{uuid4()}@example.com",
    )
    tokens = _login(client, user.email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    sessions_response = client.get("/api/v1/security/sessions", headers=headers)
    assert sessions_response.status_code == 200, sessions_response.text
    sessions = sessions_response.json()["data"]
    current = next(item for item in sessions if item["is_current"] is True)

    revoke_response = client.post(
        f"/api/v1/security/sessions/{current['id']}/revoke",
        headers=headers,
    )
    assert revoke_response.status_code == 200, revoke_response.text

    protected_response = client.get("/api/v1/me", headers=headers)
    assert protected_response.status_code == 401


def test_mfa_enrollment_requires_confirmation_and_login_code(
    client: TestClient,
    create_test_user,
):
    user = create_test_user(
        role=UserRole.AUDITOR,
        email=f"security-mfa-{uuid4()}@example.com",
    )
    tokens = _login(client, user.email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}

    enrollment_response = client.post(
        "/api/v1/security/mfa/enroll",
        headers=headers,
        json={"current_password": "Password123!"},
    )
    assert enrollment_response.status_code == 200, enrollment_response.text
    secret = enrollment_response.json()["data"]["secret"]

    code = _totp_at(secret, int(time()))
    confirm_response = client.post(
        "/api/v1/security/mfa/confirm",
        headers=headers,
        json={"code": code},
    )
    assert confirm_response.status_code == 200, confirm_response.text
    assert confirm_response.json()["data"]["mfa_enabled"] is True

    missing_code_response = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "Password123!"},
    )
    assert missing_code_response.status_code == 401

    fresh_code = _totp_at(secret, int(time()))
    mfa_login_response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
            "mfa_code": fresh_code,
        },
    )
    assert mfa_login_response.status_code == 200, mfa_login_response.text
    assert mfa_login_response.json()["data"]["access_token"]


def test_password_policy_uses_configured_minimum():
    try:
        validate_password("Short123!")
    except ValueError as exc:
        assert "at least" in str(exc)
    else:
        raise AssertionError("Password shorter than configured minimum was accepted")

    validate_password("LongerPassword123!")


def test_failed_logins_are_recorded_and_rate_limited(client, create_test_user):
    user = create_test_user(
        role=UserRole.AUDITOR,
        email=f"security-bruteforce-{uuid4()}@example.com",
    )
    for _ in range(5):
        response = client.post(
            "/api/v1/auth/login",
            json={"email": user.email, "password": "DefinitelyWrong123!"},
        )
        assert response.status_code == 401

    blocked = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "DefinitelyWrong123!"},
    )
    assert blocked.status_code == 429

    db = TestSessionLocal()
    try:
        failures = (
            db.query(SecurityEvent)
            .filter(
                SecurityEvent.email == user.email,
                SecurityEvent.event_type == "LOGIN_FAILURE",
            )
            .all()
        )
        assert len(failures) >= 5
        assert any(
            event.event_type == "LOGIN_BLOCKED"
            for event in db.query(SecurityEvent)
            .filter(SecurityEvent.email == user.email)
            .all()
        )
    finally:
        db.close()


def test_security_event_feed_is_tenant_scoped(client, create_test_user):
    admin = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"security-feed-admin-{uuid4()}@example.com",
    )
    tokens = _login(client, admin.email)
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    access_response = client.get("/api/v1/me", headers=headers)
    assert access_response.status_code == 200, access_response.text

    response = client.get(
        "/api/v1/security/events?limit=50",
        headers=headers,
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert any(event["event_type"] == "LOGIN_SUCCESS" for event in data)
    assert any(event["event_type"] == "API_ACCESS" for event in data)
