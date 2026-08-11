from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserStatus


def seed_admin() -> None:
    admin_email = "admin@example.com"
    admin_password = settings.ADMIN_PASSWORD
    if admin_password is None:
        raise RuntimeError("ADMIN_PASSWORD environment variable is required")

    db = SessionLocal()

    try:
        existing_admin = db.query(User).filter(User.email == admin_email).first()

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

        db.add(admin)
        db.commit()

        print(f"Administrator created successfully: {admin_email}")

    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
