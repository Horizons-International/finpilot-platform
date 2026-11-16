"""Native-async profile operations with tenant-scoped user access and audit."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.schemas.user import ProfileUpdateRequest
from app.services.async_audit_service import AsyncAuditService
from app.utils.enums import AuditEventType
from app.utils.errors import not_found


class AsyncProfileService:
    """Read and update the authenticated user's own profile."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id not in (None, tenant_id):
            raise ValueError("The database session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.audit = AsyncAuditService(db)

    async def get_profile(self, user_id: UUID) -> User:
        statement = select(User).where(
            User.id == user_id,
            User.tenant_id == self.tenant_id,
            User.is_deleted.is_(False),
        )
        user = await self.db.scalar(statement)
        if user is None:
            raise not_found("User")
        return user

    async def update_profile(
        self,
        user_id: UUID,
        profile_data: ProfileUpdateRequest,
        *,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        user = await self.get_profile(user_id)
        update_data = profile_data.model_dump(exclude_unset=True)
        if not update_data:
            return user

        changed = False
        for field, new_value in update_data.items():
            if getattr(user, field) != new_value:
                setattr(user, field, new_value)
                changed = True

        if not changed:
            return user

        await self.audit.log_event(
            event_type=AuditEventType.USER_UPDATED,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )
        try:
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        await self.db.refresh(user)
        return user
