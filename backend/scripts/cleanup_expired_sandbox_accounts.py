"""Delete expired sandbox accounts and their dependent sandbox-only records.

Run this script only with the dedicated sandbox deployment environment loaded.
The script refuses to run unless SANDBOX_ENABLED is explicitly true.
"""

from sqlalchemy import delete

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.sandbox import SandboxAccount
from app.utils.date_time import utc_now


def main() -> int:
    if not settings.SANDBOX_ENABLED:
        raise RuntimeError("Refusing sandbox cleanup because SANDBOX_ENABLED is false.")

    db = SessionLocal()

    try:
        deleted_ids = db.scalars(
            delete(SandboxAccount)
            .where(SandboxAccount.expires_at <= utc_now())
            .returning(SandboxAccount.id)
        ).all()

        db.commit()

        deleted_count = len(deleted_ids)
        print(f"Deleted {deleted_count} expired sandbox account(s).")

        return deleted_count

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    main()
