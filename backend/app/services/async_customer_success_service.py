"""Native-async customer lifecycle, usage, support and health scoring."""

from calendar import monthrange
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.customer_success import (
    CustomerSuccessHistory,
    CustomerSuccessProfile,
    CustomerSuccessSupportInteraction,
    CustomerSuccessUsageSnapshot,
)
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.models.user import User
from app.schemas.customer_success import (
    CustomerSuccessNoteCreate,
    CustomerSuccessProfileCreate,
    CustomerSuccessProfileUpdate,
    CustomerSuccessSupportInteractionCreate,
    CustomerSuccessSupportInteractionUpdate,
    CustomerSuccessUsageSnapshotCreate,
)
from app.utils.enums import SubscriptionStatus, UserStatus
from app.utils.errors import bad_request, conflict, not_found

_ACCOUNT_PENALTIES = {
    "TRIAL": 0,
    "ACTIVE": 0,
    "AT_RISK": 20,
    "PAUSED": 25,
    "CHURNED": 50,
}
_STAGE_PENALTIES = {
    "NOT_STARTED": 20,
    "CONFIGURATION": 15,
    "INTEGRATION": 10,
    "TESTING": 5,
    "READY_FOR_PRODUCTION": 2,
    "LIVE": 0,
}
_SEVERITY_PENALTIES = {"LOW": 3, "MEDIUM": 8, "HIGH": 15, "CRITICAL": 25}
_CROSS_TENANT_REASON = (
    "customer success imports usage from the tenant "
    "explicitly linked to an authorized profile"
)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AsyncCustomerSuccessService:
    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active = db.info.get("tenant_id")
        if active is not None and active != tenant_id:
            raise ValueError(
                "Customer-success service tenant does not match session tenant."
            )
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    async def _profile(self, profile_id: UUID) -> CustomerSuccessProfile:
        statement = (
            select(CustomerSuccessProfile)
            .options(
                selectinload(CustomerSuccessProfile.customer_tenant),
            )
            .where(
                CustomerSuccessProfile.id == profile_id,
                # Keep your existing tenant-isolation conditions here.
            )
        )

        profile = await self.db.scalar(statement)

        if profile is None:
            raise not_found("Customer success profile")

        return profile

    async def _validate_manager(self, user_id: UUID | None) -> None:
        if user_id is None:
            return
        user = await self.db.scalar(
            select(User).where(
                User.id == user_id,
                User.tenant_id == self.tenant_id,
            )
        )
        if (
            user is None
            or user.is_deleted
            or getattr(user.status, "value", user.status) != UserStatus.ACTIVE.value
        ):
            raise bad_request(
                "Assigned customer success manager must "
                "be an active user in this tenant."
            )

    async def _history(
        self,
        profile: CustomerSuccessProfile,
        actor_id: UUID | None,
        event_type: str,
        title: str,
        details: str | None = None,
        event_data: dict[str, object] | None = None,
    ) -> None:
        self.db.add(
            CustomerSuccessHistory(
                tenant_id=self.tenant_id,
                profile_id=profile.id,
                event_type=event_type,
                title=title,
                details=details,
                event_data=event_data or {},
                actor_id=actor_id,
            )
        )
        await self.db.flush()

    async def _latest_usage(
        self, profile_id: UUID
    ) -> CustomerSuccessUsageSnapshot | None:
        return await self.db.scalar(
            select(CustomerSuccessUsageSnapshot)
            .where(
                CustomerSuccessUsageSnapshot.tenant_id == self.tenant_id,
                CustomerSuccessUsageSnapshot.profile_id == profile_id,
            )
            .order_by(
                CustomerSuccessUsageSnapshot.period_end.desc(),
                CustomerSuccessUsageSnapshot.created_at.desc(),
            )
            .limit(1)
        )

    async def _interactions(
        self, profile_id: UUID
    ) -> list[CustomerSuccessSupportInteraction]:
        result = await self.db.scalars(
            select(CustomerSuccessSupportInteraction).where(
                CustomerSuccessSupportInteraction.tenant_id == self.tenant_id,
                CustomerSuccessSupportInteraction.profile_id == profile_id,
            )
        )
        return list(result.all())

    async def _recalculate_health(
        self, profile: CustomerSuccessProfile
    ) -> tuple[int, str]:
        old = (profile.health_score, profile.health_band)
        score = (
            100
            - _ACCOUNT_PENALTIES.get(profile.account_status, 0)
            - _STAGE_PENALTIES.get(profile.implementation_stage, 0)
        )
        usage = await self._latest_usage(profile.id)
        if usage is not None:
            if usage.licensed_users > 0:
                adoption = usage.active_users / usage.licensed_users
                score -= (
                    20
                    if adoption < 0.25
                    else 12  # fmt: skip
                    if adoption < 0.50
                    else 6
                    if adoption < 0.75
                    else 0  # fmt: skip
                )
            if usage.available_features > 0:
                adoption = usage.active_features / usage.available_features
                score -= 10 if adoption < 0.25 else 5 if adoption < 0.50 else 0
            if usage.api_call_limit and usage.api_call_limit > 0:
                ratio = usage.api_calls / usage.api_call_limit
                score -= (
                    8
                    if usage.api_calls == 0
                    else 5  # fmt: skip
                    if ratio < 0.05 or ratio >= 0.95
                    else 0  # fmt: skip
                )
            if (date.today() - usage.period_end).days > 90:
                score -= 5
        else:
            score -= 5
        open_interactions = [
            item
            for item in await self._interactions(profile.id)
            if item.status not in {"RESOLVED", "CLOSED"}
        ]
        if open_interactions:
            score -= max(
                (
                    _SEVERITY_PENALTIES.get(item.severity, 0)
                    for item in open_interactions
                ),
                default=0,
            )
        if profile.last_contacted_at is None:
            score -= 5
        else:
            contacted = profile.last_contacted_at
            if contacted.tzinfo is None:
                contacted = contacted.replace(tzinfo=timezone.utc)
            days = max(0, (_utcnow() - contacted).days)
            score -= 15 if days > 90 else 10 if days > 60 else 5 if days > 30 else 0
        profile.health_score = max(0, min(100, score))
        profile.health_band = (
            "HEALTHY"
            if profile.health_score >= 80
            else "NEEDS_ATTENTION"
            if profile.health_score >= 60
            else "AT_RISK"  # fmt: skip
        )
        profile.health_score_updated_at = _utcnow()
        await self.db.flush()
        return old

    async def _record_health_change(
        self,
        profile: CustomerSuccessProfile,
        actor_id: UUID | None,
        old: tuple[int, str],
    ) -> None:
        if old != (profile.health_score, profile.health_band):
            await self._history(
                profile,
                actor_id,
                "HEALTH_SCORE_UPDATED",
                "Customer health score recalculated",
                (
                    f"Health changed from {old[0]} ({old[1]}) to {profile.health_score}"
                    f" ({profile.health_band})."
                ),
                {
                    "previous_score": old[0],
                    "previous_band": old[1],
                    "health_score": profile.health_score,
                    "health_band": profile.health_band,
                },
            )

    async def list_profiles(
        self,
        *,
        account_status: str | None = None,
        health_band: str | None = None,
        assigned_manager_id: UUID | None = None,
    ) -> list[CustomerSuccessProfile]:
        stmt = select(CustomerSuccessProfile).where(
            CustomerSuccessProfile.tenant_id == self.tenant_id
        )
        if account_status is not None:
            stmt = stmt.where(CustomerSuccessProfile.account_status == account_status)
        if health_band is not None:
            stmt = stmt.where(CustomerSuccessProfile.health_band == health_band)
        if assigned_manager_id is not None:
            stmt = stmt.where(
                CustomerSuccessProfile.assigned_manager_id == assigned_manager_id
            )
        return list(
            (
                await self.db.scalars(
                    stmt.order_by(CustomerSuccessProfile.updated_at.desc())
                )
            ).all()
        )

    async def summary(self) -> dict[str, int]:
        profiles = await self.list_profiles()
        bands = [item.health_band for item in profiles]
        return {
            "total_accounts": len(profiles),
            "healthy_accounts": bands.count("HEALTHY"),
            "accounts_needing_attention": bands.count("NEEDS_ATTENTION"),
            "at_risk_accounts": bands.count("AT_RISK"),
            "churned_accounts": sum(
                item.account_status == "CHURNED" for item in profiles
            ),
        }

    async def get_profile(self, profile_id: UUID) -> CustomerSuccessProfile:
        return await self._profile(profile_id)

    async def create_profile(
        self, payload: CustomerSuccessProfileCreate, *, actor_id: UUID
    ) -> CustomerSuccessProfile:
        customer_tenant = await self.db.scalar(
            select(Tenant)
            .where(Tenant.id == payload.customer_tenant_id)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "customer success profile links an explicitly "
                    "selected customer tenant"
                ),
            )
        )
        if customer_tenant is None:
            raise bad_request(
                "customer_tenant_id does not identify an existing tenant."
            )
        exists = await self.db.scalar(
            select(CustomerSuccessProfile.id).where(
                CustomerSuccessProfile.tenant_id == self.tenant_id,
                CustomerSuccessProfile.customer_tenant_id == payload.customer_tenant_id,
            )
        )
        if exists is not None:
            raise conflict(
                "A customer success profile already exists for this account."
            )
        await self._validate_manager(payload.assigned_manager_id)
        profile = CustomerSuccessProfile(
            tenant_id=self.tenant_id,
            customer_tenant_id=payload.customer_tenant_id,
            account_status=payload.account_status,
            implementation_stage=payload.implementation_stage,
            assigned_manager_id=payload.assigned_manager_id,
            success_plan=payload.success_plan,
            last_contacted_at=payload.last_contacted_at,
            created_by=actor_id,
        )
        self.db.add(profile)
        await self.db.flush()
        previous = await self._recalculate_health(profile)
        await self._record_health_change(profile, actor_id, previous)
        await self._history(
            profile,
            actor_id,
            "PROFILE_CREATED",
            "Customer success profile created",
            f"Lifecycle profile created for {customer_tenant.name}.",
            {"customer_tenant_id": str(customer_tenant.id)},
        )
        await self.db.commit()
        await self.db.refresh(profile)
        await self.db.refresh(
            profile,
            attribute_names=["customer_tenant"],
        )
        return profile

    async def update_profile(
        self, profile_id: UUID, payload: CustomerSuccessProfileUpdate, *, actor_id: UUID
    ) -> CustomerSuccessProfile:
        profile = await self._profile(profile_id)
        changes = payload.model_dump(exclude_unset=True)
        await self._validate_manager(
            changes.get("assigned_manager_id", profile.assigned_manager_id)
        )
        tracked = {
            "account_status": ("ACCOUNT_STATUS_CHANGED", "Account status changed"),
            "implementation_stage": (
                "IMPLEMENTATION_STAGE_CHANGED",
                "Implementation stage changed",
            ),
            "assigned_manager_id": (
                "MANAGER_ASSIGNED",
                "Customer success manager changed",
            ),
            "success_plan": ("SUCCESS_PLAN_UPDATED", "Customer success plan updated"),
            "last_contacted_at": (
                "CUSTOMER_CONTACT_RECORDED",
                "Customer contact recorded",
            ),
        }
        events: list[tuple[str, str, dict[str, object]]] = []
        changed = False
        for field, value in changes.items():
            old = getattr(profile, field)
            if old == value:
                continue
            changed = True
            setattr(profile, field, value)
            if field in tracked:
                event, title = tracked[field]
                event_data: dict[str, object] = {
                    "previous": str(old) if old is not None else None,
                    "current": str(value) if value is not None else None,
                }

                events.append((event, title, event_data))
        if not changed:
            return profile
        for event, title, data in events:
            await self._history(profile, actor_id, event, title, event_data=data)
        previous = await self._recalculate_health(profile)
        await self._record_health_change(profile, actor_id, previous)
        await self.db.commit()
        await self.db.refresh(profile)
        await self.db.refresh(
            profile,
            attribute_names=["customer_tenant"],
        )
        return profile

    async def add_usage_snapshot(
        self,
        profile_id: UUID,
        payload: CustomerSuccessUsageSnapshotCreate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessUsageSnapshot:
        profile = await self._profile(profile_id)
        exists = await self.db.scalar(
            select(CustomerSuccessUsageSnapshot.id).where(
                CustomerSuccessUsageSnapshot.tenant_id == self.tenant_id,
                CustomerSuccessUsageSnapshot.profile_id == profile_id,
                CustomerSuccessUsageSnapshot.period_start == payload.period_start,
            )
        )
        if exists is not None:
            raise conflict(
                "A usage snapshot already exists for this period start date."
            )
        snapshot = CustomerSuccessUsageSnapshot(
            tenant_id=self.tenant_id,
            profile_id=profile.id,
            **payload.model_dump(),
            recorded_by=actor_id,
        )
        self.db.add(snapshot)
        await self.db.flush()
        await self._history(
            profile,
            actor_id,
            "USAGE_SNAPSHOT_RECORDED",
            "Customer usage snapshot recorded",
            (
                f"Usage period {payload.period_start.isoformat()} to"
                f" {payload.period_end.isoformat()} recorded."
            ),
            {
                "period_start": payload.period_start.isoformat(),
                "period_end": payload.period_end.isoformat(),
                "active_users": payload.active_users,
                "licensed_users": payload.licensed_users,
                "api_calls": payload.api_calls,
                "source": payload.source,
                "active_features": payload.active_features,
                "available_features": payload.available_features,
            },
        )
        previous = await self._recalculate_health(profile)
        await self._record_health_change(profile, actor_id, previous)
        await self.db.commit()
        await self.db.refresh(snapshot)
        return snapshot

    async def capture_subscription_usage(
        self, profile_id: UUID, *, actor_id: UUID
    ) -> CustomerSuccessUsageSnapshot:
        profile = await self._profile(profile_id)
        target = profile.customer_tenant_id
        subscription = await self.db.scalar(
            select(Subscription)
            .where(
                Subscription.tenant_id == target,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
                ),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
            .execution_options(
                skip_tenant_filter=True, tenant_scope_reason=_CROSS_TENANT_REASON
            )
        )
        if subscription is None:
            raise bad_request(
                "The customer tenant has no active or trial subscription to import."
            )
        today = date.today()
        start = today.replace(day=1)
        end = today.replace(day=monthrange(today.year, today.month)[1])
        rows = (
            await self.db.execute(
                select(SubscriptionUsageCounter.metric, SubscriptionUsageCounter.used)
                .where(
                    SubscriptionUsageCounter.tenant_id == target,
                    SubscriptionUsageCounter.period_start == start,
                )
                .execution_options(
                    skip_tenant_filter=True, tenant_scope_reason=_CROSS_TENANT_REASON
                )
            )
        ).all()
        active = int(
            await self.db.scalar(
                select(func.count(User.id))
                .where(
                    User.tenant_id == target,
                    User.status == UserStatus.ACTIVE,
                    User.is_deleted.is_(False),
                )
                .execution_options(
                    skip_tenant_filter=True, tenant_scope_reason=_CROSS_TENANT_REASON
                )
            )
            or 0
        )
        used = {metric: value for metric, value in rows}
        limits = subscription.usage_limits or {}
        max_users = limits.get("max_users")
        api_call_limit_value = limits.get("api_calls")
        payload = CustomerSuccessUsageSnapshotCreate(
            period_start=start,
            period_end=end,
            active_users=active,
            licensed_users=(
                max(active, int(max_users)) if max_users is not None else active
            ),
            api_calls=int(used.get("api_calls", 0)),
            api_call_limit=(
                int(api_call_limit_value) if api_call_limit_value is not None else None
            ),
            active_features=0,
            available_features=0,
            source="SUBSCRIPTION_IMPORT",
        )
        return await self.add_usage_snapshot(profile_id, payload, actor_id=actor_id)

    async def list_usage(self, profile_id: UUID) -> list[CustomerSuccessUsageSnapshot]:
        await self._profile(profile_id)
        return list(
            (
                await self.db.scalars(
                    select(CustomerSuccessUsageSnapshot)
                    .where(
                        CustomerSuccessUsageSnapshot.tenant_id == self.tenant_id,
                        CustomerSuccessUsageSnapshot.profile_id == profile_id,
                    )
                    .order_by(CustomerSuccessUsageSnapshot.period_start.desc())
                )
            ).all()
        )

    async def add_support_interaction(
        self,
        profile_id: UUID,
        payload: CustomerSuccessSupportInteractionCreate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessSupportInteraction:
        profile = await self._profile(profile_id)
        await self._validate_manager(payload.assigned_to)
        interaction = CustomerSuccessSupportInteraction(
            tenant_id=self.tenant_id,
            profile_id=profile.id,
            **payload.model_dump(),
            created_by=actor_id,
            resolved_at=_utcnow() if payload.status in {"RESOLVED", "CLOSED"} else None,
        )
        self.db.add(interaction)
        await self.db.flush()
        await self._history(
            profile,
            actor_id,
            "SUPPORT_INTERACTION_CREATED",
            "Support interaction recorded",
            f"{interaction.subject} ({interaction.severity}, {interaction.status}).",
            {
                "support_interaction_id": str(interaction.id),
                "category": interaction.category,
                "severity": interaction.severity,
                "status": interaction.status,
            },
        )
        previous = await self._recalculate_health(profile)
        await self._record_health_change(profile, actor_id, previous)
        await self.db.commit()
        await self.db.refresh(interaction)
        return interaction

    async def list_support_interactions(
        self, profile_id: UUID
    ) -> list[CustomerSuccessSupportInteraction]:
        await self._profile(profile_id)
        return list(
            (
                await self.db.scalars(
                    select(CustomerSuccessSupportInteraction)
                    .where(
                        CustomerSuccessSupportInteraction.tenant_id == self.tenant_id,
                        CustomerSuccessSupportInteraction.profile_id == profile_id,
                    )
                    .order_by(CustomerSuccessSupportInteraction.created_at.desc())
                )
            ).all()
        )

    async def update_support_interaction(
        self,
        profile_id: UUID,
        interaction_id: UUID,
        payload: CustomerSuccessSupportInteractionUpdate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessSupportInteraction:
        profile = await self._profile(profile_id)
        interaction = await self.db.scalar(
            select(CustomerSuccessSupportInteraction).where(
                CustomerSuccessSupportInteraction.id == interaction_id,
                CustomerSuccessSupportInteraction.profile_id == profile_id,
                CustomerSuccessSupportInteraction.tenant_id == self.tenant_id,
            )
        )
        if interaction is None:
            raise not_found("Customer success support interaction")
        changes = payload.model_dump(exclude_unset=True)
        if "assigned_to" in changes:
            await self._validate_manager(changes["assigned_to"])
        previous = {}
        for field, value in changes.items():
            old = getattr(interaction, field)
            if old != value:
                previous[field] = str(old) if old is not None else None
                setattr(interaction, field, value)
        if "status" in changes:
            interaction.resolved_at = (
                interaction.resolved_at or _utcnow()
                if interaction.status in {"RESOLVED", "CLOSED"}
                else None
            )
        if not previous:
            return interaction
        await self._history(
            profile,
            actor_id,
            "SUPPORT_INTERACTION_UPDATED",
            "Support interaction updated",
            f"{interaction.subject} updated.",
            {
                "support_interaction_id": str(interaction.id),
                "previous": previous,
                "current": {
                    key: (
                        str(getattr(interaction, key))
                        if getattr(interaction, key) is not None
                        else None
                    )
                    for key in changes
                },
            },
        )
        old = await self._recalculate_health(profile)
        await self._record_health_change(profile, actor_id, old)
        await self.db.commit()
        await self.db.refresh(interaction)
        return interaction

    async def add_note(
        self, profile_id: UUID, payload: CustomerSuccessNoteCreate, *, actor_id: UUID
    ) -> CustomerSuccessHistory:
        profile = await self._profile(profile_id)
        event = CustomerSuccessHistory(
            tenant_id=self.tenant_id,
            profile_id=profile.id,
            event_type="RELATIONSHIP_NOTE_ADDED",
            title=payload.title,
            details=payload.details,
            event_data={},
            actor_id=actor_id,
        )
        self.db.add(event)
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def list_history(self, profile_id: UUID) -> list[CustomerSuccessHistory]:
        await self._profile(profile_id)
        return list(
            (
                await self.db.scalars(
                    select(CustomerSuccessHistory)
                    .where(
                        CustomerSuccessHistory.tenant_id == self.tenant_id,
                        CustomerSuccessHistory.profile_id == profile_id,
                    )
                    .order_by(CustomerSuccessHistory.created_at.desc())
                )
            ).all()
        )

    async def recalculate_health(
        self, profile_id: UUID, *, actor_id: UUID
    ) -> CustomerSuccessProfile:
        profile = await self._profile(profile_id)
        previous = await self._recalculate_health(profile)
        await self._record_health_change(profile, actor_id, previous)
        await self._history(
            profile,
            actor_id,
            "HEALTH_RECALCULATED",
            "Health score manually recalculated",
            f"Current score: {profile.health_score} ({profile.health_band}).",
        )
        await self.db.commit()
        await self.db.refresh(profile)
        await self.db.refresh(
            profile,
            attribute_names=["customer_tenant"],
        )
        return profile
