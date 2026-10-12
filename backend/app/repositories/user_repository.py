from uuid import UUID

from sqlalchemy.orm import Query, Session

from app.models.user import User
from app.repositories.base_repository import BaseRepository
from app.repositories.tenant_scoped_repository import resolve_tenant_id
from app.utils.enums import UserRole, UserStatus


class UserRepository(BaseRepository[User]):
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        super().__init__(db, User)
        self.tenant_id = resolve_tenant_id(db, tenant_id, required=False)

    def _require_tenant_id(self) -> UUID:
        if self.tenant_id is None:
            raise ValueError("Tenant context is required to browse or manage users.")
        return self.tenant_id

    def _tenant_filter(self, query: Query[User]) -> Query[User]:
        tenant_id = self._require_tenant_id()
        return query.filter(User.tenant_id == tenant_id)

    def get_by_id(
        self,
        user_id: UUID,
        include_deleted: bool = False,
    ) -> User | None:
        query = self._tenant_filter(self.db.query(User).filter(User.id == user_id))
        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))
        query = query.filter(User.is_platform_admin.is_(False))
        return query.first()

    def get_by_email(
        self,
        email: str,
        include_deleted: bool = False,
    ) -> User | None:
        query = self.db.query(User).filter(User.email == email)
        # A single exact-email lookup is permitted without tenant context for
        # login/bootstrap and global unique-email checks. List/search methods
        # below always require tenant context.
        if self.tenant_id is not None:
            query = query.filter(User.tenant_id == self.tenant_id)
        else:
            query = query.execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="login by globally unique user email",
            )
        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))
        return query.first()

    def create(self, user: User) -> User:
        tenant_id = self._require_tenant_id()
        if user.tenant_id is not None and user.tenant_id != tenant_id:
            raise ValueError("Cannot create a user for another tenant.")
        user.tenant_id = tenant_id
        self.db.add(user)
        self.db.flush()
        self.db.refresh(user)
        return user

    def update(self, user: User) -> User:
        tenant_id = self._require_tenant_id()
        if user.tenant_id != tenant_id:
            raise ValueError("Cannot update a user owned by another tenant.")
        self.db.flush()
        self.db.refresh(user)
        return user

    def delete(self, user: User) -> None:
        tenant_id = self._require_tenant_id()
        if user.tenant_id != tenant_id:
            raise ValueError("Cannot delete a user owned by another tenant.")
        self.db.delete(user)
        self.db.flush()

    def get_all_active(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[User]:
        query = self._tenant_filter(
            self.db.query(User).filter(User.is_deleted.is_(False))
        ).offset(offset)
        if limit is not None:
            query = query.limit(limit)
        return query.all()

    def count_active(self) -> int:
        return self._tenant_filter(
            self.db.query(User).filter(User.is_deleted.is_(False))
        ).count()

    def get_by_status(self, user_status: UserStatus) -> list[User]:
        return self._tenant_filter(
            self.db.query(User).filter(
                User.status == user_status,
                User.is_deleted.is_(False),
            )
        ).all()

    def email_exists(
        self,
        email: str,
        exclude_user_id: UUID | None = None,
    ) -> bool:
        query = self.db.query(User).filter(
            User.email == email,
            User.is_deleted.is_(False),
        )
        if self.tenant_id is not None:
            query = query.filter(User.tenant_id == self.tenant_id)
        else:
            query = query.execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="global unique-email validation",
            )
        if exclude_user_id is not None:
            query = query.filter(User.id != exclude_user_id)
        return query.first() is not None

    def soft_delete(self, user: User) -> User:
        tenant_id = self._require_tenant_id()
        if user.tenant_id != tenant_id:
            raise ValueError("Cannot delete a user owned by another tenant.")
        user.is_deleted = True
        user.status = UserStatus.INACTIVE
        self.db.flush()
        self.db.refresh(user)
        return user

    def get_paginated(
        self,
        page: int,
        page_size: int,
    ) -> tuple[list[User], int]:
        query = self._tenant_filter(
            self.db.query(User).filter(
                User.is_deleted.is_(False),
                User.is_platform_admin.is_(False),
            )
        )
        total = query.count()
        offset = (page - 1) * page_size
        users = (
            query.order_by(User.created_at.desc()).offset(offset).limit(page_size).all()
        )
        return users, total

    def count_active_organization_admins(self) -> int:
        query = self._tenant_filter(
            self.db.query(User).filter(
                User.status == UserStatus.ACTIVE,
                User.is_deleted.is_(False),
                User.is_platform_admin.is_(False),
                User.role.in_([UserRole.ADMINISTRATOR, UserRole.ORGANIZATION_ADMIN]),
            )
        )
        return query.count()
