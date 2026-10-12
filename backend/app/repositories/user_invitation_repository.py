from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.user_invitation import UserInvitation
from app.repositories.tenant_scoped_repository import resolve_tenant_id


class UserInvitationRepository:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        self.db = db
        self.tenant_id = resolve_tenant_id(db, tenant_id, required=False)

    def _require_tenant_id(self) -> UUID:
        if self.tenant_id is None:
            raise ValueError(
                "Tenant context is required for ordinary invitation operations."
            )
        return self.tenant_id

    def create(self, invitation: UserInvitation) -> UserInvitation:
        tenant_id = self._require_tenant_id()
        if invitation.tenant_id is not None and invitation.tenant_id != tenant_id:
            raise ValueError("Cannot create an invitation for another tenant.")

        invitation.tenant_id = tenant_id

        if invitation.invited_by is not None:
            inviter_exists = self.db.scalar(
                select(User.id).where(
                    User.id == invitation.invited_by,
                    User.tenant_id == tenant_id,
                )
            )
            if inviter_exists is None:
                raise ValueError("Invitation creator is outside this tenant.")

        self.db.add(invitation)
        self.db.flush()
        self.db.refresh(invitation)
        return invitation

    def get_pending_by_email(self, email: str) -> UserInvitation | None:
        tenant_id = self._require_tenant_id()
        statement = (
            select(UserInvitation)
            .where(
                UserInvitation.tenant_id == tenant_id,
                UserInvitation.email == email,
                UserInvitation.accepted_at.is_(None),
                UserInvitation.revoked_at.is_(None),
                UserInvitation.expires_at > datetime.now().astimezone(),
            )
            .order_by(UserInvitation.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(statement)

    def get_by_token_hash(self, token_hash: str) -> UserInvitation | None:
        """Resolve an opaque invitation token for the public acceptance flow.

        This is deliberately allowed without tenant context because the token
        hash is the bearer capability used to identify exactly one invitation.
        Once a valid invitation is found, the service should establish its
        tenant context before doing further tenant-owned work.
        """
        statement = select(UserInvitation).where(
            UserInvitation.token_hash == token_hash,
        )
        if self.tenant_id is not None:
            statement = statement.where(UserInvitation.tenant_id == self.tenant_id)
        return self.db.scalar(statement)

    def get_by_id(self, invitation_id: UUID) -> UserInvitation | None:
        tenant_id = self._require_tenant_id()
        statement = select(UserInvitation).where(
            UserInvitation.id == invitation_id,
            UserInvitation.tenant_id == tenant_id,
        )
        return self.db.scalar(statement)
