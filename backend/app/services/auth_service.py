from typing import Any
from uuid import UUID

from jose import JWTError
from sqlalchemy.orm import Session

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_refresh_token,
    hash_password,
    validate_password,
    verify_password,
)
from app.repositories.user_repository import UserRepository
from app.schemas.auth import (
    AuthUserResponse,
    ChangePasswordRequest,
    LoginResponse,
    RefreshTokenResponse,
)
from app.services.audit_service import AuditService
from app.utils.enums import AuditEventType, UserStatus
from app.utils.errors import bad_request, forbidden, not_found, unauthorized


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repository = UserRepository(db)
        self.audit_service = AuditService(db)

    def login(
        self,
        email: str,
        password: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> LoginResponse:
        user = self.user_repository.get_by_email(email)

        if not user:
            self.audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                email=email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()

            raise unauthorized("Invalid email or password")

        if not verify_password(password, user.password_hash):
            self.audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=user.id,
                email=user.email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()

            raise unauthorized("Invalid email or password")

        if user.status == UserStatus.INACTIVE:
            self.audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=user.id,
                email=user.email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()

            raise forbidden("User account is inactive")

        if user.status == UserStatus.LOCKED:
            self.audit_service.log_event(
                event_type=AuditEventType.LOGIN_FAILURE,
                user_id=user.id,
                email=user.email,
                ip_address=ip_address,
                user_agent=user_agent,
            )
            self.db.commit()

            raise forbidden("User account is locked")

        token_data: dict[str, Any] = {
            "sub": str(user.id),
            "email": user.email,
            "role": user.role,
        }

        access_token = create_access_token(data=token_data)
        refresh_token = create_refresh_token(data=token_data)

        self.audit_service.log_event(
            event_type=AuditEventType.LOGIN_SUCCESS,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()

        return LoginResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            token_type="bearer",
            user=AuthUserResponse(
                id=str(user.id),
                first_name=user.first_name,
                last_name=user.last_name,
                email=user.email,
                status=user.status.value,
                role=user.role,
            ),
        )

    def refresh_token(
        self,
        refresh_token: str,
    ) -> RefreshTokenResponse:
        try:
            payload = decode_refresh_token(refresh_token)
        except JWTError as exc:
            raise unauthorized("Invalid or expired refresh token") from exc

        user_id = payload.get("sub")

        if not user_id:
            raise unauthorized("Invalid refresh token")

        access_token = create_access_token(
            data={
                "sub": user_id,
                "email": payload.get("email"),
                "role": payload.get("role"),
            }
        )

        return RefreshTokenResponse(
            access_token=access_token,
            token_type="bearer",
        )

    def change_password(
        self,
        user_id: UUID,
        password_data: ChangePasswordRequest,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        user = self.user_repository.get_by_id(user_id)

        if not user:
            raise not_found("User")

        if not verify_password(
            password_data.current_password,
            user.password_hash,
        ):
            raise bad_request("Current password is incorrect")

        if password_data.current_password == password_data.new_password:
            raise bad_request("New password must be different from current password")

        try:
            validate_password(password_data.new_password)
        except ValueError as exc:
            raise bad_request(str(exc)) from exc

        user.password_hash = hash_password(password_data.new_password)

        self.user_repository.update(user)

        self.audit_service.log_event(
            event_type=AuditEventType.PASSWORD_CHANGE,
            user_id=user.id,
            email=user.email,
            ip_address=ip_address,
            user_agent=user_agent,
        )

        self.db.commit()
