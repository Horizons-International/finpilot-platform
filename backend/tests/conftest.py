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
    expire_on_commit=False,
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

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


@pytest.fixture
def create_test_user():
    created_user_ids = []

    def _create_test_user(role: str, email: str):
        db = TestSessionLocal()

        user = User(
            first_name="Test",
            last_name="User",
            email=email,
            password_hash=hash_password("Password123!"),
            status=UserStatus.ACTIVE,
            role=role,
            is_deleted=False,
        )

        db.add(user)
        db.commit()
        db.refresh(user)

        user_id = user.id

        created_user_ids.append((db, user_id))

        return db, user

    yield _create_test_user

    try:
        for db, user_id in created_user_ids:
            # Delete audit records first because they reference the user.
            db.query(AuditLog).filter(AuditLog.user_id == user_id).delete(
                synchronize_session=False
            )

            # Retrieve the current User from this session.
            user = db.query(User).filter(User.id == user_id).first()

            if user:
                db.delete(user)

            db.commit()

    finally:
        db.close()


@pytest.fixture
def cleanup_test_files():
    created_file_ids = []

    def _track_file(file_id):
        created_file_ids.append(file_id)

    yield _track_file

    db = TestSessionLocal()

    try:
        for file_id in created_file_ids:
            file_record = db.query(File).filter(File.id == file_id).first()

            if file_record:
                db.delete(file_record)

        db.commit()
    finally:
        db.close()
