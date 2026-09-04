from uuid import UUID

from sqlalchemy.orm import Session

from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import ProfileUpdateRequest
from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType
from app.utils.errors import not_found


class ProfileService:
    def __init__(self, db: Session):
        self.db = db
        self.repository = UserRepository(db)
        self.audit_service = AuditService(db)

    def get_profile(self, user_id: UUID) -> User:
        user = self.repository.get_by_id(user_id)

        if not user:
            raise not_found("User")

        return user

    def update_profile(
        self,
        user_id: UUID,
        profile_data: ProfileUpdateRequest,
    ) -> User:
        user = self.get_profile(user_id)

        update_data = profile_data.model_dump(exclude_unset=True)

        # Nothing was supplied in the request.
        if not update_data:
            return user

        changed = False

        for field, new_value in update_data.items():
            old_value = getattr(user, field)

            if old_value == new_value:
                continue

            setattr(user, field, new_value)
            changed = True

        if not changed:
            return user

        user = self.repository.update(user)

        self.audit_service.log_event(
            event_type=AuditEventType.USER_UPDATED,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()
        self.db.refresh(user)

        return user
