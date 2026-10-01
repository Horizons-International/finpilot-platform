from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.repositories.customer_repository import CustomerRepository
from app.repositories.workflow_execution_repository import (
    WorkflowExecutionRepository,
)
from app.repositories.workflow_repository import WorkflowRepository
from app.schemas.workflow import WorkflowAdvanceRequest, WorkflowExecutionCreate
from app.services.audit_service import AuditService
from app.services.workflow_service import WorkflowService
from app.utils.enums import (
    UserRole,
    WorkflowExecutionStatus,
)
from app.utils.errors import bad_request, not_found

CUSTOMER_ONBOARDING_WORKFLOW_NAME = "Customer Onboarding"
CUSTOMER_ONBOARDING_ENTITY_TYPE = "customer"


class CustomerOnboardingService:
    def __init__(
        self,
        db: Session,
        workflow_service: WorkflowService,
    ) -> None:
        self.db = db
        self.workflow_service = workflow_service

        self.customer_repository = CustomerRepository(db)
        self.workflow_repository = WorkflowRepository(db)
        self.execution_repository = WorkflowExecutionRepository(db)
        self.audit_service = AuditService(db)

    def _get_customer(
        self,
        customer_id: UUID,
    ) -> Customer:
        customer = self.customer_repository.get_by_id(
            customer_id,
        )

        if customer is None:
            raise not_found("Customer")

        return customer

    def _get_onboarding_workflow(self):
        workflow = self.workflow_repository.get_by_name(
            CUSTOMER_ONBOARDING_WORKFLOW_NAME,
        )

        if workflow is None:
            raise not_found(
                "Customer onboarding workflow",
            )

        if workflow.status.value != "ACTIVE":
            raise bad_request(
                "Customer onboarding workflow is not active.",
            )

        return workflow

    def _get_existing_execution(
        self,
        customer_id: UUID,
    ):
        workflow = self._get_onboarding_workflow()

        return self.execution_repository.get_active_for_entity(
            workflow_id=workflow.id,
            entity_type=CUSTOMER_ONBOARDING_ENTITY_TYPE,
            entity_id=customer_id,
        )

    def start(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        ip_address: str | None = None,
        user_agent: str | None = None,
        actor_role: UserRole,
    ):
        self._get_customer(customer_id)

        workflow = self._get_onboarding_workflow()

        existing_execution = self.execution_repository.get_active_for_entity(
            workflow_id=workflow.id,
            entity_type=CUSTOMER_ONBOARDING_ENTITY_TYPE,
            entity_id=customer_id,
        )

        if existing_execution is not None:
            if existing_execution.status == WorkflowExecutionStatus.FAILED:
                raise bad_request(
                    "Customer onboarding has failed. "
                    "Retry the existing onboarding process."
                )

            raise bad_request("Customer onboarding is already in progress.")

        data = WorkflowExecutionCreate(
            entity_type=CUSTOMER_ONBOARDING_ENTITY_TYPE,
            entity_id=customer_id,
            context={
                "customer_id": str(customer_id),
                "workflow": CUSTOMER_ONBOARDING_WORKFLOW_NAME,
            },
        )

        return self.workflow_service.start_execution(
            workflow_id=workflow.id,
            data=data,
            user_id=user_id,
            email=email,
            actor_role=actor_role,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def get(
        self,
        *,
        customer_id: UUID,
    ):
        self._get_customer(customer_id)

        workflow = self._get_onboarding_workflow()

        execution = self.execution_repository.get_latest_for_entity(
            workflow_id=workflow.id,
            entity_type=CUSTOMER_ONBOARDING_ENTITY_TYPE,
            entity_id=customer_id,
        )

        if execution is None:
            raise not_found(
                "Customer onboarding process",
            )

        return execution

    def advance(
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
    ):
        execution = self._get_in_progress_execution(
            customer_id,
        )

        return self.workflow_service.advance_execution(
            execution.id,
            user_id=user_id,
            email=email,
            actor_role=actor_role,
            data=WorkflowAdvanceRequest(
                notes=notes,
                result=result,
            ),
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def fail(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        notes: str | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ):
        execution = self._get_in_progress_execution(
            customer_id,
        )

        return self.workflow_service.fail_execution(
            execution.id,
            user_id=user_id,
            email=email,
            actor_role=actor_role,
            notes=notes,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def retry(
        self,
        *,
        customer_id: UUID,
        user_id: UUID,
        email: str,
        actor_role: UserRole,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ):
        workflow = self._get_onboarding_workflow()

        execution = self.execution_repository.get_active_for_entity(
            workflow_id=workflow.id,
            entity_type=CUSTOMER_ONBOARDING_ENTITY_TYPE,
            entity_id=customer_id,
        )

        if execution is None:
            raise not_found(
                "Customer onboarding process",
            )

        if execution.status != WorkflowExecutionStatus.FAILED:
            raise bad_request(
                "Customer onboarding is not in a failed state.",
            )

        return self.workflow_service.retry_failed_execution(
            execution.id,
            user_id=user_id,
            email=email,
            actor_role=actor_role,
            ip_address=ip_address,
            user_agent=user_agent,
        )

    def _get_in_progress_execution(
        self,
        customer_id: UUID,
    ):
        workflow = self._get_onboarding_workflow()

        execution = self.execution_repository.get_for_entity(
            workflow_id=workflow.id,
            entity_type=CUSTOMER_ONBOARDING_ENTITY_TYPE,
            entity_id=customer_id,
            statuses={
                WorkflowExecutionStatus.IN_PROGRESS,
            },
        )

        if execution is None:
            raise bad_request(
                "Customer onboarding is not currently in progress.",
            )

        return execution
