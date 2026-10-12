from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User
from app.models.workflow import WorkflowExecution
from app.models.workflow_audit_log import WorkflowAuditLog
from app.repositories.tenant_scoped_repository import resolve_tenant_id


class WorkflowAuditLogRepository:
    def __init__(
        self,
        db: Session,
        tenant_id: UUID | None = None,
    ) -> None:
        resolved = resolve_tenant_id(db, tenant_id)
        assert resolved is not None
        self.db = db
        self.tenant_id = resolved

    def create(self, audit_log: WorkflowAuditLog) -> WorkflowAuditLog:
        if audit_log.tenant_id is not None and audit_log.tenant_id != self.tenant_id:
            raise ValueError("Cannot create a workflow audit log for another tenant.")

        execution_exists = self.db.scalar(
            select(WorkflowExecution.id).where(
                WorkflowExecution.id == audit_log.workflow_execution_id,
                WorkflowExecution.tenant_id == self.tenant_id,
            )
        )
        if execution_exists is None:
            raise ValueError("Workflow audit execution is outside this tenant.")

        if audit_log.user_id is not None:
            user_exists = self.db.scalar(
                select(User.id).where(
                    User.id == audit_log.user_id,
                    User.tenant_id == self.tenant_id,
                )
            )
            if user_exists is None:
                raise ValueError("Workflow audit actor is outside this tenant.")

        audit_log.tenant_id = self.tenant_id
        self.db.add(audit_log)
        self.db.flush()
        return audit_log

    def get_by_workflow_id(self, workflow_id: UUID) -> list[WorkflowAuditLog]:
        """Return audit records for a workflow execution ID (legacy method name)."""
        statement = (
            select(WorkflowAuditLog)
            .where(
                WorkflowAuditLog.tenant_id == self.tenant_id,
                WorkflowAuditLog.workflow_execution_id == workflow_id,
            )
            .order_by(
                WorkflowAuditLog.created_at.asc(),
                WorkflowAuditLog.id.asc(),
            )
        )
        return list(self.db.scalars(statement).all())
