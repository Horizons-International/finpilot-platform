"""Business rules for customer lifecycle, usage, support and health scoring."""

from calendar import monthrange
from datetime import date, datetime, timezone
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.customer_success import (
    CustomerSuccessHistory,
    CustomerSuccessProfile,
    CustomerSuccessSupportInteraction,
    CustomerSuccessUsageSnapshot,
)
from app.models.subscription import Subscription, SubscriptionUsageCounter
from app.models.tenant import Tenant
from app.models.user import User
from app.repositories.customer_success_repository import CustomerSuccessRepository
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class CustomerSuccessService:
    """Use cases for one owner tenant; all profiles are tenant-filtered."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        self.db = db
        self.tenant_id = tenant_id
        existing_tenant = db.info.get("tenant_id")
        if existing_tenant is not None and existing_tenant != tenant_id:
            raise ValueError("The database session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.repository = CustomerSuccessRepository(db, tenant_id)

    def _require_profile(self, profile_id: UUID) -> CustomerSuccessProfile:
        profile = self.repository.get_profile(profile_id)
        if profile is None:
            # Don't disclose whether a profile exists in another tenant.
            raise not_found("Customer success profile")
        return profile

    def _validate_manager(self, user_id: UUID | None) -> None:
        if user_id is None:
            return
        user = self.db.scalar(
            select(User).where(User.id == user_id, User.tenant_id == self.tenant_id)
        )
        if (
            user is None
            or user.is_deleted
            or getattr(user.status, "value", user.status) != UserStatus.ACTIVE.value
        ):
            raise bad_request(
                "Assigned customer success manager must be an active user "
                "in this tenant."
            )

    def _history(
        self,
        profile: CustomerSuccessProfile,
        actor_id: UUID | None,
        event_type: str,
        title: str,
        details: str | None = None,
        event_data: dict[str, object] | None = None,
    ) -> None:
        self.repository.add_history(
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

    def _recalculate_health(self, profile: CustomerSuccessProfile) -> tuple[int, str]:
        """Recalculate a deterministic 0-100 score from documented risk factors."""
        old_score = profile.health_score
        old_band = profile.health_band
        score = 100
        score -= _ACCOUNT_PENALTIES[profile.account_status]
        score -= _STAGE_PENALTIES[profile.implementation_stage]

        usage = self.repository.latest_usage(profile.id)
        if usage is not None:
            if usage.licensed_users > 0:
                adoption = usage.active_users / usage.licensed_users
                if adoption < 0.25:
                    score -= 20
                elif adoption < 0.50:
                    score -= 12
                elif adoption < 0.75:
                    score -= 6
            if usage.available_features > 0:
                feature_adoption = usage.active_features / usage.available_features
                if feature_adoption < 0.25:
                    score -= 10
                elif feature_adoption < 0.50:
                    score -= 5
            if usage.api_call_limit and usage.api_call_limit > 0:
                api_utilization = usage.api_calls / usage.api_call_limit
                if usage.api_calls == 0:
                    score -= 8
                elif api_utilization < 0.05:
                    score -= 5
                elif api_utilization >= 0.95:
                    score -= 5
            if (date.today() - usage.period_end).days > 90:
                score -= 5
        else:
            # Missing instrumentation should be visible, but is not treated as
            # proof of customer failure; account managers can add snapshots.
            score -= 5

        open_interactions = [
            item
            for item in self.repository.list_interactions(profile.id)
            if item.status not in {"RESOLVED", "CLOSED"}
        ]
        if open_interactions:
            worst = max(
                (_SEVERITY_PENALTIES[item.severity] for item in open_interactions),
                default=0,
            )
            score -= worst

        if profile.last_contacted_at is None:
            score -= 5
        else:
            contacted = profile.last_contacted_at
            if contacted.tzinfo is None:
                contacted = contacted.replace(tzinfo=timezone.utc)
            days_since_contact = max(0, (_utcnow() - contacted).days)
            if days_since_contact > 90:
                score -= 15
            elif days_since_contact > 60:
                score -= 10
            elif days_since_contact > 30:
                score -= 5

        profile.health_score = max(0, min(100, score))
        profile.health_band = (
            "HEALTHY"
            if profile.health_score >= 80
            else (
                "NEEDS_ATTENTION"
                if profile.health_score >= 60  # fmt: skip
                else "AT_RISK"
            )
        )
        profile.health_score_updated_at = _utcnow()
        self.db.flush()
        return old_score, old_band

    def _record_health_change(
        self,
        profile: CustomerSuccessProfile,
        actor_id: UUID | None,
        previous: tuple[int, str],
    ) -> None:
        old_score, old_band = previous
        if old_score != profile.health_score or old_band != profile.health_band:
            self._history(
                profile,
                actor_id,
                "HEALTH_SCORE_UPDATED",
                "Customer health score recalculated",
                f"Health changed from {old_score} ({old_band}) to "
                f"{profile.health_score} ({profile.health_band}).",
                {
                    "previous_score": old_score,
                    "previous_band": old_band,
                    "health_score": profile.health_score,
                    "health_band": profile.health_band,
                },
            )

    def list_profiles(
        self,
        *,
        account_status: str | None = None,
        health_band: str | None = None,
        assigned_manager_id: UUID | None = None,
    ) -> list[CustomerSuccessProfile]:
        return self.repository.list_profiles(
            account_status=account_status,
            health_band=health_band,
            assigned_manager_id=assigned_manager_id,
        )

    def summary(self) -> dict[str, int]:
        profiles = self.repository.list_profiles()
        bands = [profile.health_band for profile in profiles]
        return {
            "total_accounts": len(profiles),
            "healthy_accounts": bands.count("HEALTHY"),
            "accounts_needing_attention": bands.count("NEEDS_ATTENTION"),
            "at_risk_accounts": bands.count("AT_RISK"),
            "churned_accounts": sum(
                profile.account_status == "CHURNED" for profile in profiles
            ),
        }

    def get_profile(self, profile_id: UUID) -> CustomerSuccessProfile:
        return self._require_profile(profile_id)

    def create_profile(
        self,
        payload: CustomerSuccessProfileCreate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessProfile:
        customer_tenant = self.db.scalar(
            select(Tenant).where(Tenant.id == payload.customer_tenant_id)
        )
        if customer_tenant is None:
            raise bad_request(
                "customer_tenant_id does not identify an existing tenant."
            )
        if (
            self.db.scalar(
                select(CustomerSuccessProfile.id).where(
                    CustomerSuccessProfile.tenant_id == self.tenant_id,
                    CustomerSuccessProfile.customer_tenant_id
                    == payload.customer_tenant_id,
                )
            )
            is not None
        ):
            raise conflict(
                "A customer success profile already exists for this account."
            )
        self._validate_manager(payload.assigned_manager_id)
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
        self.db.flush()
        self._recalculate_health(profile)
        self._history(
            profile,
            actor_id,
            "PROFILE_CREATED",
            "Customer success profile created",
            f"Lifecycle profile created for {customer_tenant.name}.",
            {"customer_tenant_id": str(customer_tenant.id)},
        )
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def update_profile(
        self,
        profile_id: UUID,
        payload: CustomerSuccessProfileUpdate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessProfile:
        profile = self._require_profile(profile_id)
        changes = payload.model_dump(exclude_unset=True)
        self._validate_manager(
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
        history_events: list[tuple[str, str, dict[str, object]]] = []
        for field, value in changes.items():
            old_value = getattr(profile, field)
            if old_value == value:
                continue
            setattr(profile, field, value)
            if field in tracked:
                event_type, title = tracked[field]
                history_events.append(
                    (
                        event_type,
                        title,
                        {
                            "previous": (
                                str(old_value) if old_value is not None else None
                            ),
                            "current": str(value) if value is not None else None,
                        },
                    )
                )
        if not history_events and not any(
            getattr(profile, field) != value for field, value in changes.items()
        ):
            # Do not create an artificial timeline event for an unchanged model.
            return profile
        for event_type, title, data in history_events:
            self._history(profile, actor_id, event_type, title, event_data=data)
        previous_health = self._recalculate_health(profile)
        self._record_health_change(profile, actor_id, previous_health)
        self.db.commit()
        self.db.refresh(profile)
        return profile

    def add_usage_snapshot(
        self,
        profile_id: UUID,
        payload: CustomerSuccessUsageSnapshotCreate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessUsageSnapshot:
        profile = self._require_profile(profile_id)
        existing = self.db.scalar(
            select(CustomerSuccessUsageSnapshot.id).where(
                CustomerSuccessUsageSnapshot.tenant_id == self.tenant_id,
                CustomerSuccessUsageSnapshot.profile_id == profile_id,
                CustomerSuccessUsageSnapshot.period_start == payload.period_start,
            )
        )
        if existing is not None:
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
        self.db.flush()
        self._history(
            profile,
            actor_id,
            "USAGE_SNAPSHOT_RECORDED",
            "Customer usage snapshot recorded",
            (
                f"Usage period {payload.period_start.isoformat()} to "
                f"{payload.period_end.isoformat()} recorded."
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
        previous_health = self._recalculate_health(profile)
        self._record_health_change(profile, actor_id, previous_health)
        self.db.commit()
        self.db.refresh(snapshot)
        return snapshot

    def capture_subscription_usage(
        self,
        profile_id: UUID,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessUsageSnapshot:
        """Import an account-scoped usage sample from the linked customer tenant.

        These deliberate cross-tenant reads are narrowly filtered to the one
        ``customer_tenant_id`` attached to an authorized customer-success profile.
        ``skip_tenant_filter`` is required because the active session belongs to
        the relationship owner, not the customer being measured.
        """
        profile = self._require_profile(profile_id)
        target_tenant_id = profile.customer_tenant_id
        scope_reason = (
            "customer-success manager imports subscription usage for the customer "
            "tenant explicitly linked to this profile"
        )
        subscription = self.db.scalar(
            select(Subscription)
            .where(
                Subscription.tenant_id == target_tenant_id,
                Subscription.status.in_(
                    [SubscriptionStatus.ACTIVE, SubscriptionStatus.TRIAL]
                ),
            )
            .order_by(Subscription.created_at.desc())
            .limit(1)
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=scope_reason,
            )
        )
        if subscription is None:
            raise bad_request(
                "The customer tenant has no active or trial subscription to import."
            )

        today = date.today()
        period_start = today.replace(day=1)
        period_end = today.replace(day=monthrange(today.year, today.month)[1])
        counter_rows = self.db.execute(
            select(SubscriptionUsageCounter.metric, SubscriptionUsageCounter.used)
            .where(
                SubscriptionUsageCounter.tenant_id == target_tenant_id,
                SubscriptionUsageCounter.period_start == period_start,
            )
            .execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=scope_reason,
            )
        ).all()
        used_by_metric = {metric: used for metric, used in counter_rows}
        active_users = (
            self.db.scalar(
                select(func.count(User.id))
                .where(
                    User.tenant_id == target_tenant_id,
                    User.status == UserStatus.ACTIVE,
                    User.is_deleted.is_(False),
                )
                .execution_options(
                    skip_tenant_filter=True,
                    tenant_scope_reason=scope_reason,
                )
            )
            or 0
        )

        limits = subscription.usage_limits or {}
        configured_user_limit = limits.get("max_users")
        # Enterprise plans may be unlimited (None); represent their current
        # active-user count as the denominator rather than inventing a quota.
        licensed_users = (
            max(active_users, int(configured_user_limit))
            if configured_user_limit is not None
            else active_users
        )
        api_call_limit_value = limits.get("api_calls")
        payload = CustomerSuccessUsageSnapshotCreate(
            period_start=period_start,
            period_end=period_end,
            active_users=active_users,
            licensed_users=licensed_users,
            api_calls=int(used_by_metric.get("api_calls", 0)),
            api_call_limit=(
                int(api_call_limit_value) if api_call_limit_value is not None else None
            ),
            active_features=0,
            available_features=0,
            source="SUBSCRIPTION_IMPORT",
        )
        return self.add_usage_snapshot(profile_id, payload, actor_id=actor_id)

    def list_usage(self, profile_id: UUID) -> list[CustomerSuccessUsageSnapshot]:
        self._require_profile(profile_id)
        return self.repository.list_usage(profile_id)

    def add_support_interaction(
        self,
        profile_id: UUID,
        payload: CustomerSuccessSupportInteractionCreate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessSupportInteraction:
        profile = self._require_profile(profile_id)
        self._validate_manager(payload.assigned_to)
        interaction = CustomerSuccessSupportInteraction(
            tenant_id=self.tenant_id,
            profile_id=profile.id,
            **payload.model_dump(),
            created_by=actor_id,
            resolved_at=_utcnow() if payload.status in {"RESOLVED", "CLOSED"} else None,
        )
        self.db.add(interaction)
        self.db.flush()
        self._history(
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
        previous_health = self._recalculate_health(profile)
        self._record_health_change(profile, actor_id, previous_health)
        self.db.commit()
        self.db.refresh(interaction)
        return interaction

    def list_support_interactions(
        self, profile_id: UUID
    ) -> list[CustomerSuccessSupportInteraction]:
        self._require_profile(profile_id)
        return self.repository.list_interactions(profile_id)

    def update_support_interaction(
        self,
        profile_id: UUID,
        interaction_id: UUID,
        payload: CustomerSuccessSupportInteractionUpdate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessSupportInteraction:
        profile = self._require_profile(profile_id)
        interaction = self.repository.get_interaction(profile_id, interaction_id)
        if interaction is None:
            raise not_found("Customer success support interaction")
        changes = payload.model_dump(exclude_unset=True)
        if "assigned_to" in changes:
            self._validate_manager(changes["assigned_to"])
        previous: dict[str, object] = {}
        for field, value in changes.items():
            old_value = getattr(interaction, field)
            if old_value == value:
                continue
            previous[field] = str(old_value) if old_value is not None else None
            setattr(interaction, field, value)
        if "status" in changes:
            if interaction.status in {"RESOLVED", "CLOSED"}:
                interaction.resolved_at = interaction.resolved_at or _utcnow()
            else:
                interaction.resolved_at = None
        if not previous:
            return interaction
        self._history(
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
        old_health = self._recalculate_health(profile)
        self._record_health_change(profile, actor_id, old_health)
        self.db.commit()
        self.db.refresh(interaction)
        return interaction

    def add_note(
        self,
        profile_id: UUID,
        payload: CustomerSuccessNoteCreate,
        *,
        actor_id: UUID,
    ) -> CustomerSuccessHistory:
        profile = self._require_profile(profile_id)
        event = CustomerSuccessHistory(
            tenant_id=self.tenant_id,
            profile_id=profile.id,
            event_type="RELATIONSHIP_NOTE_ADDED",
            title=payload.title,
            details=payload.details,
            event_data={},
            actor_id=actor_id,
        )
        self.repository.add_history(event)
        self.db.commit()
        self.db.refresh(event)
        return event

    def list_history(self, profile_id: UUID) -> list[CustomerSuccessHistory]:
        self._require_profile(profile_id)
        return self.repository.list_history(profile_id)

    def recalculate_health(
        self, profile_id: UUID, *, actor_id: UUID
    ) -> CustomerSuccessProfile:
        profile = self._require_profile(profile_id)
        old_health = self._recalculate_health(profile)
        self._record_health_change(profile, actor_id, old_health)
        self._history(
            profile,
            actor_id,
            "HEALTH_RECALCULATED",
            "Health score manually recalculated",
            f"Current score: {profile.health_score} ({profile.health_band}).",
        )
        self.db.commit()
        self.db.refresh(profile)
        return profile
