"""Async public invitation acceptance with locking and quota enforcement."""

import hashlib
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from app.core.security import hash_password, validate_password
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.services.async_audit_service import AsyncAuditService
from app.services.async_subscription_capacity import ensure_subscription_capacity
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, UserRole, UserStatus
from app.utils.errors import bad_request, conflict, not_found


class AsyncUserInvitationAcceptanceService:
    """Accept a public invitation without opening a synchronous DB session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.audit = AsyncAuditService(db)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    async def accept(self, *, token: str, password: str) -> User:
        try:
            validate_password(password)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        previous_tenant_id = self.db.info.get("tenant_id")
        try:
            token_hash = self._hash_token(token)
            invitation_statement = (
                select(UserInvitation)
                .where(UserInvitation.token_hash == token_hash)
                .execution_options(
                    skip_tenant_filter=True,
                    tenant_scope_reason=(
                        "resolve public invitation by its unique bearer-token hash"
                    ),
                )
                .with_for_update()
            )
            invitation = await self.db.scalar(invitation_statement)
            if invitation is None:
                raise not_found("User invitation")

            # The opaque token establishes the tenant for this unauthenticated flow.
            invitation_tenant_id: UUID = invitation.tenant_id
            if (
                previous_tenant_id is not None
                and previous_tenant_id != invitation_tenant_id
            ):
                raise not_found("User invitation")
            self.db.info["tenant_id"] = invitation_tenant_id

            now = utc_now()
            if invitation.accepted_at is not None:
                raise bad_request("This invitation has already been accepted.")
            if invitation.revoked_at is not None:
                raise bad_request("This invitation has been revoked.")
            if invitation.expires_at <= now:
                raise bad_request("This invitation has expired.")

            existing_user = await self.db.scalar(
                select(User)
                .where(User.email == invitation.email)
                .execution_options(
                    skip_tenant_filter=True,
                    tenant_scope_reason=(
                        "check globally unique email before accepting invitation"
                    ),
                )
            )
            if existing_user is not None:
                raise conflict("A user with this email already exists.")

            # This uses the existing async subscription/tenant locks so concurrent
            # invitations and user creation share the same active-user capacity guard.
            await ensure_subscription_capacity(
                self.db,
                invitation_tenant_id,
                metric="active_users",
                additional=1,
            )
            password_hash = await run_in_threadpool(hash_password, password)
            user = User(
                tenant_id=invitation_tenant_id,
                first_name=invitation.first_name,
                last_name=invitation.last_name,
                email=invitation.email,
                password_hash=password_hash,
                status=UserStatus.ACTIVE,
                role=UserRole(invitation.role),
                department=invitation.department,
                is_platform_admin=False,
                is_deleted=False,
            )
            self.db.add(user)
            await self.db.flush()

            invitation.accepted_at = now
            await self.audit.log_event(
                event_type=AuditEventType.USER_INVITATION_ACCEPTED,
                user_id=user.id,
                email=user.email,
                resource_type="user",
                resource_id=user.id,
            )
            await self.audit.log_event(
                event_type=AuditEventType.USER_CREATED,
                user_id=user.id,
                email=user.email,
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
            if previous_tenant_id is None:
                self.db.info.pop("tenant_id", None)
            else:
                self.db.info["tenant_id"] = previous_tenant_id
