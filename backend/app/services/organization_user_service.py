import hashlib
import secrets
from datetime import timedelta
from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import hash_password, validate_password
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.repositories.user_invitation_repository import (
    UserInvitationRepository,
)
from app.repositories.user_repository import UserRepository
from app.schemas.user import (
    UserInvitationCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, UserRole, UserStatus
from app.utils.errors import (
    bad_request,
    conflict,
    not_found,
)
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


class OrganizationUserService:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id

        self.repository = UserRepository(
            db,
            tenant_id=tenant_id,
        )

        self.invitation_repository = UserInvitationRepository(
            db,
            tenant_id=tenant_id,
        )

        self.audit_service = AuditService(db)

    @staticmethod
    def _hash_invitation_token(
        token: str,
    ) -> str:
        return hashlib.sha256(
            token.encode("utf-8"),
        ).hexdigest()

    def invite_user(
        self,
        *,
        data: UserInvitationCreate,
        invited_by: UUID,
        email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> tuple[UserInvitation, str]:
        role = data.role

        if role not in MANAGEABLE_ENTERPRISE_ROLES:
            raise bad_request(
                "The selected role cannot be assigned to organization users.",
            )

        normalized_email = str(data.email).strip().lower()

        if (
            self.repository.get_by_email(
                normalized_email,
                include_deleted=True,
            )
            is not None
        ):
            raise conflict(
                "A user with this email already exists.",
            )

        if (
            self.invitation_repository.get_pending_by_email(
                normalized_email,
            )
            is not None
        ):
            raise conflict(
                "A pending invitation already exists for this email.",
            )

        token = secrets.token_urlsafe(32)

        invitation = UserInvitation(
            tenant_id=self.tenant_id,
            email=normalized_email,
            first_name=data.first_name,
            last_name=data.last_name,
            role=role.value,
            department=(data.department.strip() if data.department else None),
            token_hash=self._hash_invitation_token(token),
            expires_at=(
                utc_now()
                + timedelta(
                    hours=settings.USER_INVITATION_EXPIRE_HOURS,
                )
            ),
            invited_by=invited_by,
        )

        self.invitation_repository.create(
            invitation,
        )

        self.audit_service.log_event(
            event_type=AuditEventType.USER_INVITED,
            user_id=invited_by,
            email=email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user_invitation",
            resource_id=invitation.id,
        )

        self.db.commit()
        self.db.refresh(invitation)

        return invitation, token

    def list_users(
        self,
        *,
        page: int = 1,
        page_size: int = 20,
    ) -> UserListResponse:
        validate_pagination(
            page,
            page_size,
        )

        users, total = self.repository.get_paginated(
            page=page,
            page_size=page_size,
        )

        pagination = Pagination(
            page=page,
            page_size=page_size,
            total=total,
        )

        return UserListResponse(
            users=[UserResponse.model_validate(user) for user in users],
            total=total,
            page=page,
            page_size=page_size,
            total_pages=pagination.total_pages,
        )

    def get_user(
        self,
        user_id: UUID,
    ) -> User:
        user = self.repository.get_by_id(
            user_id,
        )

        if user is None:
            raise not_found("User")

        return user

    def update_user(
        self,
        *,
        user_id: UUID,
        data: UserUpdate,
        acting_user_id: UUID,
        acting_user_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> User:
        user = self.get_user(
            user_id,
        )

        if user.id == acting_user_id:
            raise bad_request(
                "You cannot modify your own enterprise user account here.",
            )

        update_data = data.model_dump(
            exclude_unset=True,
        )

        if not update_data:
            raise bad_request(
                "No user fields were provided for update.",
            )

        if "role" in update_data:
            new_role = update_data["role"]

            if new_role not in MANAGEABLE_ENTERPRISE_ROLES:
                raise bad_request(
                    "The selected role cannot be assigned to organization users.",
                )

            if (
                user.role
                in {
                    UserRole.ADMINISTRATOR,
                    UserRole.ORGANIZATION_ADMIN,
                }
                and new_role
                not in {
                    UserRole.ADMINISTRATOR,
                    UserRole.ORGANIZATION_ADMIN,
                }
                and user.status == UserStatus.ACTIVE
                and self.repository.count_active_organization_admins() <= 1
            ):
                raise bad_request(
                    "The organization must have at least one active administrator.",
                )

        if "email" in update_data:
            normalized_email = (
                str(
                    update_data["email"],
                )
                .strip()
                .lower()
            )

            existing_user = self.repository.get_by_email(
                normalized_email,
            )

            if existing_user is not None and existing_user.id != user_id:
                raise conflict(
                    "A user with this email already exists.",
                )

            update_data["email"] = normalized_email

        if "department" in update_data:
            department = update_data["department"]

            update_data["department"] = department.strip() if department else None

        role_changed = False

        for field, new_value in update_data.items():
            old_value = getattr(
                user,
                field,
            )

            if old_value == new_value:
                continue

            if field == "role":
                role_changed = True

            setattr(
                user,
                field,
                new_value,
            )

        self.db.flush()

        self.audit_service.log_event(
            event_type=(
                AuditEventType.USER_ROLE_CHANGED
                if role_changed
                else AuditEventType.USER_UPDATED
            ),
            user_id=acting_user_id,
            email=acting_user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def update_status(
        self,
        *,
        user_id: UUID,
        data: UserStatusUpdate,
        acting_user_id: UUID,
        acting_user_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> User:
        user = self.get_user(
            user_id,
        )

        if user.id == acting_user_id:
            raise bad_request(
                "You cannot disable your own account.",
            )

        if (
            user.status == UserStatus.ACTIVE
            and data.status != UserStatus.ACTIVE
            and user.role
            in {
                UserRole.ADMINISTRATOR,
                UserRole.ORGANIZATION_ADMIN,
            }
            and self.repository.count_active_organization_admins() <= 1
        ):
            raise bad_request(
                "The organization must have at least one active administrator.",
            )

        if user.status == data.status:
            raise bad_request(
                "User already has this status.",
            )

        user.status = data.status

        self.db.flush()

        self.audit_service.log_event(
            event_type=AuditEventType.USER_STATUS_CHANGED,
            user_id=acting_user_id,
            email=acting_user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def delete_user(
        self,
        *,
        user_id: UUID,
        acting_user_id: UUID,
        acting_user_email: str,
        ip_address: str | None,
        user_agent: str | None,
    ) -> User:
        user = self.get_user(
            user_id,
        )

        if user.id == acting_user_id:
            raise bad_request(
                "You cannot remove your own account.",
            )

        if (
            user.role
            in {
                UserRole.ADMINISTRATOR,
                UserRole.ORGANIZATION_ADMIN,
            }
            and user.status == UserStatus.ACTIVE
            and self.repository.count_active_organization_admins() <= 1
        ):
            raise bad_request(
                "The organization must have at least one active administrator.",
            )

        user.is_deleted = True
        user.status = UserStatus.INACTIVE

        self.db.flush()

        self.audit_service.log_event(
            event_type=AuditEventType.USER_DELETED,
            user_id=acting_user_id,
            email=acting_user_email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def accept_invitation(
        self,
        *,
        token: str,
        password: str,
    ) -> User:
        try:
            validate_password(password)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        token_hash = self._hash_invitation_token(
            token,
        )

        invitation = (
            self.db.query(UserInvitation)
            .filter(
                UserInvitation.token_hash == token_hash,
            )
            .first()
        )

        if invitation is None:
            raise not_found("User invitation")

        if invitation.accepted_at is not None:
            raise bad_request(
                "This invitation has already been accepted.",
            )

        if invitation.revoked_at is not None:
            raise bad_request(
                "This invitation has been revoked.",
            )

        if invitation.expires_at <= utc_now():
            raise bad_request(
                "This invitation has expired.",
            )

        existing_user = (
            self.db.query(User)
            .filter(
                User.email == invitation.email,
            )
            .first()
        )

        if existing_user is not None:
            raise conflict(
                "A user with this email already exists.",
            )

        user = User(
            tenant_id=invitation.tenant_id,
            first_name=invitation.first_name,
            last_name=invitation.last_name,
            email=invitation.email,
            password_hash=hash_password(password),
            status=UserStatus.ACTIVE,
            role=UserRole(invitation.role),
            department=invitation.department,
            is_platform_admin=False,
            is_deleted=False,
        )

        self.db.add(user)

        try:
            self.db.flush()
        except IntegrityError as exc:
            self.db.rollback()
            raise conflict(
                "A user with this email already exists.",
            ) from exc

        invitation.accepted_at = utc_now()

        self.audit_service.log_event(
            event_type=AuditEventType.USER_INVITATION_ACCEPTED,
            user_id=user.id,
            email=user.email,
            ip_address=None,
            user_agent=None,
            resource_type="user",
            resource_id=user.id,
        )

        self.audit_service.log_event(
            event_type=AuditEventType.USER_CREATED,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user
