import os

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserStatus

DEFAULT_ADMIN_EMAIL = os.getenv(
    "ADMIN_EMAIL",
    "admin@example.com",
)


def seed_admin() -> None:
    admin_password = os.getenv("ADMIN_PASSWORD")

    if admin_password is None:
        raise RuntimeError("ADMIN_PASSWORD environment variable is required")

    db = SessionLocal()

    try:
        existing_admin = (
            db.query(User).filter(User.email == DEFAULT_ADMIN_EMAIL).first()
        )

        if existing_admin:
            print(f"Administrator already exists: {DEFAULT_ADMIN_EMAIL}")
            return

        admin = User(
            first_name="System",
            last_name="Administrator",
            email=DEFAULT_ADMIN_EMAIL,
            password_hash=hash_password(admin_password),
            status=UserStatus.ACTIVE,
            role="Administrator",
        )

        db.add(admin)
        db.commit()

        print(f"Administrator created successfully: {DEFAULT_ADMIN_EMAIL}")

    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
