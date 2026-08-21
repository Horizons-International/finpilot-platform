from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserStatus
from app.repositories.user_repository import UserRepository


def seed_admin() -> None:
    admin_email = "admin@example.com"
    admin_password = settings.ADMIN_PASSWORD
    if admin_password is None:
        raise RuntimeError("ADMIN_PASSWORD environment variable is required")

    db = SessionLocal()

    try:
        user_repository = UserRepository(db)

        existing_admin = user_repository.get_by_email(
            admin_email,
        )

        if existing_admin:
            print(f"Administrator already exists: {admin_email}")
            return

        admin = User(
            first_name="System",
            last_name="Administrator",
            email=admin_email,
            password_hash=hash_password(admin_password),
            status=UserStatus.ACTIVE,
            role="Administrator",
        )

        user_repository.create(admin)

        db.add(admin)
        db.commit()

        print(f"Administrator created successfully: {admin_email}")

    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
