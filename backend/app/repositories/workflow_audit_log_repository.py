from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.workflow_audit_log import WorkflowAuditLog


class WorkflowAuditLogRepository:
    def __init__(
        self,
        db: Session,
    ) -> None:
        self.db = db

    def create(
        self,
        audit_log: WorkflowAuditLog,
    ) -> WorkflowAuditLog:
        self.db.add(audit_log)
        self.db.flush()

        return audit_log

    def get_by_workflow_id(
        self,
        workflow_id: UUID,
    ) -> list[WorkflowAuditLog]:
        statement = (
            select(WorkflowAuditLog)
            .where(
                WorkflowAuditLog.workflow_id == workflow_id,
            )
            .order_by(
                WorkflowAuditLog.created_at.asc(),
                WorkflowAuditLog.id.asc(),
            )
        )

        return list(
            self.db.scalars(statement).all(),
        )
