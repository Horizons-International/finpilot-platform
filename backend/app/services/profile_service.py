from uuid import UUID

from sqlalchemy.orm import Session

from app.models.audit_log import AuditEventType
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.user import ProfileUpdateRequest
from app.services.audit_service import AuditService
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

        if profile_data.first_name is not None:
            user.first_name = profile_data.first_name

        if profile_data.last_name is not None:
            user.last_name = profile_data.last_name

        if profile_data.phone_number is not None:
            user.phone_number = profile_data.phone_number

        user = self.repository.update(user)

        self.audit_service.log_event(
            event_type=AuditEventType.USER_UPDATED,
            user_id=user.id,
            email=user.email,
            resource_type="user",
            resource_id=user.id,
        )

        self.db.commit()

        return user
