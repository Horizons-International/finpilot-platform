from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


def test_administrator_can_access_admin_endpoint(client, create_test_user):
    _, user = create_test_user(
        role="Administrator",
        email="admin-rbac@example.com",
    )

    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )

    response = client.get(
        "/api/v1/auth/admin-only",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 200


def test_reviewer_cannot_access_admin_endpoint(client, create_test_user):
    _, user = create_test_user(
        role="Reviewer",
        email="reviewer-rbac@example.com",
    )

    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )

    response = client.get(
        "/api/v1/auth/admin-only",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403


def test_compliance_officer_cannot_access_admin_endpoint(
    client,
    create_test_user,
):
    _, user = create_test_user(
        role="Compliance Officer",
        email="compliance-rbac@example.com",
    )

    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )

    response = client.get(
        "/api/v1/auth/admin-only",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403


def test_auditor_cannot_access_admin_endpoint(client, create_test_user):
    _, user = create_test_user(
        role="Auditor",
        email="auditor-rbac@example.com",
    )

    token = create_access_token(
        data={
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }
    )

    response = client.get(
        "/api/v1/auth/admin-only",
        headers={
            "Authorization": f"Bearer {token}",
        },
    )

    assert response.status_code == 403
