from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app
from app.models.user import User

client = TestClient(app)


def test_create_user(client, create_test_user):
    db, admin = create_test_user(
        role="Administrator",
        email="admin-user-test@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(admin.id),
                "email": admin.email,
                "role": admin.role,
            }
        )

        response = client.post(
            "/api/v1/users",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "first_name": "New",
                "last_name": "User",
                "email": "new-user-test@example.com",
                "password": "Password123!",
                "role": "Reviewer",
            },
        )

        assert response.status_code == 201

        data = response.json()

        assert data["first_name"] == "New"
        assert data["last_name"] == "User"
        assert data["email"] == "new-user-test@example.com"
        assert data["role"] == "Reviewer"

    finally:
        created_user = (
            db.query(User).filter(User.email == "new-user-test@example.com").first()
        )

        if created_user:
            db.delete(created_user)

        db.delete(admin)
        db.commit()
        db.close()


def test_get_user(client, create_test_user):
    db, admin = create_test_user(
        role="Administrator",
        email="admin-get-user@example.com",
    )

    db2, target_user = create_test_user(
        role="Reviewer",
        email="target-get-user@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(admin.id),
                "email": admin.email,
                "role": admin.role,
            }
        )

        response = client.get(
            f"/api/v1/users/{target_user.id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert data["id"] == str(target_user.id)
        assert data["email"] == target_user.email
        assert data["role"] == "Reviewer"

    finally:
        db.delete(admin)
        db.commit()
        db.close()

        db2.delete(target_user)
        db2.commit()
        db2.close()


def test_get_all_users(client, create_test_user):
    db, admin = create_test_user(
        role="Administrator",
        email="admin-list-users@example.com",
    )

    db2, target_user = create_test_user(
        role="Reviewer",
        email="target-list-users@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(admin.id),
                "email": admin.email,
                "role": admin.role,
            }
        )

        response = client.get(
            "/api/v1/users",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert "users" in data
        assert "total" in data
        assert "page" in data
        assert "page_size" in data
        assert "total_pages" in data

    finally:
        db.delete(admin)
        db.commit()
        db.close()

        db2.delete(target_user)
        db2.commit()
        db2.close()


def test_update_user(client, create_test_user):
    db, admin = create_test_user(
        role="Administrator",
        email="admin-update-user@example.com",
    )

    db2, target_user = create_test_user(
        role="Reviewer",
        email="target-update-user@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(admin.id),
                "email": admin.email,
                "role": admin.role,
            }
        )

        response = client.put(
            f"/api/v1/users/{target_user.id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "first_name": "Updated",
                "last_name": "Name",
                "email": target_user.email,
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert data["first_name"] == "Updated"
        assert data["last_name"] == "Name"

    finally:
        db.delete(admin)
        db.commit()
        db.close()

        db2.delete(target_user)
        db2.commit()
        db2.close()


def test_deactivate_user(client, create_test_user):
    db, admin = create_test_user(
        role="Administrator",
        email="admin-deactivate@example.com",
    )

    db2, target_user = create_test_user(
        role="Reviewer",
        email="target-deactivate@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(admin.id),
                "email": admin.email,
                "role": admin.role,
            }
        )

        response = client.patch(
            f"/api/v1/users/{target_user.id}/status",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "status": "inactive",
            },
        )

        assert response.status_code == 200

        data = response.json()

        assert data["status"] == "inactive"

    finally:
        db.delete(admin)
        db.commit()
        db.close()

        db2.delete(target_user)
        db2.commit()
        db2.close()


def test_delete_user(client, create_test_user):
    db, admin = create_test_user(
        role="Administrator",
        email="admin-delete-user@example.com",
    )

    db2, target_user = create_test_user(
        role="Reviewer",
        email="target-delete-user@example.com",
    )

    target_user_id = target_user.id

    try:
        token = create_access_token(
            data={
                "sub": str(admin.id),
                "email": admin.email,
                "role": admin.role,
            }
        )

        response = client.delete(
            f"/api/v1/users/{target_user_id}",
            headers={
                "Authorization": f"Bearer {token}",
            },
        )

        assert response.status_code in (200, 204)

    finally:
        db.delete(admin)
        db.commit()
        db.close()

        db2.delete(target_user)
        db2.commit()
        db2.close()
