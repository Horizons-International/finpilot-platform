from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


def test_user_can_get_own_profile(client, create_test_user):
    db, user = create_test_user(
        role="Reviewer",
        email="profile-get@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
            }
        )

        response = client.get(
            "/api/v1/profile",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 200

        data = response.json()["data"]

        assert data["id"] == str(user.id)
        assert data["first_name"] == "Test"
        assert data["last_name"] == "User"
        assert data["email"] == user.email
        assert data["role"] == "Reviewer"

    finally:
        db.delete(user)
        db.commit()
        db.close()


def test_user_can_update_own_profile(client, create_test_user):
    db, user = create_test_user(
        role="Reviewer",
        email="profile-update@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
            }
        )

        response = client.put(
            "/api/v1/profile",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "first_name": "Updated",
                "last_name": "Profile",
                "phone_number": "+249123456789",
            },
        )

        assert response.status_code == 200

        data = response.json()["data"]

        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Profile"
        assert data["phone_number"] == "+249123456789"
        assert data["role"] == "Reviewer"

    finally:
        db.delete(user)
        db.commit()
        db.close()


def test_unauthenticated_user_cannot_get_profile(client):
    response = client.get("/api/v1/profile")

    assert response.status_code == 401


def test_user_cannot_change_role(client, create_test_user):
    db, user = create_test_user(
        role="Reviewer",
        email="profile-role@example.com",
    )

    original_role = user.role

    try:
        token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
            }
        )

        response = client.put(
            "/api/v1/profile",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "first_name": "Updated",
                "last_name": "User",
                "phone_number": "+249123456789",
                "role": "Administrator",
            },
        )

        assert response.status_code == 200

        data = response.json()["data"]

        assert data["role"] == original_role

        db.refresh(user)
        assert user.role == original_role

    finally:
        db.delete(user)
        db.commit()
        db.close()
