"""Native-async user administration and invitation workflows."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.config import settings
from app.core.security import hash_password, validate_password
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.schemas.user import (
    UserCreate,
    UserInvitationCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.async_audit_service import AsyncAuditService
from app.services.async_subscription_capacity import ensure_subscription_capacity
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, UserRole, UserStatus
from app.utils.errors import bad_request, conflict, forbidden, not_found
from app.utils.pagination import Pagination, validate_pagination

MANAGEABLE_ENTERPRISE_ROLES = {
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.ANALYST,
    UserRole.VIEWER,
}
_ADMIN_ROLES = {UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN}


class AsyncOrganizationUserService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        if db.info.get("tenant_id") not in (None, tenant_id):
            raise ValueError("The database session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db, self.tenant_id = db, tenant_id
        self.audit = AsyncAuditService(db)

    async def _get(self, user_id: UUID, *, lock: bool = False) -> User:
        stmt = select(User).where(
            User.id == user_id,
            User.tenant_id == self.tenant_id,
            User.is_deleted.is_(False),
        )
        if lock:
            stmt = stmt.with_for_update()
        user = await self.db.scalar(stmt)
        if user is None:
            raise not_found("User")
        return user

    async def _admin_count(self) -> int:
        return int(
            await self.db.scalar(
                select(func.count(User.id)).where(
                    User.tenant_id == self.tenant_id,
                    User.status == UserStatus.ACTIVE,
                    User.is_deleted.is_(False),
                    User.role.in_([r.value for r in _ADMIN_ROLES]),
                )
            )
            or 0
        )

    async def get_user(self, user_id: UUID) -> User:
        return await self._get(user_id)

    async def create_user(
        self,
        data: UserCreate,
        *,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
        target_tenant_id: UUID | None = None,
        actor_is_platform_admin: bool = False,
    ) -> User:
        target = target_tenant_id or self.tenant_id
        if target != self.tenant_id and not actor_is_platform_admin:
            raise forbidden("You cannot create a user in another tenant.")
        email = str(data.email).strip().lower()
        existing = await self.db.scalar(
            select(User)
            .where(func.lower(User.email) == email)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "enforce globally unique user email before creating account"
                ),
            )
        )
        if existing:
            raise bad_request("Email is already registered")
        from app.models.tenant import Tenant

        tenant = await self.db.scalar(
            select(Tenant)
            .where(Tenant.id == target)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "validate the explicitly selected tenant "
                    "before creating an organization user"
                ),
            )
        )
        if tenant is None:
            raise not_found("Tenant")
        from app.utils.enums import TenantStatus

        if tenant.status != TenantStatus.ACTIVE:
            raise bad_request("Cannot create a user in an inactive tenant.")

        previous_tenant = self.db.info.get("tenant_id")
        self.db.info["tenant_id"] = target
        try:
            try:
                validate_password(data.password)
            except ValueError as exc:
                raise bad_request(str(exc)) from exc
            await ensure_subscription_capacity(
                self.db, target, "active_users", additional=1
            )
            password_hash = await run_in_threadpool(hash_password, data.password)
            user = User(
                tenant_id=target,
                first_name=data.first_name,
                last_name=data.last_name,
                email=email,
                password_hash=password_hash,
                status=UserStatus.ACTIVE,
                role=data.role,
                department=data.department.strip() if data.department else None,
                is_platform_admin=False,
                is_deleted=False,
            )
            self.db.add(user)
            await self.db.flush()
            await self.audit.log_event(
                event_type=AuditEventType.USER_CREATED,
                user_id=user.id,
                email=user.email,
                ip_address=ip_address,
                user_agent=user_agent,
                resource_type="user",
                resource_id=user.id,
            )
            await self.db.commit()
            await self.db.refresh(user)
            return user
        except IntegrityError as exc:
            await self.db.rollback()
            raise conflict("A user with this email already exists.") from exc
        except Exception:
            await self.db.rollback()
            raise
        finally:
            if previous_tenant is None:
                self.db.info.pop("tenant_id", None)
            else:
                self.db.info["tenant_id"] = previous_tenant

    async def list_users(
        self, *, page: int = 1, page_size: int = 20
    ) -> UserListResponse:
        validate_pagination(page, page_size)
        total = int(
            await self.db.scalar(
                select(func.count(User.id)).where(
                    User.tenant_id == self.tenant_id, User.is_deleted.is_(False)
                )
            )
            or 0
        )
        rows = await self.db.scalars(
            select(User)
            .where(User.tenant_id == self.tenant_id, User.is_deleted.is_(False))
            .order_by(User.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        pagination = Pagination(page=page, page_size=page_size, total=total)
        return UserListResponse(
            users=[UserResponse.model_validate(user) for user in rows.all()],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=pagination.total_pages,
        )

    async def update_user(
        self,
        *,
        user_id: UUID,
        data: UserUpdate,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> User:
        user = await self._get(user_id, lock=True)
        if user.id == actor_id:
            raise bad_request(
                "You cannot modify your own enterprise user account here."
            )
        changes = data.model_dump(exclude_unset=True)
        if not changes:
            raise bad_request("No user fields were provided for update.")
        if (
            changes.get("role") is not None
            and changes["role"] not in MANAGEABLE_ENTERPRISE_ROLES
        ):
            raise bad_request(
                "The selected role cannot be assigned to organization users."
            )
        if changes.get("email") is not None:
            email = str(changes["email"]).strip().lower()
            existing = await self.db.scalar(
                select(User)
                .where(func.lower(User.email) == email)
                .execution_options(
                    skip_tenant_filter=True,
                    tenant_scope_reason=(
                        "check globally unique email before updating user"
                    ),
                )
            )
            if existing is not None and existing.id != user_id:
                raise conflict("A user with this email already exists.")
            changes["email"] = email
        if "department" in changes:
            changes["department"] = (
                changes["department"].strip() if changes["department"] else None
            )
        if (
            changes.get("role") is not None
            and user.role in {r.value for r in _ADMIN_ROLES}
            and changes["role"] not in _ADMIN_ROLES
            and user.status == UserStatus.ACTIVE
            and await self._admin_count() <= 1
        ):
            raise bad_request(
                "The organization must have at least one active administrator."
            )
        changed = False
        role_changed = False
        for field, value in changes.items():
            if getattr(user, field) != value:
                setattr(user, field, value)
                changed = True
                role_changed |= field == "role"
        if not changed:
            raise bad_request("No user fields were changed.")
        await self.audit.log_event(
            event_type=(
                AuditEventType.USER_ROLE_CHANGED
                if role_changed
                else AuditEventType.USER_UPDATED
            ),
            user_id=actor_id,
            email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def update_status(
        self,
        *,
        user_id: UUID,
        data: UserStatusUpdate,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> User:
        user = await self._get(user_id, lock=True)
        if user.id == actor_id:
            raise bad_request("You cannot disable your own account.")
        if user.status == data.status:
            raise bad_request("User already has this status.")
        if (
            user.status == UserStatus.ACTIVE
            and data.status != UserStatus.ACTIVE
            and user.role in {r.value for r in _ADMIN_ROLES}
            and await self._admin_count() <= 1
        ):
            raise bad_request(
                "The organization must have at least one active administrator."
            )
        if data.status == UserStatus.ACTIVE and user.status != UserStatus.ACTIVE:
            await ensure_subscription_capacity(
                self.db, self.tenant_id, "active_users", additional=1
            )
        user.status = data.status
        await self.audit.log_event(
            event_type=AuditEventType.USER_STATUS_CHANGED,
            user_id=actor_id,
            email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    async def delete_user(
        self,
        *,
        user_id: UUID,
        actor_id: UUID,
        actor_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> User:
        user = await self._get(user_id, lock=True)
        if user.id == actor_id:
            raise bad_request("You cannot remove your own account.")
        if (
            user.role in {r.value for r in _ADMIN_ROLES}
            and user.status == UserStatus.ACTIVE
            and await self._admin_count() <= 1
        ):
            raise bad_request(
                "The organization must have at least one active administrator."
            )
        user.is_deleted = True
        user.status = UserStatus.INACTIVE
        await self.audit.log_event(
            event_type=AuditEventType.USER_DELETED,
            user_id=actor_id,
            email=actor_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )
        await self.db.commit()
        await self.db.refresh(user)
        return user

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def invite_user(
        self,
        *,
        data: UserInvitationCreate,
        invited_by: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[UserInvitation, str]:
        if data.role not in MANAGEABLE_ENTERPRISE_ROLES:
            raise bad_request(
                "The selected role cannot be assigned to organization users."
            )
        normalized = str(data.email).strip().lower()
        existing = await self.db.scalar(
            select(User)
            .where(func.lower(User.email) == normalized)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="ensure invitation email is globally unique",
            )
        )
        if existing:
            raise conflict("A user with this email already exists.")
        pending = await self.db.scalar(
            select(UserInvitation).where(
                UserInvitation.tenant_id == self.tenant_id,
                UserInvitation.email == normalized,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
                UserInvitation.expires_at > utc_now(),
            )
        )
        if pending:
            raise conflict("A pending invitation already exists for this email.")
        token = secrets.token_urlsafe(32)
        invitation = UserInvitation(
            tenant_id=self.tenant_id,
            email=normalized,
            first_name=data.first_name,
            last_name=data.last_name,
            role=data.role.value,
            department=data.department.strip() if data.department else None,
            token_hash=self._token_hash(token),
            expires_at=utc_now()
            + timedelta(hours=settings.USER_INVITATION_EXPIRE_HOURS),
            invited_by=invited_by,
        )
        self.db.add(invitation)
        await self.db.flush()
        await self.audit.log_event(
            event_type=AuditEventType.USER_INVITED,
            user_id=invited_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user_invitation",
            resource_id=invitation.id,
        )
        await self.db.commit()
        await self.db.refresh(invitation)
        return invitation, token
