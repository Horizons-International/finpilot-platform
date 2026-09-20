from app.services.workflow_service import WorkflowValidationService
from app.utils.enums import ComplianceCaseStatus

COMPLIANCE_CASE_TRANSITIONS: dict[
    ComplianceCaseStatus,
    set[ComplianceCaseStatus],
] = {
    ComplianceCaseStatus.OPEN: {
        ComplianceCaseStatus.ASSIGNED,
    },
    ComplianceCaseStatus.ASSIGNED: {
        ComplianceCaseStatus.UNDER_REVIEW,
    },
    ComplianceCaseStatus.UNDER_REVIEW: {
        ComplianceCaseStatus.ESCALATED,
        ComplianceCaseStatus.RESOLVED,
    },
    ComplianceCaseStatus.ESCALATED: {
        ComplianceCaseStatus.UNDER_REVIEW,
    },
    ComplianceCaseStatus.RESOLVED: {
        ComplianceCaseStatus.CLOSED,
    },
    ComplianceCaseStatus.CLOSED: set(),
}


compliance_workflow_validator = WorkflowValidationService(
    COMPLIANCE_CASE_TRANSITIONS,
)
