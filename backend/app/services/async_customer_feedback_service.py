"""Native-async customer feedback and roadmap operations."""

from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer_feedback import (
    CustomerFeedback,
    CustomerFeedbackHistory,
    ProductRoadmapItem,
)
from app.schemas.customer_feedback import (
    CustomerFeedbackCreate,
    CustomerFeedbackUpdate,
    ProductRoadmapItemCreate,
    ProductRoadmapItemUpdate,
)
from app.utils.errors import bad_request, not_found

_CROSS_TENANT_REASON = "authorized platform product manager reviews tenant feedback"


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AsyncCustomerFeedbackService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError("Feedback service tenant does not match session tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    def _cross_tenant(self, statement):
        return statement.execution_options(
            skip_tenant_filter=True,
            tenant_scope_reason=_CROSS_TENANT_REASON,
        )

    async def _roadmap_item(
        self, item_id: UUID | None, *, public_only: bool
    ) -> ProductRoadmapItem | None:
        if item_id is None:
            return None
        item = await self.db.get(ProductRoadmapItem, item_id)
        if item is None or (public_only and item.visibility != "PUBLIC"):
            raise bad_request("The selected roadmap item is unavailable.")
        return item

    async def _append_history(
        self,
        feedback: CustomerFeedback,
        *,
        event_type: str,
        old_value: str | None,
        new_value: str | None,
        actor_id: UUID | None,
        notes: str | None = None,
    ) -> None:
        self.db.add(
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
        await self.db.flush()

    @staticmethod
    def serialize_feedback(
        feedback: CustomerFeedback, *, product_team: bool = False
    ) -> dict:
        item = feedback.roadmap_item
        visible = item is not None and (item.visibility == "PUBLIC" or product_team)
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
            "roadmap_item_id": feedback.roadmap_item_id if visible else None,
            "roadmap_item_title": item.title if visible else None,
            "created_at": feedback.created_at,
            "updated_at": feedback.updated_at,
        }

    async def create_feedback(
        self, payload: CustomerFeedbackCreate, *, actor_id: UUID
    ) -> CustomerFeedback:
        await self._roadmap_item(payload.roadmap_item_id, public_only=True)
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
            self.db.add(feedback)
            await self.db.flush()
            await self._append_history(
                feedback,
                event_type="CREATED",
                old_value=None,
                new_value="SUBMITTED",
                actor_id=actor_id,
            )
            await self.db.commit()
            await self.db.refresh(feedback, attribute_names=["roadmap_item"])
            return feedback
        except Exception:
            await self.db.rollback()
            raise

    async def _get_feedback(
        self, feedback_id: UUID, *, product_team: bool = False
    ) -> CustomerFeedback:
        statement = select(CustomerFeedback).where(CustomerFeedback.id == feedback_id)
        if not product_team:
            statement = statement.where(CustomerFeedback.tenant_id == self.tenant_id)
        else:
            statement = self._cross_tenant(statement)
        statement = statement.options(selectinload(CustomerFeedback.roadmap_item))
        feedback = await self.db.scalar(statement)
        if feedback is None:
            raise not_found("Customer feedback")
        return feedback

    async def get_feedback(self, feedback_id: UUID) -> CustomerFeedback:
        return await self._get_feedback(feedback_id)

    async def list_tenant_feedback(
        self, *, status_value: str | None = None, limit: int = 100
    ) -> list[CustomerFeedback]:
        statement = select(CustomerFeedback).where(
            CustomerFeedback.tenant_id == self.tenant_id
        )
        if status_value is not None:
            statement = statement.where(CustomerFeedback.status == status_value)
        statement = (
            statement.options(selectinload(CustomerFeedback.roadmap_item))
            .order_by(CustomerFeedback.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())

    async def list_product_feedback(
        self,
        *,
        tenant_id: UUID | None = None,
        status_value: str | None = None,
        category: str | None = None,
        priority: str | None = None,
        limit: int = 100,
    ) -> list[CustomerFeedback]:
        statement = self._cross_tenant(select(CustomerFeedback))
        if tenant_id is not None:
            statement = statement.where(CustomerFeedback.tenant_id == tenant_id)
        if status_value is not None:
            statement = statement.where(CustomerFeedback.status == status_value)
        if category is not None:
            statement = statement.where(CustomerFeedback.category == category)
        if priority is not None:
            statement = statement.where(CustomerFeedback.priority == priority)
        statement = (
            statement.options(selectinload(CustomerFeedback.roadmap_item))
            .order_by(CustomerFeedback.created_at.desc())
            .limit(limit)
        )
        return list((await self.db.scalars(statement)).all())

    async def update_feedback(
        self,
        feedback_id: UUID,
        payload: CustomerFeedbackUpdate,
        *,
        actor_id: UUID,
        product_team: bool = False,
    ) -> CustomerFeedback:
        feedback = await self._get_feedback(feedback_id, product_team=product_team)
        roadmap_item_id = (
            payload.roadmap_item_id
            if "roadmap_item_id" in payload.model_fields_set
            else feedback.roadmap_item_id
        )
        if (
            "roadmap_item_id" in payload.model_fields_set
            and roadmap_item_id is not None
        ):
            await self._roadmap_item(roadmap_item_id, public_only=not product_team)
        try:
            previous_tenant = self.db.info.get("tenant_id")
            if product_team:
                self.db.info["tenant_id"] = feedback.tenant_id
            notes_recorded = False
            if "status" in payload.model_fields_set:
                value = str(payload.status)
                if value != feedback.status:
                    await self._append_history(
                        feedback,
                        event_type="STATUS_CHANGED",
                        old_value=feedback.status,
                        new_value=value,
                        actor_id=actor_id,
                        notes=payload.notes,
                    )
                    notes_recorded = bool(payload.notes)
                    feedback.status = value
            if "priority" in payload.model_fields_set:
                value = str(payload.priority)
                if value != feedback.priority:
                    await self._append_history(
                        feedback,
                        event_type="PRIORITY_CHANGED",
                        old_value=feedback.priority,
                        new_value=value,
                        actor_id=actor_id,
                        notes=payload.notes,
                    )
                    notes_recorded = notes_recorded or bool(payload.notes)
                    feedback.priority = value
            if (
                "roadmap_item_id" in payload.model_fields_set
                and roadmap_item_id != feedback.roadmap_item_id
            ):
                old_id = feedback.roadmap_item_id
                await self._append_history(
                    feedback,
                    event_type="ROADMAP_LINK_CHANGED",
                    old_value=str(old_id) if old_id else None,
                    new_value=str(roadmap_item_id) if roadmap_item_id else None,
                    actor_id=actor_id,
                    notes=payload.notes,
                )
                notes_recorded = notes_recorded or bool(payload.notes)
                feedback.roadmap_item_id = roadmap_item_id
            if payload.notes and not notes_recorded:
                await self._append_history(
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
            await self.db.commit()
            await self.db.refresh(feedback)
            await self.db.refresh(feedback, attribute_names=["roadmap_item"])
            return feedback
        except Exception:
            await self.db.rollback()
            raise
        finally:
            if product_team:
                if previous_tenant is None:
                    self.db.info.pop("tenant_id", None)
                else:
                    self.db.info["tenant_id"] = previous_tenant

    async def list_history(
        self, feedback_id: UUID, *, product_team: bool = False
    ) -> list[CustomerFeedbackHistory]:
        feedback = await self._get_feedback(feedback_id, product_team=product_team)
        statement = select(CustomerFeedbackHistory).where(
            CustomerFeedbackHistory.feedback_id == feedback.id
        )
        if product_team:
            statement = self._cross_tenant(statement)
            statement = statement.where(
                CustomerFeedbackHistory.tenant_id == feedback.tenant_id
            )
        else:
            statement = statement.where(
                CustomerFeedbackHistory.tenant_id == self.tenant_id
            )
        statement = statement.order_by(CustomerFeedbackHistory.created_at.asc())
        return list((await self.db.scalars(statement)).all())

    async def create_roadmap_item(
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
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_roadmap_items(
        self, *, product_team: bool = False
    ) -> list[ProductRoadmapItem]:
        statement = select(ProductRoadmapItem)
        if not product_team:
            statement = statement.where(ProductRoadmapItem.visibility == "PUBLIC")
        return list(
            (
                await self.db.scalars(
                    statement.order_by(ProductRoadmapItem.created_at.desc())
                )
            ).all()
        )

    async def update_roadmap_item(
        self, item_id: UUID, payload: ProductRoadmapItemUpdate
    ) -> ProductRoadmapItem:
        item = await self.db.get(ProductRoadmapItem, item_id)
        if item is None:
            raise not_found("Product roadmap item")
        for field, value in payload.model_dump(exclude_unset=True).items():
            if field in {"title", "description", "target_release"} and isinstance(
                value, str
            ):
                value = value.strip() or None
            setattr(item, field, value)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def summary(self, *, tenant_id: UUID | None = None) -> dict[str, int]:
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
            statement = self._cross_tenant(statement)
        else:
            statement = self._cross_tenant(statement)
        row = (await self.db.execute(statement)).one()
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
