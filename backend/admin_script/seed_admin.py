from app.core.config import settings
from app.core.database import SessionLocal
from app.core.security import hash_password, validate_password
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.utils.enums import UserStatus


def seed_admin() -> None:
    admin_email = settings.ADMIN_EMAIL
    admin_password = settings.ADMIN_PASSWORD
    if admin_password is None:
        raise RuntimeError("ADMIN_PASSWORD environment variable is required")
    try:
        validate_password(admin_password)
    except ValueError as exc:
        raise RuntimeError(f"ADMIN_PASSWORD does not meet policy: {exc}") from exc

    db = SessionLocal()

    try:
        tenant = (
            db.query(Tenant)
            .filter(
                Tenant.code == "DEFAULT",
            )
            .first()
        )

        if tenant is None:
            raise RuntimeError(
                "Default tenant does not exist. Run database migrations first."
            )

        user_repository = UserRepository(db, tenant.id)

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
            tenant_id=tenant.id,
            is_platform_admin=True,
        )

        user_repository.create(admin)

        db.add(admin)
        db.commit()

        print(f"Administrator created successfully: {admin_email}")

    finally:
        db.close()


if __name__ == "__main__":
    seed_admin()
