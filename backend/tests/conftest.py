import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.audit_log import AuditLog
from app.models.user import User, UserStatus

os.environ.setdefault(
    "TEST_DATABASE_URL",
    "postgresql+psycopg://user:123789@localhost:5432/testdb",
)

test_database_url = os.environ["TEST_DATABASE_URL"]

test_engine = create_engine(test_database_url)

TestSessionLocal = sessionmaker(
    bind=test_engine,
    autoflush=False,
    autocommit=False,
)


@pytest.fixture
def client():
    def override_get_db():
        db = TestSessionLocal()

        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture
def test_user():
    db = TestSessionLocal()

    user = User(
        first_name="Test",
        last_name="User",
        email="test@example.com",
        password_hash=hash_password("Password123!"),
        status=UserStatus.ACTIVE,
        role="Administrator",
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    yield user

    db.query(AuditLog).filter(AuditLog.user_id == user.id).delete(
        synchronize_session=False
    )

    db.delete(user)
    db.commit()
    db.close()


@pytest.fixture
def create_test_user():
    created_users = []

    def _create_test_user(role: str, email: str):
        db = TestSessionLocal()

        user = User(
            first_name="Test",
            last_name="User",
            email=email,
            password_hash=hash_password("Password123!"),
            status=UserStatus.ACTIVE,
            role=role,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        return db, user

    yield _create_test_user

    for db, user in created_users:
        db.query(AuditLog).filter(AuditLog.user_id == user.id).delete(
            synchronize_session=False
        )

        db.delete(user)
        db.commit()
        db.close()
