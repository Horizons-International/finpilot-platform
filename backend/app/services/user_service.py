from uuid import UUID

from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.tenant import TenantStatus
from app.schemas.user import (
    UserCreate,
    UserListResponse,
    UserResponse,
    UserStatusUpdate,
    UserUpdate,
)
from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType, UserStatus
from app.utils.errors import bad_request, forbidden, not_found
from app.utils.pagination import Pagination, validate_pagination


class UserService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)
        self.audit_service = AuditService(db)

    def create_user(
        self,
        user_data: UserCreate,
        *,
        actor_tenant_id: UUID,
        actor_is_platform_admin: bool,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        existing_user = self.repository.get_by_email(
            user_data.email,
        )

        if existing_user:
            raise bad_request("Email is already registered")

        target_tenant_id = (
            user_data.tenant_id if user_data.tenant_id is not None else actor_tenant_id
        )

        if target_tenant_id != actor_tenant_id and not actor_is_platform_admin:
            raise forbidden(
                "You cannot create a user in another tenant.",
            )

        tenant = self.db.get(
            Tenant,
            target_tenant_id,
        )

        if tenant is None:
            raise not_found("Tenant")

        if tenant.status != TenantStatus.ACTIVE:
            raise bad_request(
                "Cannot create a user in an inactive tenant.",
            )

        user = User(
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            email=user_data.email,
            password_hash=hash_password(user_data.password),
            status=UserStatus.ACTIVE,
            role=user_data.role,
            department=(user_data.department.strip() if user_data.department else None),
            tenant_id=target_tenant_id,
            is_platform_admin=False,
            is_deleted=False,
        )

        user = self.repository.create(user)

        self.db.flush()

        self.audit_service.log_event(
            event_type=AuditEventType.USER_CREATED,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def get_user(self, user_id: UUID) -> User:
        user = self.repository.get_by_id(user_id)

        if not user:
            raise not_found("User")

        return user

    def update_user(
        self,
        user_id: UUID,
        user_data: UserUpdate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        user = self.get_user(user_id)

        update_data = user_data.model_dump(exclude_unset=True)

        if not update_data:
            return user

        if "department" in update_data:
            department = update_data["department"]

            update_data["department"] = department.strip() if department else None

        changed_fields: list[tuple[str, object | None, object | None]] = []

        for field, new_value in update_data.items():
            old_value = getattr(user, field)

            if old_value == new_value:
                continue

            changed_fields.append(
                (
                    field,
                    old_value,
                    new_value,
                )
            )

        if not changed_fields:
            return user

        changed_field_names = {field for field, _, _ in changed_fields}

        if "email" in changed_field_names:
            existing_user = self.repository.get_by_email(
                update_data["email"],
            )

            if existing_user and existing_user.id != user_id:
                raise bad_request("Email is already registered")

        for field, _, new_value in changed_fields:
            setattr(user, field, new_value)

        user = self.repository.update(user)

        self.audit_service.log_event(
            event_type=AuditEventType.USER_UPDATED,
            user_id=user.id,
            email=user.email,
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
        user_id: UUID,
        status_data: UserStatusUpdate,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        user = self.get_user(user_id)

        old_status = user.status
        new_status = status_data.status

        # Requested status is already the current status.
        if old_status == new_status:
            raise bad_request("User already has this status.")

        user.status = new_status

        user = self.repository.update(user)

        self.audit_service.log_event(
            event_type=AuditEventType.USER_STATUS_CHANGED,
            user_id=user.id,
            email=user.email,
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
        user_id: UUID,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> User:
        user = self.get_user(user_id)

        self.repository.soft_delete(user)

        self.audit_service.log_event(
            event_type=AuditEventType.USER_DELETED,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user

    def get_users(
        self,
        page: int = 1,
        page_size: int = 20,
    ) -> UserListResponse:
        validate_pagination(page, page_size)

        users, total = self.repository.get_paginated(
            page=page,
            page_size=page_size,
        )

        pagination = Pagination(
            page=page,
            page_size=page_size,
            total=total,
        )

        user_responses = [UserResponse.model_validate(user) for user in users]

        return UserListResponse(
            users=user_responses,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=pagination.total_pages,
        )
