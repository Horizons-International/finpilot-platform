import os

import pytest

os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+psycopg://user:123789@localhost:5432/customers",
)
os.environ.setdefault("SECRET_KEY", "test-secret-key")
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserStatus


@pytest.fixture
def test_user():
    db = SessionLocal()

    user = User(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
        role="user",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    yield user

    db.delete(user)
    db.commit()
    db.close()
