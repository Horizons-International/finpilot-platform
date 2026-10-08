import hashlib

from sqlalchemy.orm import Session

from app.core.security import hash_password, validate_password
from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.services.audit_service import AuditService
from app.utils.date_time import utc_now
from app.utils.enums import AuditEventType, UserRole, UserStatus
from app.utils.errors import (
    bad_request,
    conflict,
    not_found,
)


class UserInvitationService:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db
        self.audit_service = AuditService(db)

    @staticmethod
    def _hash_token(
        token: str,
    ) -> str:
        return hashlib.sha256(
            token.encode("utf-8"),
        ).hexdigest()

    def accept(
        self,
        *,
        token: str,
        password: str,
    ) -> User:
        try:
            validate_password(password)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        token_hash = self._hash_token(token)

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
        self.db.flush()

        invitation.accepted_at = utc_now()

        self.audit_service.log_event(
            event_type=AuditEventType.USER_INVITATION_ACCEPTED,
            user_id=user.id,
            email=user.email,
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
