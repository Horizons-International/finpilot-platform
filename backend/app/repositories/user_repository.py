from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.base_repository import BaseRepository
from app.utils.enums import UserStatus


class UserRepository(BaseRepository[User]):
    def __init__(self, db: Session) -> None:
        super().__init__(db, User)

    def get_by_id(
        self,
        user_id: UUID,
        include_deleted: bool = False,
    ) -> User | None:
        query = self.db.query(User).filter(User.id == user_id)

        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))

        return query.first()

    def get_by_email(
        self,
        email: str,
        include_deleted: bool = False,
    ) -> User | None:
        query = self.db.query(User).filter(User.email == email)

        if not include_deleted:
            query = query.filter(User.is_deleted.is_(False))

        return query.first()

    def get_all_active(
        self,
        offset: int = 0,
        limit: int | None = None,
    ) -> list[User]:
        query = self.db.query(User).filter(User.is_deleted.is_(False))

        query = query.offset(offset)

        if limit is not None:
            query = query.limit(limit)

        return query.all()

    def count_active(self) -> int:
        return self.db.query(User).filter(User.is_deleted.is_(False)).count()

    def get_by_status(
        self,
        user_status: UserStatus,
    ) -> list[User]:
        return (
            self.db.query(User)
            .filter(
                User.status == user_status,
                User.is_deleted.is_(False),
            )
            .all()
        )

    def email_exists(
        self,
        email: str,
        exclude_user_id: UUID | None = None,
    ) -> bool:
        query = self.db.query(User).filter(
            User.email == email,
            User.is_deleted.is_(False),
        )

        if exclude_user_id is not None:
            query = query.filter(User.id != exclude_user_id)

        return query.first() is not None

    def soft_delete(self, user: User) -> User:
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
        query = self.db.query(User).filter(
            User.is_deleted.is_(False),
        )

        total = query.count()

        offset = (page - 1) * page_size

        users = query.offset(offset).limit(page_size).all()

        return users, total
