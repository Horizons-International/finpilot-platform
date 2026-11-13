"""Native-async customer onboarding orchestration over AsyncWorkflowService."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.workflow import Workflow, WorkflowExecution
from app.schemas.workflow import WorkflowAdvanceRequest, WorkflowExecutionCreate
from app.services.async_workflow_service import AsyncWorkflowService
from app.utils.enums import UserRole, WorkflowExecutionStatus, WorkflowStatus
from app.utils.errors import bad_request, not_found

CUSTOMER_ONBOARDING_WORKFLOW_NAME = "Customer Onboarding"
CUSTOMER_ONBOARDING_ENTITY_TYPE = "customer"
_ACTIVE_EXECUTION_STATUSES = {
    WorkflowExecutionStatus.IN_PROGRESS,
    WorkflowExecutionStatus.FAILED,
}


class AsyncCustomerOnboardingService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError("Onboarding service tenant does not match session tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.workflow_service = AsyncWorkflowService(db, tenant_id)

    async def _require_customer(self, customer_id: UUID) -> Customer:
        customer = await self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )
        if customer is None:
            raise not_found("Customer")
        return customer

    async def _workflow(self) -> Workflow:
        workflow = await self.db.scalar(
            select(Workflow).where(
                Workflow.tenant_id == self.tenant_id,
                Workflow.name == CUSTOMER_ONBOARDING_WORKFLOW_NAME,
            )
        )
        if workflow is None:
            raise not_found("Customer onboarding workflow")
        if workflow.status != WorkflowStatus.ACTIVE:
            raise bad_request("Customer onboarding workflow is not active.")
        return workflow

    async def _execution(
        self, customer_id: UUID, *, active_only: bool
    ) -> WorkflowExecution | None:
        workflow = await self._workflow()
        statement = select(WorkflowExecution).where(
            WorkflowExecution.tenant_id == self.tenant_id,
            WorkflowExecution.workflow_id == workflow.id,
            WorkflowExecution.entity_type == CUSTOMER_ONBOARDING_ENTITY_TYPE,
            WorkflowExecution.entity_id == customer_id,
        )
        if active_only:
            statement = statement.where(
                WorkflowExecution.status.in_(_ACTIVE_EXECUTION_STATUSES)
            )
        statement = statement.order_by(WorkflowExecution.created_at.desc())
        return await self.db.scalar(statement)

    async def start(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        await self._require_customer(customer_id)
        workflow = await self._workflow()
        current = await self._execution(customer_id, active_only=True)
        if current is not None:
            if current.status == WorkflowExecutionStatus.FAILED:
                raise bad_request(
                    "Customer onboarding has failed. Retry the "
                    "existing onboarding process."
                )
            raise bad_request("Customer onboarding is already in progress.")
        return await self.workflow_service.start_execution(
            workflow.id,
            WorkflowExecutionCreate(
                entity_type=CUSTOMER_ONBOARDING_ENTITY_TYPE,
                entity_id=customer_id,
                context={
                    "customer_id": str(customer_id),
                    "workflow": CUSTOMER_ONBOARDING_WORKFLOW_NAME,
                },
            ),
            user_id=user_id,
            email=email,
            actor_role=actor_role,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def get(self, *, customer_id: UUID) -> WorkflowExecution:
        await self._require_customer(customer_id)
        execution = await self._execution(customer_id, active_only=False)
        if execution is None:
            raise not_found("Customer onboarding process")
        return await self.workflow_service.get_execution(execution.id)

    async def _get_in_progress(self, customer_id: UUID) -> WorkflowExecution:
        await self._require_customer(customer_id)
        execution = await self._execution(customer_id, active_only=True)
        if execution is None or execution.status != WorkflowExecutionStatus.IN_PROGRESS:
            raise bad_request("There is no in-progress onboarding process to update.")
        return execution

    async def advance(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        notes: str | None = None,
        result: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        execution = await self._get_in_progress(customer_id)
        return await self.workflow_service.advance_execution(
            execution.id,
            WorkflowAdvanceRequest(notes=notes, result=result),
            user_id=user_id,
            email=email,
            actor_role=actor_role,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def fail(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        notes: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        execution = await self._get_in_progress(customer_id)
        return await self.workflow_service.fail_execution(
            execution.id,
            user_id=user_id,
            email=email,
            actor_role=actor_role,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    async def retry(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ) -> WorkflowExecution:
        await self._require_customer(customer_id)
        execution = await self._execution(customer_id, active_only=True)
        if execution is None:
            raise not_found("Customer onboarding process")
        if execution.status != WorkflowExecutionStatus.FAILED:
            raise bad_request("Customer onboarding is not in a failed state.")
        return await self.workflow_service.retry_failed_execution(
            execution.id,
            user_id=user_id,
            email=email,
            actor_role=actor_role,
            ip_address=ip_address,
            user_agent=user_agent,
        )
