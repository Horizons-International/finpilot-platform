from collections.abc import Callable, Generator
from uuid import UUID, uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    CustomerFeedback,
    CustomerFeedbackHistory,
    ProductRoadmapItem,
)
from app.models.tenant import Tenant
from app.utils.enums import UserRole
from tests.conftest import TestSessionLocal
from tests.helpers import authenticate_client


@pytest.fixture
def feedback_cleanup() -> Generator[
    tuple[list[UUID], list[UUID], list[UUID]],
    None,
    None,
]:
    feedback_ids: list[UUID] = []
    roadmap_ids: list[UUID] = []
    tenant_ids: list[UUID] = []
    yield feedback_ids, roadmap_ids, tenant_ids
    db: Session = TestSessionLocal()
    try:
        if feedback_ids:
            db.query(CustomerFeedbackHistory).filter(
                CustomerFeedbackHistory.feedback_id.in_(feedback_ids)
            ).execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="clean feedback integration-test history",
            ).delete(synchronize_session=False)  # fmt: skip
            db.query(CustomerFeedback).filter(
                CustomerFeedback.id.in_(feedback_ids)
            ).execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="clean feedback integration-test records",
            ).delete(synchronize_session=False)  # fmt: skip
        if tenant_ids:
            db.query(Tenant).filter(Tenant.id.in_(tenant_ids)).delete(
                synchronize_session=False
            )
        if roadmap_ids:
            db.query(CustomerFeedback).filter(
                CustomerFeedback.roadmap_item_id.in_(roadmap_ids)
            ).execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="unlink integration-test roadmap items",
            ).update(
                {CustomerFeedback.roadmap_item_id: None}, synchronize_session=False
            )
            db.query(ProductRoadmapItem).filter(
                ProductRoadmapItem.id.in_(roadmap_ids)
            ).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_customer_can_submit_feedback_and_product_team_can_prioritize_and_link_roadmap(
    client,
    create_test_user: Callable[..., object],
    feedback_cleanup,
) -> None:
    feedback_ids, roadmap_ids, _ = feedback_cleanup
    bank_user = create_test_user(
        role=UserRole.ORGANIZATION_ADMIN.value,
        email="feedback-bank-user@example.com",
    )
    authenticate_client(client, bank_user)

    response = client.post(
        "/api/v1/customer-feedback",
        json={
            "title": "Bulk verification API support",
            "category": "FEATURE_REQUEST",
            "description": (
                "Allow a single request to submit several verification checks."
            ),
        },
    )
    assert response.status_code == 201, response.text
    feedback = response.json()["data"]
    feedback_ids.append(UUID(feedback["id"]))
    assert feedback["status"] == "SUBMITTED"
    assert feedback["priority"] == "MEDIUM"

    product_user = create_test_user(
        role=UserRole.PRODUCT_MANAGER.value,
        email="feedback-product-manager@example.com",
        is_platform_admin=True,
    )
    authenticate_client(client, product_user)

    public_item_response = client.post(
        "/api/v1/customer-feedback/product/roadmap",
        json={
            "title": "Bulk verification endpoint",
            "description": "Support multiple verification requests per call.",
            "status": "PLANNED",
            "visibility": "PUBLIC",
            "target_release": "2027.1",
        },
    )
    assert public_item_response.status_code == 201, public_item_response.text
    public_item = public_item_response.json()["data"]
    roadmap_ids.append(UUID(public_item["id"]))

    internal_item_response = client.post(
        "/api/v1/customer-feedback/product/roadmap",
        json={
            "title": "Internal delivery dependency",
            "visibility": "INTERNAL",
        },
    )
    assert internal_item_response.status_code == 201, internal_item_response.text
    internal_item = internal_item_response.json()["data"]
    roadmap_ids.append(UUID(internal_item["id"]))

    update = client.patch(
        f"/api/v1/customer-feedback/product/{feedback['id']}",
        json={
            "status": "PLANNED",
            "priority": "HIGH",
            "roadmap_item_id": str(UUID(internal_item["id"])),
            "notes": "Multiple customers requested this capability.",
        },
    )
    assert update.status_code == 200, update.text
    updated = update.json()["data"]
    assert updated["status"] == "PLANNED"
    assert updated["priority"] == "HIGH"
    assert updated["roadmap_item_title"] == "Internal delivery dependency"

    timeline = client.get(f"/api/v1/customer-feedback/product/{feedback['id']}/history")
    assert timeline.status_code == 200, timeline.text
    event_types = {row["event_type"] for row in timeline.json()["data"]}
    assert {
        "CREATED",
        "STATUS_CHANGED",
        "PRIORITY_CHANGED",
        "ROADMAP_LINK_CHANGED",
    } <= event_types

    # Customer-facing users can view public roadmap items, but not internal ones.
    authenticate_client(client, bank_user)

    public_roadmap = client.get("/api/v1/customer-feedback/roadmap")
    assert public_roadmap.status_code == 200, public_roadmap.text

    public_titles = {row["title"] for row in public_roadmap.json()["data"]}
    assert "Bulk verification endpoint" in public_titles
    assert "Internal delivery dependency" not in public_titles

    # Internal roadmap details must not be exposed to the bank tenant.
    tenant_read = client.get(f"/api/v1/customer-feedback/{feedback['id']}")
    assert tenant_read.status_code == 200, tenant_read.text
    assert tenant_read.json()["data"]["roadmap_item_title"] is None
    assert tenant_read.json()["data"]["roadmap_item_id"] is None


def test_product_manager_role_without_platform_scope_cannot_read_all_feedback(
    client,
    create_test_user: Callable[..., object],
) -> None:
    product_user = create_test_user(
        role=UserRole.PRODUCT_MANAGER.value,
        email="feedback-product-local@example.com",
        is_platform_admin=False,
    )
    authenticate_client(client, product_user)
    response = client.get("/api/v1/customer-feedback/product")
    assert response.status_code == 403, response.text


def test_customer_feedback_is_tenant_scoped(
    client,
    create_test_user: Callable[..., object],
    feedback_cleanup,
) -> None:
    feedback_ids, _, tenant_ids = feedback_cleanup
    # Create a synthetic foreign tenant and feedback row without creating a user
    # in that tenant, so the test can completely clean it up afterward.
    setup_db: Session = TestSessionLocal()
    tenant = Tenant(
        name="Feedback Isolation Tenant",
        code=f"FB-ISO-{uuid4().hex[:10]}",
    )
    setup_db.add(tenant)
    setup_db.commit()
    setup_db.refresh(tenant)
    foreign_feedback = CustomerFeedback(
        tenant_id=tenant.id,
        title="Foreign tenant feature request",
        category="FEATURE_REQUEST",
        description="This row must not be visible to another tenant.",
        priority="MEDIUM",
        status="SUBMITTED",
    )
    setup_db.add(foreign_feedback)
    setup_db.commit()
    setup_db.refresh(foreign_feedback)
    foreign_tenant_id = tenant.id
    tenant_ids.append(foreign_tenant_id)
    foreign_feedback_id = foreign_feedback.id
    setup_db.close()
    feedback_ids.append(foreign_feedback_id)

    try:
        default_db: Session = TestSessionLocal()
        try:
            default_tenant = default_db.scalar(
                select(Tenant).where(Tenant.code == "DEFAULT")
            )
            assert default_tenant is not None
            default_tenant_id = default_tenant.id
        finally:
            default_db.close()
        default_user = create_test_user(
            role=UserRole.ORGANIZATION_ADMIN.value,
            email="feedback-default-tenant@example.com",
            tenant_id=default_tenant_id,
        )
        authenticate_client(client, default_user)
        cross_tenant_read = client.get(
            f"/api/v1/customer-feedback/{foreign_feedback_id}"
        )
        assert cross_tenant_read.status_code == 404, cross_tenant_read.text

        product_user = create_test_user(
            role=UserRole.PRODUCT_MANAGER.value,
            email="feedback-cross-tenant-product-manager@example.com",
            is_platform_admin=True,
        )
        authenticate_client(client, product_user)
        product_list = client.get(
            "/api/v1/customer-feedback/product",
            params={"tenant_id": str(foreign_tenant_id)},
        )
        assert product_list.status_code == 200, product_list.text
        assert [row["id"] for row in product_list.json()["data"]] == [
            str(foreign_feedback_id)
        ]

        product_update = client.patch(
            f"/api/v1/customer-feedback/product/{foreign_feedback_id}",
            json={
                "status": "UNDER_REVIEW",
                "priority": "CRITICAL",
                "notes": "Triaged by the central product team.",
            },
        )
        assert product_update.status_code == 200, product_update.text
        assert product_update.json()["data"]["status"] == "UNDER_REVIEW"
        assert product_update.json()["data"]["priority"] == "CRITICAL"
    finally:
        cleanup_db: Session = TestSessionLocal()
        try:
            cleanup_db.query(CustomerFeedbackHistory).filter(
                CustomerFeedbackHistory.feedback_id == foreign_feedback_id
            ).execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="clean feedback tenant-isolation history",
            ).delete(synchronize_session=False)  # fmt: skip
            cleanup_db.query(CustomerFeedback).filter(
                CustomerFeedback.id == foreign_feedback_id
            ).execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason="clean feedback tenant-isolation row",
            ).delete(synchronize_session=False)  # fmt: skip
            cleanup_db.query(Tenant).filter(Tenant.id == foreign_tenant_id).delete(
                synchronize_session=False
            )
            cleanup_db.commit()
            if foreign_tenant_id in tenant_ids:
                tenant_ids.remove(foreign_tenant_id)
        finally:
            cleanup_db.close()
