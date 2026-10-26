"""Customer feedback workflows with tenant-safe product-team review."""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Iterator
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_feedback import (
    CustomerFeedback,
    CustomerFeedbackHistory,
    ProductRoadmapItem,
)
from app.repositories.customer_feedback_repository import CustomerFeedbackRepository
from app.schemas.customer_feedback import (
    CustomerFeedbackCreate,
    CustomerFeedbackUpdate,
    ProductRoadmapItemCreate,
    ProductRoadmapItemUpdate,
)
from app.utils.errors import bad_request, not_found


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CustomerFeedbackService:
    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("The session is already bound to a different tenant.")
        self.tenant_id = tenant_id
        db.info["tenant_id"] = tenant_id
        self.repository = CustomerFeedbackRepository(db, tenant_id)

    @contextmanager
    def _tenant_scope(self, tenant_id: UUID) -> Iterator[None]:
        """Temporarily scope ORM writes to the authorized feedback owner's tenant."""
        previous = self.db.info.get("tenant_id")
        self.db.info["tenant_id"] = tenant_id
        try:
            yield
        finally:
            if previous is None:
                self.db.info.pop("tenant_id", None)
            else:
                self.db.info["tenant_id"] = previous

    def _roadmap_item(
        self, item_id: UUID | None, *, public_only: bool
    ) -> ProductRoadmapItem | None:
        if item_id is None:
            return None
        item = self.repository.get_roadmap_item(item_id)
        if item is None or (public_only and item.visibility != "PUBLIC"):
            raise bad_request("The selected roadmap item is unavailable.")
        return item

    def _append_history(
        self,
        feedback: CustomerFeedback,
        *,
        event_type: str,
        old_value: str | None,
        new_value: str | None,
        actor_id: UUID | None,
        notes: str | None = None,
    ) -> None:
        repository = (
            self.repository
            if self.repository.tenant_id == feedback.tenant_id
            else CustomerFeedbackRepository(self.db, feedback.tenant_id)
        )
        repository.add_history(
            CustomerFeedbackHistory(
                tenant_id=feedback.tenant_id,
                feedback_id=feedback.id,
                event_type=event_type,
                old_value=old_value,
                new_value=new_value,
                changed_by=actor_id,
                notes=notes,
            )
        )

    @staticmethod
    def serialize_feedback(
        feedback: CustomerFeedback, *, product_team: bool = False
    ) -> dict:
        roadmap_item = feedback.roadmap_item
        roadmap_title = None
        roadmap_item_id = None
        if roadmap_item is not None and (
            roadmap_item.visibility == "PUBLIC" or product_team
        ):
            roadmap_title = roadmap_item.title
            roadmap_item_id = feedback.roadmap_item_id
        return {
            "id": feedback.id,
            "tenant_id": feedback.tenant_id,
            "title": feedback.title,
            "category": feedback.category,
            "description": feedback.description,
            "priority": feedback.priority,
            "status": feedback.status,
            "submitted_by": feedback.submitted_by,
            "reviewed_by": feedback.reviewed_by,
            "reviewed_at": feedback.reviewed_at,
            "roadmap_item_id": roadmap_item_id,
            "roadmap_item_title": roadmap_title,
            "created_at": feedback.created_at,
            "updated_at": feedback.updated_at,
        }

    def create_feedback(
        self, payload: CustomerFeedbackCreate, *, actor_id: UUID
    ) -> CustomerFeedback:
        self._roadmap_item(payload.roadmap_item_id, public_only=True)
        feedback = CustomerFeedback(
            tenant_id=self.tenant_id,
            title=payload.title,
            category=payload.category,
            description=payload.description,
            priority="MEDIUM",
            status="SUBMITTED",
            submitted_by=actor_id,
            roadmap_item_id=payload.roadmap_item_id,
        )
        try:
            self.repository.create_feedback(feedback)
            self._append_history(
                feedback,
                event_type="CREATED",
                old_value=None,
                new_value="SUBMITTED",
                actor_id=actor_id,
            )
            self.db.commit()
            self.db.refresh(feedback)
            return feedback
        except Exception:
            self.db.rollback()
            raise

    def get_feedback(self, feedback_id: UUID) -> CustomerFeedback:
        feedback = self.repository.get_for_tenant(feedback_id)
        if feedback is None:
            raise not_found("Customer feedback")
        return feedback

    def list_tenant_feedback(
        self, *, status_value: str | None = None, limit: int = 100
    ) -> list[CustomerFeedback]:
        return self.repository.list_for_tenant(status_value=status_value, limit=limit)

    def list_product_feedback(
        self,
        *,
        tenant_id: UUID | None = None,
        status_value: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        limit: int = 100,
    ) -> list[CustomerFeedback]:
        return self.repository.list_for_product_team(
            tenant_id=tenant_id,
            status_value=status_value,
            category=category,
            priority=priority,
            limit=limit,
        )

    def update_feedback(
        self,
        feedback_id: UUID,
        payload: CustomerFeedbackUpdate,
        *,
        actor_id: UUID,
        product_team: bool = False,
    ) -> CustomerFeedback:
        feedback = (
            self.repository.get_for_product_team(feedback_id)
            if product_team
            else self.repository.get_for_tenant(feedback_id)
        )
        if feedback is None:
            raise not_found("Customer feedback")

        roadmap_item_id = (
            payload.roadmap_item_id
            if "roadmap_item_id" in payload.model_fields_set
            else feedback.roadmap_item_id
        )
        if (
            "roadmap_item_id" in payload.model_fields_set
            and roadmap_item_id is not None
        ):
            self._roadmap_item(roadmap_item_id, public_only=not product_team)

        try:
            with self._tenant_scope(feedback.tenant_id):
                notes_recorded = False
                if "status" in payload.model_fields_set:
                    new_status = str(payload.status)
                    if new_status != feedback.status:
                        self._append_history(
                            feedback,
                            event_type="STATUS_CHANGED",
                            old_value=feedback.status,
                            new_value=new_status,
                            actor_id=actor_id,
                            notes=payload.notes,
                        )
                        notes_recorded = bool(payload.notes)
                        feedback.status = new_status
                if "priority" in payload.model_fields_set:
                    new_priority = str(payload.priority)
                    if new_priority != feedback.priority:
                        self._append_history(
                            feedback,
                            event_type="PRIORITY_CHANGED",
                            old_value=feedback.priority,
                            new_value=new_priority,
                            actor_id=actor_id,
                            notes=payload.notes,
                        )
                        notes_recorded = notes_recorded or bool(payload.notes)
                        feedback.priority = new_priority
                if "roadmap_item_id" in payload.model_fields_set:
                    old_item_id = feedback.roadmap_item_id
                    if roadmap_item_id != old_item_id:
                        self._append_history(
                            feedback,
                            event_type="ROADMAP_LINK_CHANGED",
                            old_value=str(old_item_id) if old_item_id else None,
                            new_value=str(roadmap_item_id) if roadmap_item_id else None,
                            actor_id=actor_id,
                            notes=payload.notes,
                        )
                        notes_recorded = notes_recorded or bool(payload.notes)
                        feedback.roadmap_item_id = roadmap_item_id
                if payload.notes and not notes_recorded:
                    self._append_history(
                        feedback,
                        event_type="REVIEW_NOTE",
                        old_value=None,
                        new_value=None,
                        actor_id=actor_id,
                        notes=payload.notes,
                    )
                if product_team:
                    feedback.reviewed_by = actor_id
                    feedback.reviewed_at = _utcnow()
                self.db.commit()
                self.db.refresh(feedback)
            return feedback
        except Exception:
            self.db.rollback()
            raise

    def list_history(
        self, feedback_id: UUID, *, product_team: bool = False
    ) -> list[CustomerFeedbackHistory]:
        feedback = (
            self.repository.get_for_product_team(feedback_id)
            if product_team
            else self.repository.get_for_tenant(feedback_id)
        )
        if feedback is None:
            raise not_found("Customer feedback")
        if product_team:
            return self.repository.history_for_product_team(feedback_id)
        return self.repository.history_for_tenant(feedback_id)

    def create_roadmap_item(
        self, payload: ProductRoadmapItemCreate, *, actor_id: UUID
    ) -> ProductRoadmapItem:
        item = ProductRoadmapItem(
            title=payload.title,
            description=payload.description,
            status=payload.status,
            visibility=payload.visibility,
            target_release=payload.target_release,
            created_by=actor_id,
        )
        self.db.add(item)
        self.db.commit()
        self.db.refresh(item)
        return item

    def list_roadmap_items(
        self, *, product_team: bool = False
    ) -> list[ProductRoadmapItem]:
        return self.repository.list_roadmap(public_only=not product_team)

    def update_roadmap_item(
        self, item_id: UUID, payload: ProductRoadmapItemUpdate
    ) -> ProductRoadmapItem:
        item = self.repository.get_roadmap_item(item_id)
        if item is None:
            raise not_found("Product roadmap item")
        changes = payload.model_dump(exclude_unset=True)
        for field, value in changes.items():
            if field in {"title", "description", "target_release"} and isinstance(
                value, str
            ):
                value = value.strip() or None
            setattr(item, field, value)
        self.db.commit()
        self.db.refresh(item)
        return item

    def summary(self, *, tenant_id: UUID | None = None) -> dict[str, int]:
        statement = select(
            func.count(CustomerFeedback.id).label("total"),
            func.count(CustomerFeedback.id)
            .filter(CustomerFeedback.status.in_(["SUBMITTED", "UNDER_REVIEW"]))
            .label("awaiting_review"),
            func.count(CustomerFeedback.id)
            .filter(CustomerFeedback.status.in_(["ACCEPTED", "PLANNED"]))
            .label("accepted_or_planned"),
            func.count(CustomerFeedback.id)
            .filter(CustomerFeedback.status == "IN_PROGRESS")
            .label("in_progress"),
            func.count(CustomerFeedback.id)
            .filter(CustomerFeedback.status == "COMPLETED")
            .label("completed"),
            func.count(CustomerFeedback.id)
            .filter(CustomerFeedback.status.in_(["DECLINED", "DUPLICATE"]))
            .label("declined_or_duplicate"),
            func.count(CustomerFeedback.id)
            .filter(CustomerFeedback.priority.in_(["HIGH", "CRITICAL"]))
            .label("critical_or_high_priority"),
            func.count(CustomerFeedback.id)
            .filter(CustomerFeedback.roadmap_item_id.is_not(None))
            .label("linked_to_roadmap"),
        ).select_from(CustomerFeedback)
        if tenant_id is not None:
            statement = statement.where(CustomerFeedback.tenant_id == tenant_id)
        scope_reason = (
            "aggregate feedback totals with an explicit tenant filter"
            if tenant_id is not None
            else "authorized product-team feedback dashboard aggregation across tenants"
        )
        row = self.db.execute(
            statement.execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=scope_reason,
            )
        ).one()
        return {
            "total_submissions": int(row.total or 0),
            "awaiting_review": int(row.awaiting_review or 0),
            "accepted_or_planned": int(row.accepted_or_planned or 0),
            "in_progress": int(row.in_progress or 0),
            "completed": int(row.completed or 0),
            "declined_or_duplicate": int(row.declined_or_duplicate or 0),
            "critical_or_high_priority": int(row.critical_or_high_priority or 0),
            "linked_to_roadmap": int(row.linked_to_roadmap or 0),
        }
