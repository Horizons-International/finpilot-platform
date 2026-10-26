"""Tenant-aware persistence queries for feedback and roadmap records."""

from uuid import UUID

from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    CustomerFeedback,
    CustomerFeedbackHistory,
    ProductRoadmapItem,
)


class CustomerFeedbackRepository:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id

    def create_feedback(self, feedback: CustomerFeedback) -> CustomerFeedback:
        if feedback.tenant_id != self.tenant_id:
            raise ValueError("Feedback tenant does not match repository tenant.")
        self.db.add(feedback)
        self.db.flush()
        return feedback

    def get_for_tenant(self, feedback_id: UUID) -> CustomerFeedback | None:
        return self.db.scalar(
            select(CustomerFeedback).where(
                CustomerFeedback.id == feedback_id,
                CustomerFeedback.tenant_id == self.tenant_id,
            )
        )

    def get_for_product_team(self, feedback_id: UUID) -> CustomerFeedback | None:
        statement = (
            select(CustomerFeedback)
            .where(CustomerFeedback.id == feedback_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "authorized product-team review of feedback by explicit feedback ID"
                ),
            )
        )
        return self.db.scalar(statement)

    def list_for_tenant(
        self,
        *,
        status_value: str | None = None,
        limit: int = 100,
    ) -> list[CustomerFeedback]:
        statement = select(CustomerFeedback).where(
            CustomerFeedback.tenant_id == self.tenant_id
        )
        if status_value is not None:
            statement = statement.where(CustomerFeedback.status == status_value)
        return list(
            self.db.scalars(
                statement.order_by(CustomerFeedback.created_at.desc()).limit(limit)
            ).all()
        )

    def list_for_product_team(
        self,
        *,
        tenant_id: UUID | None = None,
        status_value: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        limit: int = 100,
    ) -> list[CustomerFeedback]:
        statement = select(CustomerFeedback)
        if tenant_id is not None:
            statement = statement.where(CustomerFeedback.tenant_id == tenant_id)
        if status_value is not None:
            statement = statement.where(CustomerFeedback.status == status_value)
        if category is not None:
            statement = statement.where(CustomerFeedback.category == category)
        if priority is not None:
            statement = statement.where(CustomerFeedback.priority == priority)
        statement = statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=(
                "authorized product-team cross-tenant feedback review "
                "with explicit filters"
            ),
        )
        priority_order = case(
            (CustomerFeedback.priority == "CRITICAL", 4),
            (CustomerFeedback.priority == "HIGH", 3),
            (CustomerFeedback.priority == "MEDIUM", 2),
            (CustomerFeedback.priority == "LOW", 1),
            else_=0,
        )
        return list(
            self.db.scalars(
                statement.order_by(
                    priority_order.desc(), CustomerFeedback.created_at.desc()
                ).limit(limit)
            ).all()
        )

    def add_history(self, event: CustomerFeedbackHistory) -> None:
        if event.tenant_id != self.tenant_id:
            raise ValueError("History tenant does not match repository tenant.")
        self.db.add(event)
        self.db.flush()

    def history_for_tenant(self, feedback_id: UUID) -> list[CustomerFeedbackHistory]:
        statement = select(CustomerFeedbackHistory).where(
            CustomerFeedbackHistory.feedback_id == feedback_id,
            CustomerFeedbackHistory.tenant_id == self.tenant_id,
        )
        statement = statement.order_by(CustomerFeedbackHistory.created_at.asc())
        return list(self.db.scalars(statement).all())

    def history_for_product_team(
        self, feedback_id: UUID
    ) -> list[CustomerFeedbackHistory]:
        statement = (
            select(CustomerFeedbackHistory)
            .where(CustomerFeedbackHistory.feedback_id == feedback_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "authorized product-team read of a feedback lifecycle timeline"
                ),
            )
            .order_by(CustomerFeedbackHistory.created_at.asc())
        )
        return list(self.db.scalars(statement).all())

    def get_roadmap_item(self, item_id: UUID) -> ProductRoadmapItem | None:
        return self.db.get(ProductRoadmapItem, item_id)

    def list_roadmap(self, *, public_only: bool = False) -> list[ProductRoadmapItem]:
        statement = select(ProductRoadmapItem)
        if public_only:
            statement = statement.where(ProductRoadmapItem.visibility == "PUBLIC")
        statement = statement.order_by(ProductRoadmapItem.created_at.desc())
        return list(self.db.scalars(statement).all())
