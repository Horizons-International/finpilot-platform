from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.services.verification_service import VerificationService
from app.utils.enums import UserStatus
from app.utils.errors import unauthorized

security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db),
) -> User:
    token = credentials.credentials

    try:
        payload = decode_access_token(token)
    except JWTError:
        raise unauthorized("Invalid or expired token")

    if payload.get("type") != "access":
        raise unauthorized("Invalid access token")

    user_id = payload.get("sub")

    if not user_id:
        raise unauthorized("Invalid token")

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise unauthorized("User not found")

    if user.status != UserStatus.ACTIVE:
        raise unauthorized("User account is not active")

    return user


def get_verification_service(
    db: Session = Depends(get_db),
) -> VerificationService:
    return VerificationService(db)
