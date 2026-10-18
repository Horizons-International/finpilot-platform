from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.data_protection import (
    DataDeletionRequest,
    DataLegalHold,
    DataProtectionPolicy,
)


class DataProtectionRepository:
    """Persistence boundary; every lookup explicitly binds to the active tenant."""

    def __init__(self, db: Session, tenant_id: uuid.UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        session_tenant_id = db.info.get("tenant_id")
        if session_tenant_id is not None and session_tenant_id != tenant_id:
            raise ValueError(
                "The SQLAlchemy session is already bound to another tenant"
            )
        if session_tenant_id is None:
            db.info["tenant_id"] = tenant_id

    def get_policy(self, resource_type: str) -> DataProtectionPolicy | None:
        return self.db.scalar(
            select(DataProtectionPolicy).where(
                DataProtectionPolicy.tenant_id == self.tenant_id,
                DataProtectionPolicy.resource_type == resource_type,
            )
        )

    def list_policies(self) -> list[DataProtectionPolicy]:
        return list(
            self.db.scalars(
                select(DataProtectionPolicy)
                .where(
                    DataProtectionPolicy.tenant_id == self.tenant_id,
                )
                .order_by(DataProtectionPolicy.resource_type)
            ).all()
        )

    def list_deletion_requests(self, limit: int = 100) -> list[DataDeletionRequest]:
        return list(
            self.db.scalars(
                select(DataDeletionRequest)
                .where(
                    DataDeletionRequest.tenant_id == self.tenant_id,
                )
                .order_by(DataDeletionRequest.requested_at.desc())
                .limit(limit)
            ).all()
        )

    def get_deletion_request(self, request_id: uuid.UUID) -> DataDeletionRequest | None:
        return self.db.scalar(
            select(DataDeletionRequest).where(
                DataDeletionRequest.id == request_id,
                DataDeletionRequest.tenant_id == self.tenant_id,
            )
        )

    def active_hold(
        self, resource_type: str, resource_id: uuid.UUID
    ) -> DataLegalHold | None:
        return self.db.scalar(
            select(DataLegalHold).where(
                DataLegalHold.tenant_id == self.tenant_id,
                DataLegalHold.resource_type == resource_type,
                DataLegalHold.resource_id == resource_id,
                DataLegalHold.active.is_(True),
            )
        )

    def active_holds_for(
        self, resource_type: str, resource_ids: list[uuid.UUID]
    ) -> list[DataLegalHold]:
        if not resource_ids:
            return []
        return list(
            self.db.scalars(
                select(DataLegalHold).where(
                    DataLegalHold.tenant_id == self.tenant_id,
                    DataLegalHold.resource_type == resource_type,
                    DataLegalHold.resource_id.in_(resource_ids),
                    DataLegalHold.active.is_(True),
                )
            ).all()
        )
