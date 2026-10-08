from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user_invitation import UserInvitation


class UserInvitationRepository:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID,
    ) -> None:
        self.db = db
        self.tenant_id = tenant_id

    def create(
        self,
        invitation: UserInvitation,
    ) -> UserInvitation:
        self.db.add(invitation)
        self.db.flush()
        self.db.refresh(invitation)

        return invitation

    def get_pending_by_email(
        self,
        email: str,
    ) -> UserInvitation | None:
        statement = (
            select(UserInvitation)
            .where(
                UserInvitation.tenant_id == self.tenant_id,
                UserInvitation.email == email,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
                UserInvitation.expires_at > datetime.now().astimezone(),
            )
            .order_by(
                UserInvitation.created_at.desc(),
            )
        )

        return self.db.scalar(statement)

    def get_by_token_hash(
        self,
        token_hash: str,
    ) -> UserInvitation | None:
        statement = select(UserInvitation).where(
            UserInvitation.token_hash == token_hash,
        )

        return self.db.scalar(statement)

    def get_by_id(
        self,
        invitation_id: UUID,
    ) -> UserInvitation | None:
        statement = select(UserInvitation).where(
            UserInvitation.id == invitation_id,
            UserInvitation.tenant_id == self.tenant_id,
        )

        return self.db.scalar(statement)
