"""Small, database-free checks for compliance document status conventions."""

from app.models.compliance_document import (
    ComplianceApprovalStatus,
    ComplianceDocumentStatus,
)


def test_compliance_document_lifecycle_status_values_are_stable() -> None:
    assert {value.value for value in ComplianceDocumentStatus} == {
        "DRAFT",
        "IN_REVIEW",
        "APPROVED",
        "REJECTED",
        "ARCHIVED",
    }


def test_compliance_approval_decisions_are_explicit() -> None:
    assert {value.value for value in ComplianceApprovalStatus} == {
        "PENDING",
        "APPROVED",
        "REJECTED",
    }
