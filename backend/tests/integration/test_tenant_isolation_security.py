"""Security regression tests for tenant isolation enforcement."""

from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import delete, select, text, update
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.jobs import report_export_worker
from app.models.audit_log import AuditLog
from app.models.compliance_case import ComplianceCase
from app.models.customer import Customer
from app.models.document import CustomerDocument
from app.models.report_export import ReportExport
from app.models.risk_score_threshold import RiskScoreThreshold
from app.models.system_configuration import SystemConfiguration
from app.models.task import Task
from app.models.user import UserRole
from app.models.verification_case import IdentityVerificationCase
from app.models.verification_document_type import VerificationDocumentType
from app.reporting.data_service import ReportingDataService
from app.repositories.compliance_case_repository import ComplianceCaseRepository
from app.repositories.document_repository import CustomerDocumentRepository
from app.repositories.task_repository import TaskRepository
from app.schemas.report_exports import ReportFilters
from app.schemas.verification_case import VerificationCaseStatusUpdate
from app.services.compliance_service import ComplianceService
from app.services.customer_service import CustomerService
from app.services.document_service import DocumentService
from app.services.report_export_service import ReportExportService
from app.services.system_configuration_service import SystemConfigurationService
from app.services.task_service import TaskService
from app.services.verification_case_assignment_service import (
    VerificationCaseAssignmentService,
)
from app.services.verification_service import VerificationService
from app.storages.local_storage import LocalStorage
from app.utils.enums import (
    AuditEventType,
    ComplianceCasePriority,
    ComplianceCaseStatus,
    ComplianceCaseType,
    CustomerStatus,
    ReportExportFormat,
    ReportExportStatus,
    ReportType,
    SystemConfigurationCategory,
    SystemConfigurationStatus,
    TaskPriority,
    TaskStatus,
    VerificationStatus,
    VerificationType,
)
from tests.helpers import authenticate_client


def _audit_log(db_session, *, user_id, tenant_id, resource_type, resource_id):
    db_session.info["tenant_id"] = tenant_id
    return (
        db_session.query(AuditLog)
        .filter(
            AuditLog.user_id == user_id,
            AuditLog.tenant_id == tenant_id,
            AuditLog.event_type == AuditEventType.ACCESS_DENIED,
            AuditLog.resource_type == resource_type,
            AuditLog.resource_id == resource_id,
        )
        .order_by(AuditLog.timestamp.desc())
        .first()
    )


def test_orm_query_fails_closed_without_trusted_tenant_context(db_session):
    """Production reads fail closed when an authenticated tenant binding is lost."""
    db_session.info.pop("allow_unscoped_tenant_operations", None)
    db_session.info.pop("tenant_id", None)
    with pytest.raises(RuntimeError, match="Tenant context is required"):
        db_session.query(Customer).all()
    with pytest.raises(RuntimeError, match="Raw SQL"):
        db_session.execute(text("SELECT * FROM customers"))
    with pytest.raises(RuntimeError, match="tenant_scope_reason"):
        db_session.query(Customer).execution_options(skip_tenant_filter=True).all()

    # The deliberately global reference tables remain accessible without a
    # tenant binding; this package does not add tenant columns to them.
    db_session.query(VerificationDocumentType).all()
    db_session.query(RiskScoreThreshold).all()

    db_session.info["allow_unscoped_tenant_operations"] = True
    db_session.info["tenant_user_id"] = uuid4()
    with pytest.raises(RuntimeError, match="no tenant context"):
        db_session.query(Customer).all()


def test_orm_bulk_update_and_delete_are_tenant_scoped(
    db_session,
    create_test_tenant,
    create_test_customer,
):
    tenant_a = create_test_tenant(code=f"FILTER-A-{uuid4().hex[:8].upper()}")
    tenant_b = create_test_tenant(code=f"FILTER-B-{uuid4().hex[:8].upper()}")
    customer_a = create_test_customer(
        tenant_id=tenant_a.id,
        email=f"scope-a-{uuid4()}@example.com",
    )
    customer_b = create_test_customer(
        tenant_id=tenant_b.id,
        email=f"scope-b-{uuid4()}@example.com",
    )

    db_session.info["tenant_id"] = tenant_a.id
    db_session.info["tenant_user_id"] = uuid4()

    # Scalar SELECTs and legacy Query.count() wrappers are scoped too. The count
    # form is particularly important because its outer SELECT has no ORM mapper.
    assert db_session.scalars(select(Customer.id)).all() == [customer_a.id]
    assert db_session.query(Customer).count() == 1
    assert db_session.query(Customer.id).count() == 1

    # Even when the caller's WHERE clause includes IDs from both tenants, the
    # listener adds the active tenant predicate to bulk UPDATE and DELETE.
    db_session.query(Customer).filter(
        Customer.id.in_([customer_a.id, customer_b.id])
    ).update({Customer.status: CustomerStatus.SUSPENDED}, synchronize_session=False)
    db_session.commit()

    stored_a = db_session.query(Customer).filter(Customer.id == customer_a.id).first()
    assert stored_a is not None
    assert stored_a.status == CustomerStatus.SUSPENDED

    stored_b_unscoped = (
        db_session.query(Customer)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="verify cross-tenant bulk update regression test",
        )
        .filter(Customer.id == customer_b.id)
        .first()
    )
    assert stored_b_unscoped is not None
    assert stored_b_unscoped.status == CustomerStatus.NEW

    db_session.query(Customer).filter(
        Customer.id.in_([customer_a.id, customer_b.id])
    ).delete(synchronize_session=False)
    db_session.commit()

    remaining_a = (
        db_session.query(Customer)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="verify cross-tenant bulk delete regression test",
        )
        .filter(Customer.id == customer_a.id)
        .first()
    )
    remaining_b = (
        db_session.query(Customer)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="verify cross-tenant bulk delete regression test",
        )
        .filter(Customer.id == customer_b.id)
        .first()
    )
    assert remaining_a is None
    assert remaining_b is not None

    # Core DML against a tenant table is scoped too; it cannot bypass ORM query
    # filtering merely by targeting the table object instead of the mapped class.
    db_session.execute(
        update(Customer.__table__)
        .where(Customer.__table__.c.id == customer_b.id)
        .values(phone_number="+249900000000")
    )
    db_session.commit()
    core_checked_b = (
        db_session.query(Customer)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="verify core DML tenant scope regression test",
        )
        .filter(Customer.id == customer_b.id)
        .first()
    )
    assert core_checked_b is not None
    assert core_checked_b.phone_number != "+249900000000"

    db_session.execute(
        delete(Customer.__table__).where(Customer.__table__.c.id == customer_b.id)
    )
    db_session.commit()
    core_deleted_b = (
        db_session.query(Customer)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="verify core DELETE tenant scope regression test",
        )
        .filter(Customer.id == customer_b.id)
        .first()
    )
    assert core_deleted_b is not None


def test_related_records_cannot_cross_tenant_boundaries(
    db_session,
    create_test_tenant,
    create_test_user,
    create_test_customer,
):
    tenant_a = create_test_tenant(code=f"REL-A-{uuid4().hex[:8].upper()}")
    tenant_b = create_test_tenant(code=f"REL-B-{uuid4().hex[:8].upper()}")
    user_b = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"related-b-{uuid4()}@example.com",
        tenant_id=tenant_b.id,
    )
    customer_b = create_test_customer(
        tenant_id=tenant_b.id,
        email=f"related-customer-b-{uuid4()}@example.com",
    )
    case_b = IdentityVerificationCase(
        tenant_id=tenant_b.id,
        customer_id=customer_b.id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.PENDING,
    )
    db_session.add(case_b)
    db_session.commit()
    db_session.refresh(case_b)

    task_repo = TaskRepository(db_session, tenant_id=tenant_a.id)
    with pytest.raises(ValueError, match="assignee does not belong"):
        task_repo.create(
            Task(
                tenant_id=tenant_a.id,
                title="Must not reference another tenant's user",
                priority=TaskPriority.MEDIUM,
                status=TaskStatus.NEW,
                assigned_to=user_b.id,
            )
        )

    compliance_repo = ComplianceCaseRepository(db_session, tenant_id=tenant_a.id)
    with pytest.raises(ValueError, match="customer does not belong"):
        compliance_repo.create(
            ComplianceCase(
                tenant_id=tenant_a.id,
                customer_id=customer_b.id,
                case_type=ComplianceCaseType.AML_ALERT,
                priority=ComplianceCasePriority.MEDIUM,
                status=ComplianceCaseStatus.OPEN,
            )
        )

    document_repo = CustomerDocumentRepository(db_session, tenant_id=tenant_a.id)
    with pytest.raises(ValueError, match="document customer does not belong"):
        document_repo.create(
            CustomerDocument(
                tenant_id=tenant_a.id,
                customer_id=customer_b.id,
                verification_case_id=case_b.id,
                document_type_id=uuid4(),
                file_reference="tenant-test-file",
                file_name="test.pdf",
                file_type="application/pdf",
                file_size=1,
                uploaded_by=user_b.id,
            )
        )


def test_dirty_and_deleted_cross_tenant_records_are_rejected(
    db_session,
    create_test_tenant,
    create_test_customer,
):
    tenant_a = create_test_tenant(code=f"MUTATE-A-{uuid4().hex[:8].upper()}")
    tenant_b = create_test_tenant(code=f"MUTATE-B-{uuid4().hex[:8].upper()}")
    customer_b = create_test_customer(
        tenant_id=tenant_b.id,
        email=f"mutate-b-{uuid4()}@example.com",
    )
    db_session.info["tenant_id"] = tenant_a.id
    db_session.info["tenant_user_id"] = uuid4()

    cross_tenant_customer = (
        db_session.query(Customer)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="load cross-tenant fixture to verify mutation guard",
        )
        .filter(Customer.id == customer_b.id)
        .first()
    )
    assert cross_tenant_customer is not None
    cross_tenant_customer.phone_number = "+249900000001"
    with pytest.raises(ValueError, match="outside the active tenant"):
        db_session.flush()
    db_session.rollback()

    # Reassigning the tenant_id to the current tenant must not allow a caller to
    # transfer a row they originally loaded from another tenant.
    cross_tenant_customer = (
        db_session.query(Customer)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=(
                "load cross-tenant fixture to verify tenant transfer guard"
            ),
        )
        .filter(Customer.id == customer_b.id)
        .first()
    )
    assert cross_tenant_customer is not None
    cross_tenant_customer.tenant_id = tenant_a.id
    cross_tenant_customer.phone_number = "+249900000002"
    with pytest.raises(ValueError, match="previously owned by another tenant"):
        db_session.flush()
    db_session.rollback()

    cross_tenant_customer = (
        db_session.query(Customer)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="load cross-tenant fixture to verify delete guard",
        )
        .filter(Customer.id == customer_b.id)
        .first()
    )
    assert cross_tenant_customer is not None
    db_session.delete(cross_tenant_customer)
    with pytest.raises(ValueError, match="outside the active tenant"):
        db_session.flush()
    db_session.rollback()


def test_cross_tenant_customer_get_is_audited(
    client,
    db_session,
    create_test_tenant,
    create_test_user,
    create_test_customer,
):
    tenant_a = create_test_tenant(code=f"AUDIT-A-{uuid4().hex[:8].upper()}")
    tenant_b = create_test_tenant(code=f"AUDIT-B-{uuid4().hex[:8].upper()}")
    user_a = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"audit-a-{uuid4()}@example.com",
        tenant_id=tenant_a.id,
    )
    customer_b = create_test_customer(
        tenant_id=tenant_b.id,
        email=f"audit-b-customer-{uuid4()}@example.com",
    )

    authenticate_client(client, user_a)
    response = client.get(f"/api/v1/customers/{customer_b.id}")

    assert response.status_code == 404
    audit_log = _audit_log(
        db_session,
        user_id=user_a.id,
        tenant_id=tenant_a.id,
        resource_type="customer",
        resource_id=customer_b.id,
    )
    assert audit_log is not None


def test_cross_tenant_access_to_required_entities_is_audited(
    db_session,
    create_test_tenant,
    create_test_user,
    create_test_customer,
):
    """Resource detail lookups deny and audit all required entity categories."""
    tenant_a = create_test_tenant(code=f"DENY-A-{uuid4().hex[:8].upper()}")
    tenant_b = create_test_tenant(code=f"DENY-B-{uuid4().hex[:8].upper()}")
    user_a = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"deny-a-{uuid4()}@example.com",
        tenant_id=tenant_a.id,
    )
    user_b = create_test_user(
        role=UserRole.REVIEWER,
        email=f"deny-b-{uuid4()}@example.com",
        tenant_id=tenant_b.id,
    )
    customer_b = create_test_customer(
        tenant_id=tenant_b.id,
        email=f"deny-customer-{uuid4()}@example.com",
    )

    # Create resources while this is still a trusted, unbound test session.
    verification_case = IdentityVerificationCase(
        tenant_id=tenant_b.id,
        customer_id=customer_b.id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.PENDING,
    )
    compliance_case = ComplianceCase(
        tenant_id=tenant_b.id,
        customer_id=customer_b.id,
        case_type=ComplianceCaseType.AML_ALERT,
        priority=ComplianceCasePriority.MEDIUM,
        status=ComplianceCaseStatus.OPEN,
        description="Cross-tenant isolation test record",
    )
    task = Task(
        tenant_id=tenant_b.id,
        title="Cross-tenant isolation test task",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.NEW,
    )
    configuration = SystemConfiguration(
        tenant_id=tenant_b.id,
        key=f"tenant.test.{uuid4().hex}",
        value={"enabled": True},
        category=SystemConfigurationCategory.SLA,
        status=SystemConfigurationStatus.ACTIVE,
        updated_by=user_b.id,
    )
    report_export = ReportExport(
        tenant_id=tenant_b.id,
        report_type=ReportType.CUSTOMER,
        format=ReportExportFormat.CSV,
        requested_by=user_b.id,
        filters={},
        status=ReportExportStatus.REQUESTED,
    )
    db_session.add_all(
        [verification_case, compliance_case, task, configuration, report_export]
    )
    db_session.commit()
    db_session.refresh(verification_case)
    db_session.refresh(compliance_case)
    db_session.refresh(task)
    db_session.refresh(configuration)
    db_session.refresh(report_export)
    customer_b_id = customer_b.id
    verification_case_id = verification_case.id
    compliance_case_id = compliance_case.id
    task_id = task.id
    configuration_id = configuration.id
    report_export_id = report_export.id
    user_a_id = user_a.id
    user_b_id = user_b.id
    user_a_email = user_a.email

    # Bind this session to tenant A before calling tenant-aware services.
    db_session.info["tenant_id"] = tenant_a.id
    db_session.info["tenant_user_id"] = user_a.id
    db_session.info["tenant_user_email"] = user_a.email

    with pytest.raises(HTTPException) as customer_error:
        CustomerService(db_session, tenant_a.id).get_customer(customer_b_id)
    assert customer_error.value.status_code == 404

    with pytest.raises(HTTPException) as verification_error:
        VerificationService(db_session, tenant_a.id).get_cases_by_customer(
            customer_b_id
        )
    assert verification_error.value.status_code == 404

    document_id = uuid4()
    with pytest.raises(HTTPException) as document_error:
        DocumentService(
            db_session,
            LocalStorage(settings.STORAGE_PATH),
            tenant_id=tenant_a.id,
            actor_user_id=user_a.id,
            actor_email=user_a.email,
        ).get_document(
            customer_id=customer_b_id,
            verification_case_id=verification_case_id,
            document_id=document_id,
        )
    assert document_error.value.status_code == 404

    with pytest.raises(HTTPException) as compliance_error:
        ComplianceService(db_session, tenant_a.id).get_case(compliance_case_id)
    assert compliance_error.value.status_code == 404

    with pytest.raises(HTTPException) as task_error:
        TaskService(db_session, tenant_a.id).get_task(
            task_id,
            user_id=user_a_id,
            role=UserRole.ADMINISTRATOR,
        )
    assert task_error.value.status_code == 404

    with pytest.raises(HTTPException) as configuration_error:
        SystemConfigurationService(db_session, tenant_a.id).get_by_id(configuration_id)
    assert configuration_error.value.status_code == 404

    with pytest.raises(HTTPException) as report_error:
        ReportExportService(
            db_session,
            LocalStorage(settings.STORAGE_PATH),
            tenant_id=tenant_a.id,
        ).get_export(export_id=report_export_id)
    assert report_error.value.status_code == 404

    expected = [
        ("customer", customer_b_id),
        ("customer", customer_b_id),  # verification collection is customer-scoped
        ("customer_document", document_id),
        ("compliance_case", compliance_case_id),
        ("task", task_id),
        ("system_configuration", configuration_id),
        ("report_export", report_export_id),
    ]
    for resource_type, resource_id in expected:
        assert (
            _audit_log(
                db_session,
                user_id=user_a_id,
                tenant_id=tenant_a.id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
            is not None
        )

    # Explicitly exercise a forged verification-case ID under a tenant-A customer
    # to check the audit record's resource type is the case, not the customer.
    customer_a = create_test_customer(
        tenant_id=tenant_a.id,
        email=f"deny-a-customer-{uuid4()}@example.com",
    )
    customer_a_id = customer_a.id
    verification_case_a = IdentityVerificationCase(
        tenant_id=tenant_a.id,
        customer_id=customer_a_id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.PENDING,
    )
    db_session.add(verification_case_a)
    db_session.commit()
    db_session.refresh(verification_case_a)
    verification_case_a_id = verification_case_a.id

    with pytest.raises(HTTPException) as verification_case_error:
        VerificationService(db_session, tenant_a.id).update_status(
            customer_id=customer_a_id,
            case_id=verification_case_id,
            status_data=VerificationCaseStatusUpdate(
                status=VerificationStatus.APPROVED
            ),
            user_id=user_a_id,
            email=user_a_email,
        )
    assert verification_case_error.value.status_code == 404
    assert (
        _audit_log(
            db_session,
            user_id=user_a_id,
            tenant_id=tenant_a.id,
            resource_type="verification_case",
            resource_id=verification_case_id,
        )
        is not None
    )

    # Attempts to link task/compliance/verification resources to another
    # tenant's user are denied and audited as well.
    with pytest.raises(HTTPException) as task_assignee_error:
        TaskService(db_session, tenant_a.id)._get_active_user(user_b_id)
    assert task_assignee_error.value.status_code == 404

    with pytest.raises(HTTPException) as compliance_assignee_error:
        ComplianceService(db_session, tenant_a.id)._get_tenant_user(user_b_id)
    assert compliance_assignee_error.value.status_code == 404

    with pytest.raises(HTTPException) as reviewer_error:
        VerificationCaseAssignmentService(db_session, tenant_a.id).assign_case(
            customer_id=customer_a_id,
            verification_case_id=verification_case_a_id,
            reviewer_id=user_b_id,
            assigned_by=user_a_id,
            assigned_by_email=user_a_email,
        )
    assert reviewer_error.value.status_code == 404
    assert (
        _audit_log(
            db_session,
            user_id=user_a_id,
            tenant_id=tenant_a.id,
            resource_type="user",
            resource_id=user_b_id,
        )
        is not None
    )


def test_report_export_worker_binds_tenant_before_processing(
    monkeypatch,
    db_session,
    create_test_tenant,
    create_test_user,
):
    original_install_tenant_filter = report_export_worker.install_tenant_filter
    install_calls = []

    def track_filter_installation():
        install_calls.append(True)
        original_install_tenant_filter()

    monkeypatch.setattr(
        report_export_worker,
        "install_tenant_filter",
        track_filter_installation,
    )

    tenant = create_test_tenant(code=f"WORKER-{uuid4().hex[:8].upper()}")
    user = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"worker-export-{uuid4()}@example.com",
        tenant_id=tenant.id,
    )
    export = ReportExport(
        tenant_id=tenant.id,
        report_type=ReportType.CUSTOMER,
        format=ReportExportFormat.CSV,
        requested_by=user.id,
        filters={},
        status=ReportExportStatus.REQUESTED,
    )
    db_session.add(export)
    db_session.commit()
    db_session.refresh(export)
    export_id = export.id

    worker_session_factory = sessionmaker(
        bind=db_session.get_bind(),
        autoflush=False,
        autocommit=False,
        expire_on_commit=False,
    )
    monkeypatch.setattr(report_export_worker, "SessionLocal", worker_session_factory)
    monkeypatch.setattr(report_export_worker, "LocalStorage", lambda _path: object())

    processed = {}

    def fake_process_export(service, *, export_id):
        processed["tenant_id"] = service.db.info.get("tenant_id")
        claimed_export = service.repository.get_by_id(export_id)
        assert claimed_export is not None
        processed["status"] = claimed_export.status
        return claimed_export

    monkeypatch.setattr(ReportExportService, "process_export", fake_process_export)

    assert report_export_worker.run_report_export_worker_once() == 1
    assert install_calls, "the standalone worker must install tenant enforcement"
    assert processed["tenant_id"] == tenant.id
    assert processed["status"] == ReportExportStatus.PROCESSING

    db_session.expire_all()
    stored_export = (
        db_session.query(ReportExport)
        .execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason="verify report worker claim regression test",
        )
        .filter(ReportExport.id == export_id)
        .first()
    )
    assert stored_export is not None
    assert stored_export.tenant_id == tenant.id
    assert stored_export.status == ReportExportStatus.PROCESSING


def test_tenant_api_lists_and_mutations_do_not_expose_other_tenant_resources(
    client,
    db_session,
    create_test_tenant,
    create_test_user,
    create_test_customer,
):
    tenant_a = create_test_tenant(code=f"API-A-{uuid4().hex[:8].upper()}")
    tenant_b = create_test_tenant(code=f"API-B-{uuid4().hex[:8].upper()}")
    user_a = create_test_user(
        role=UserRole.ADMINISTRATOR,
        email=f"api-tenant-a-{uuid4()}@example.com",
        tenant_id=tenant_a.id,
    )
    customer_b = create_test_customer(
        tenant_id=tenant_b.id,
        email=f"api-tenant-b-customer-{uuid4()}@example.com",
    )
    verification_case_b = IdentityVerificationCase(
        tenant_id=tenant_b.id,
        customer_id=customer_b.id,
        verification_type=VerificationType.IDENTITY,
        status=VerificationStatus.PENDING,
    )
    compliance_case_b = ComplianceCase(
        tenant_id=tenant_b.id,
        customer_id=customer_b.id,
        case_type=ComplianceCaseType.AML_ALERT,
        priority=ComplianceCasePriority.MEDIUM,
        status=ComplianceCaseStatus.OPEN,
        description="private-tenant-b-compliance-record",
    )
    task_b = Task(
        tenant_id=tenant_b.id,
        title="private-tenant-b-task",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.NEW,
    )
    configuration_b = SystemConfiguration(
        tenant_id=tenant_b.id,
        key=f"private.tenant.b.{uuid4().hex}",
        value={"secret_setting": "tenant-b-only"},
        category=SystemConfigurationCategory.SLA,
        status=SystemConfigurationStatus.ACTIVE,
        updated_by=None,
    )
    report_export_b = ReportExport(
        tenant_id=tenant_b.id,
        report_type=ReportType.CUSTOMER,
        format=ReportExportFormat.CSV,
        requested_by=None,
        filters={},
        status=ReportExportStatus.REQUESTED,
    )
    db_session.add_all(
        [
            verification_case_b,
            compliance_case_b,
            task_b,
            configuration_b,
            report_export_b,
        ]
    )
    db_session.commit()
    for entity in (
        verification_case_b,
        compliance_case_b,
        task_b,
        configuration_b,
        report_export_b,
    ):
        db_session.refresh(entity)

    authenticate_client(client, user_a)

    # Lists must never serialize another tenant's resource identifiers or data.
    response = client.get("/api/v1/customers")
    assert response.status_code == 200
    assert customer_b.email not in response.text

    response = client.get(f"/api/v1/customers/{customer_b.id}/verification-cases")
    assert response.status_code == 404
    response = client.get(
        "/api/v1/customers/{}/verification-cases/{}/documents".format(
            customer_b.id, verification_case_b.id
        )
    )
    assert response.status_code == 404

    response = client.get("/api/v1/compliance-cases")
    assert response.status_code == 200
    assert str(compliance_case_b.id) not in response.text
    assert "private-tenant-b-compliance-record" not in response.text

    response = client.get("/api/v1/tasks")
    assert response.status_code == 200
    assert str(task_b.id) not in response.text
    assert "private-tenant-b-task" not in response.text

    response = client.get("/api/v1/system-configurations")
    assert response.status_code == 200
    assert configuration_b.key not in response.text
    assert "tenant-b-only" not in response.text

    response = client.get("/api/v1/reports/exports")
    assert response.status_code == 200
    assert str(report_export_b.id) not in response.text

    # Detail, mutation, and download attempts reveal no cross-tenant existence.
    assert (
        client.get(f"/api/v1/compliance-cases/{compliance_case_b.id}").status_code
        == 404
    )
    assert (
        client.put(
            f"/api/v1/compliance-cases/{compliance_case_b.id}",
            json={"description": "tenant-a-forged-update", "status": "OPEN"},
        ).status_code
        == 404
    )
    assert client.get(f"/api/v1/tasks/{task_b.id}").status_code == 404
    assert (
        client.put(
            f"/api/v1/tasks/{task_b.id}",
            json={
                "title": "tenant-a-forged-update",
                "assigned_to": str(user_a.id),
                "status": "NEW",
            },
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/system-configurations/{configuration_b.id}").status_code
        == 404
    )
    assert (
        client.patch(
            f"/api/v1/system-configurations/{configuration_b.id}/status",
            json={"status": "INACTIVE"},
        ).status_code
        == 404
    )
    assert (
        client.get(f"/api/v1/reports/exports/{report_export_b.id}").status_code == 404
    )
    assert (
        client.get(f"/api/v1/reports/exports/{report_export_b.id}/download").status_code
        == 404
    )

    # A cross-tenant export download and the mutation attempts must be audited.
    db_session.info["tenant_id"] = tenant_a.id
    db_session.info["tenant_user_id"] = user_a.id
    for resource_type, resource_id in (
        ("compliance_case", compliance_case_b.id),
        ("task", task_b.id),
        ("system_configuration", configuration_b.id),
        ("report_export", report_export_b.id),
    ):
        assert (
            _audit_log(
                db_session,
                user_id=user_a.id,
                tenant_id=tenant_a.id,
                resource_type=resource_type,
                resource_id=resource_id,
            )
            is not None
        )


def test_operational_report_task_rows_are_tenant_scoped(
    db_session,
    create_test_tenant,
):
    """Report rows/counts must be safe even without the global ORM listener."""
    tenant_a = create_test_tenant(code=f"REPORT-A-{uuid4().hex[:8].upper()}")
    tenant_b = create_test_tenant(code=f"REPORT-B-{uuid4().hex[:8].upper()}")

    task_a = Task(
        tenant_id=tenant_a.id,
        title="tenant-a-operational-task",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.NEW,
    )
    task_b = Task(
        tenant_id=tenant_b.id,
        title="tenant-b-private-operational-task",
        priority=TaskPriority.MEDIUM,
        status=TaskStatus.NEW,
    )
    db_session.add_all([task_a, task_b])
    db_session.commit()
    db_session.refresh(task_a)
    db_session.refresh(task_b)

    # This direct session has allow_unscoped_tenant_operations enabled and no
    # active tenant_id. It therefore proves the report service's own predicates
    # are sufficient; it cannot pass merely because app.main installed a hook.
    reporting = ReportingDataService(db_session, tenant_id=tenant_a.id)
    filters = ReportFilters()
    assert reporting._count_task_rows(filters) == 1

    report = reporting.build_report(
        report_type=ReportType.OPERATIONAL_PERFORMANCE,
        filters=filters,
    )
    task_ids = {row[1] for row in report.rows if row[0] == "TASK"}
    task_titles = {row[2] for row in report.rows if row[0] == "TASK"}

    assert task_a.id in task_ids
    assert task_b.id not in task_ids
    assert "tenant-a-operational-task" in task_titles
    assert "tenant-b-private-operational-task" not in task_titles
