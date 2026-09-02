import os
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.core.database import get_db
from app.core.security import hash_password
from app.main import app
from app.models.audit_log import AuditLog
from app.models.customer import Customer, CustomerStatus
from app.models.customer_contact import CustomerContact
from app.models.customer_status_history import CustomerStatusHistory
from app.models.file import File
from app.models.user import User, UserStatus
from app.repositories.customer_repository import CustomerRepository
from app.storages.local_storage import LocalStorage

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
    storage = LocalStorage(settings.STORAGE_PATH)

    try:
        for file_id in created_file_ids:
            file_record = db.query(File).filter(File.id == file_id).first()

            if file_record:
                # Delete physical file first.
                if storage.exists(file_record.storage_path):
                    storage.delete(file_record.storage_path)

                # Delete database record.
                db.delete(file_record)

        db.commit()
    finally:
        db.close()


@pytest.fixture
def create_test_customer():
    created_customer_ids = []

    def _create_test_customer(
        first_name: str = "Test",
        middle_name: str | None = None,
        last_name: str = "Customer",
        date_of_birth: date | None = None,
        nationality: str | None = None,
        country_of_residence: str | None = None,
        email: str | None = None,
        phone_number: str = "+249123456789",
        status: CustomerStatus = CustomerStatus.NEW,
    ):
        db = TestSessionLocal()

        customer = Customer(
            first_name=first_name,
            middle_name=middle_name,
            last_name=last_name,
            date_of_birth=date_of_birth,
            nationality=nationality,
            country_of_residence=country_of_residence,
            email=email,
            phone_number=phone_number,
            status=status,
        )

        db.add(customer)
        db.commit()
        db.refresh(customer)

        created_customer_ids.append(customer)

        db.close()

        return customer

    yield _create_test_customer

    db = TestSessionLocal()

    try:
        for customer_id in created_customer_ids:
            customer = db.query(Customer).filter(Customer.id == customer_id).first()

            if customer:
                db.delete(customer)

        db.commit()
    finally:
        db.close()


@pytest.fixture
def cleanup_test_customers():
    db = TestSessionLocal()
    repository = CustomerRepository(db)

    existing_customers = {customer.id for customer in repository.get_all()}

    yield

    current_customers = repository.get_all()

    for customer in current_customers:
        if customer.id not in existing_customers:
            db.query(CustomerStatusHistory).filter(
                CustomerStatusHistory.customer_id == customer.id
            ).delete(synchronize_session=False)

            db.query(CustomerContact).filter(
                CustomerContact.customer_id == customer.id
            ).delete(synchronize_session=False)

            repository.delete(customer)

    db.commit()
    db.close()
