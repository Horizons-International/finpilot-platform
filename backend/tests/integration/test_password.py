from fastapi.testclient import TestClient

from app.core.security import create_access_token
from app.main import app

client = TestClient(app)


def test_change_password_success(create_test_user):
    db, user = create_test_user(
        role="Reviewer",
        email="password-change@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
            }
        )

        response = client.post(
            "/api/v1/auth/change-password",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "current_password": "Password123!",
                "new_password": "NewPassword123!",
            },
        )

        assert response.status_code == 200

    finally:
        db.delete(user)
        db.commit()
        db.close()


def test_change_password_invalid_current_password(create_test_user):
    db, user = create_test_user(
        role="Reviewer",
        email="password-invalid-current@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
            }
        )

        response = client.post(
            "/api/v1/auth/change-password",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "current_password": "WrongPassword123!",
                "new_password": "NewPassword123!",
            },
        )

        assert response.status_code == 400

    finally:
        db.delete(user)
        db.commit()
        db.close()


def test_change_password_rejects_weak_password(create_test_user):
    db, user = create_test_user(
        role="Reviewer",
        email="password-weak@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
            }
        )

        response = client.post(
            "/api/v1/auth/change-password",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "current_password": "Password123!",
                "new_password": "weak",
            },
        )

        assert response.status_code == 400

    finally:
        db.delete(user)
        db.commit()
        db.close()


def test_change_password_rejects_same_password(create_test_user):
    db, user = create_test_user(
        role="Reviewer",
        email="password-same@example.com",
    )

    try:
        token = create_access_token(
            data={
                "sub": str(user.id),
                "email": user.email,
                "role": user.role,
            }
        )

        response = client.post(
            "/api/v1/auth/change-password",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "current_password": "Password123!",
                "new_password": "Password123!",
            },
        )

        assert response.status_code == 400

    finally:
        db.delete(user)
        db.commit()
        db.close()
