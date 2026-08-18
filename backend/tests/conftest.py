import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.audit_log import AuditLog
from app.models.file import File
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

        created_users.append((db, user))

        return db, user

    yield _create_test_user

    for db, user in created_users:
        db.query(AuditLog).filter(AuditLog.user_id == user.id).delete(
            synchronize_session=False
        )

        db.delete(user)
        db.commit()
        db.close()


@pytest.fixture
def cleanup_test_files():
    created_files = []

    def _track_file(file_id):
        created_files.append(file_id)

    yield _track_file

    db = TestSessionLocal()

    try:
        for file_id in created_files:
            file_record = db.query(File).filter(File.id == file_id).first()

            if file_record:
                db.delete(file_record)

        db.commit()
    finally:
        db.close()
