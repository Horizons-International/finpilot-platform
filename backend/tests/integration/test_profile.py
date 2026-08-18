from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def authenticate_client(client: TestClient, user) -> None:
    response = client.post(
        "/api/v1/auth/login",
        json={
            "email": user.email,
            "password": "Password123!",
        },
    )

    assert response.status_code == 200

    access_token = response.json()["data"]["access_token"]

    client.headers.update({"Authorization": f"Bearer {access_token}"})


def test_user_can_get_own_profile(client, create_test_user):
    _, user = create_test_user(
        role="Reviewer",
        email="profile-get@example.com",
    )

    authenticate_client(client, user)

    response = client.get("/api/v1/profile")

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["id"] == str(user.id)
    assert data["first_name"] == "Test"
    assert data["last_name"] == "User"
    assert data["email"] == user.email
    assert data["role"] == "Reviewer"


def test_user_can_update_own_profile(client, create_test_user):
    _, user = create_test_user(
        role="Reviewer",
        email="profile-update@example.com",
    )

    authenticate_client(client, user)

    response = client.put(
        "/api/v1/profile",
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


def test_unauthenticated_user_cannot_get_profile(client):
    response = client.get("/api/v1/profile")

    assert response.status_code == 401


def test_user_cannot_change_role(client, create_test_user):
    db, user = create_test_user(
        role="Reviewer",
        email="profile-role@example.com",
    )

    original_role = user.role

    authenticate_client(client, user)

    response = client.put(
        "/api/v1/profile",
        json={
            "first_name": "Updated",
            "last_name": "User",
            "phone_number": "+249123456789",
            "role": "Administrator",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    # The profile endpoint should ignore the role field.
    assert data["role"] == original_role

    db.refresh(user)

    assert user.role == original_role
