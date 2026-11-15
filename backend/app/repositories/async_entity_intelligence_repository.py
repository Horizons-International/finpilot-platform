"""Native-async, tenant-scoped persistence for the entity-intelligence graph."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.entity_intelligence import (
    EntityIntelligenceNode,
    EntityIntelligenceRelationship,
)
from app.models.transaction_anomaly import (
    TransactionAnomaly,
    TransactionAnomalyActivity,
)
from app.models.transaction_risk_analysis import TransactionRiskTransaction


def risk_level_for_score(score: int) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def shared_recipient_risk_score(distinct_customer_count: int) -> int:
    """Sharing is an investigative signal only, not proof of wrongdoing."""
    if distinct_customer_count < 2:
        return 0
    return min(100, 50 + (distinct_customer_count - 2) * 10)


def _risk_level_expression(score_expression: Any) -> Any:
    return case(
        (score_expression >= 85, "CRITICAL"),
        (score_expression >= 70, "HIGH"),
        (score_expression >= 40, "MEDIUM"),
        else_="LOW",
    )


class AsyncEntityIntelligenceRepository:
    """Persistence boundary that explicitly scopes every graph operation."""

    def __init__(self, db: AsyncSession, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("Entity repository tenant does not match session tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id

    async def get_by_id(self, entity_id: UUID) -> EntityIntelligenceNode | None:
        return await self.db.scalar(
            select(EntityIntelligenceNode).where(
                EntityIntelligenceNode.id == entity_id,
                EntityIntelligenceNode.tenant_id == self.tenant_id,
            )
        )

    async def get_customer(self, customer_id: UUID) -> Customer | None:
        return await self.db.scalar(
            select(Customer).where(
                Customer.id == customer_id,
                Customer.tenant_id == self.tenant_id,
            )
        )

    async def lock_customer(self, customer_id: UUID) -> Customer | None:
        """Serialize graph synchronization for a customer within this tenant."""
        return await self.db.scalar(
            select(Customer)
            .where(Customer.id == customer_id, Customer.tenant_id == self.tenant_id)
            .with_for_update()
        )

    async def get_customers(self, customer_ids: Iterable[UUID]) -> list[Customer]:
        ids = set(customer_ids)
        if not ids:
            return []
        result = await self.db.scalars(
            select(Customer).where(
                Customer.tenant_id == self.tenant_id,
                Customer.id.in_(ids),
            )
        )
        return list(result.all())

    async def list_customer_activity(
        self, customer_id: UUID, *, limit: int = 5000
    ) -> list[TransactionAnomalyActivity]:
        result = await self.db.scalars(
            select(TransactionAnomalyActivity)
            .where(
                TransactionAnomalyActivity.tenant_id == self.tenant_id,
                TransactionAnomalyActivity.customer_id == customer_id,
            )
            .order_by(TransactionAnomalyActivity.occurred_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def list_customer_risk_transactions(
        self, customer_id: UUID, *, limit: int = 5000
    ) -> list[TransactionRiskTransaction]:
        result = await self.db.scalars(
            select(TransactionRiskTransaction)
            .where(
                TransactionRiskTransaction.tenant_id == self.tenant_id,
                TransactionRiskTransaction.customer_id == customer_id,
            )
            .order_by(TransactionRiskTransaction.occurred_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def find_activities_for_beneficiaries(
        self, beneficiary_keys: set[str], *, limit: int = 10000
    ) -> list[TransactionAnomalyActivity]:
        """Find only this tenant's activities with matching normalized recipients."""
        if not beneficiary_keys:
            return []
        result = await self.db.scalars(
            select(TransactionAnomalyActivity)
            .where(
                TransactionAnomalyActivity.tenant_id == self.tenant_id,
                TransactionAnomalyActivity.beneficiary_id.is_not(None),
                func.lower(func.trim(TransactionAnomalyActivity.beneficiary_id)).in_(
                    beneficiary_keys
                ),
            )
            .order_by(TransactionAnomalyActivity.occurred_at.desc())
            .limit(limit)
        )
        return list(result.all())

    async def anomaly_scores_for_transactions(
        self, transaction_ids: set[UUID]
    ) -> dict[UUID, int]:
        if not transaction_ids:
            return {}
        result = await self.db.execute(
            select(
                TransactionAnomaly.transaction_id,
                func.max(TransactionAnomaly.risk_score),
            )
            .where(
                TransactionAnomaly.tenant_id == self.tenant_id,
                TransactionAnomaly.transaction_id.in_(transaction_ids),
            )
            .group_by(TransactionAnomaly.transaction_id)
        )
        scores: dict[UUID, int] = {}
        for transaction_id, score in result.all():
            if score is not None:
                scores[transaction_id] = int(score)
        return scores

    async def get_node_by_type_key(
        self, entity_type: str, entity_key: str
    ) -> EntityIntelligenceNode | None:
        return await self.db.scalar(
            select(EntityIntelligenceNode).where(
                EntityIntelligenceNode.tenant_id == self.tenant_id,
                EntityIntelligenceNode.entity_type == entity_type,
                EntityIntelligenceNode.entity_key == entity_key,
            )
        )

    async def upsert_node(
        self,
        *,
        entity_type: str,
        entity_key: str,
        label: str,
        attributes: dict[str, Any] | None = None,
        source_type: str | None = None,
        source_id: str | None = None,
        risk_score: int = 0,
        first_seen_at: datetime | None = None,
        last_seen_at: datetime | None = None,
    ) -> EntityIntelligenceNode:
        """Atomically create/update a node using its tenant/type/key constraint."""
        if not 0 <= risk_score <= 100:
            raise ValueError("Node risk score must be between 0 and 100.")
        table = EntityIntelligenceNode.__table__
        statement = pg_insert(EntityIntelligenceNode).values(
            tenant_id=self.tenant_id,
            entity_type=entity_type,
            entity_key=entity_key,
            label=label,
            attributes=attributes or {},
            source_type=source_type,
            source_id=source_id,
            risk_score=risk_score,
            risk_level=risk_level_for_score(risk_score),
            first_seen_at=first_seen_at,
            last_seen_at=last_seen_at,
        )
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            constraint="uq_entity_intelligence_nodes_tenant_type_key",
            set_={
                "label": excluded.label,
                "attributes": table.c.attributes.op("||")(excluded.attributes),
                "source_type": func.coalesce(excluded.source_type, table.c.source_type),
                "source_id": func.coalesce(excluded.source_id, table.c.source_id),
                "risk_score": func.greatest(table.c.risk_score, excluded.risk_score),
                "risk_level": _risk_level_expression(
                    func.greatest(table.c.risk_score, excluded.risk_score)
                ),
                "first_seen_at": func.least(
                    table.c.first_seen_at, excluded.first_seen_at
                ),
                "last_seen_at": func.greatest(
                    table.c.last_seen_at, excluded.last_seen_at
                ),
                "updated_at": func.now(),
            },
        )
        await self.db.execute(
            statement.execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "Tenant-scoped entity intelligence node upsert. "
                    "The repository explicitly binds tenant_id and uses the "
                    "tenant-scoped unique constraint for conflict resolution."
                ),
            )
        )
        node = await self.get_node_by_type_key(entity_type, entity_key)
        if node is None:
            raise RuntimeError("Entity node upsert did not return a persisted node.")
        return node

    async def upsert_relationship(
        self,
        *,
        source_entity_id: UUID,
        target_entity_id: UUID,
        relationship_type: str,
        confidence: float = 1.0,
        risk_score: int = 0,
        risk_indicators: list[str] | None = None,
        evidence: dict[str, Any] | None = None,
        observed_at: datetime | None = None,
        observed_count: int = 1,
    ) -> EntityIntelligenceRelationship:
        if source_entity_id == target_entity_id:
            raise ValueError("An entity cannot have a relationship to itself.")
        if observed_count < 1:
            raise ValueError("Observed count must be at least one.")
        if not 0 <= risk_score <= 100 or not 0.0 <= confidence <= 1.0:
            raise ValueError("Relationship risk score or confidence is out of range.")
        owned_result = await self.db.scalars(
            select(EntityIntelligenceNode.id).where(
                EntityIntelligenceNode.tenant_id == self.tenant_id,
                EntityIntelligenceNode.id.in_({source_entity_id, target_entity_id}),
            )
        )
        owned_node_ids = set(owned_result.all())
        if owned_node_ids != {source_entity_id, target_entity_id}:
            raise ValueError("Both relationship endpoints must belong to this tenant.")

        indicators = list(dict.fromkeys(risk_indicators or []))
        table = EntityIntelligenceRelationship.__table__
        statement = pg_insert(EntityIntelligenceRelationship).values(
            tenant_id=self.tenant_id,
            source_entity_id=source_entity_id,
            target_entity_id=target_entity_id,
            relationship_type=relationship_type,
            confidence=confidence,
            risk_score=risk_score,
            risk_level=risk_level_for_score(risk_score),
            risk_indicators=indicators,
            evidence=evidence or {},
            observed_count=observed_count,
            first_seen_at=observed_at,
            last_seen_at=observed_at,
        )
        excluded = statement.excluded
        statement = statement.on_conflict_do_update(
            constraint="uq_entity_intelligence_relationships_tenant_edge_type",
            set_={
                "confidence": func.greatest(table.c.confidence, excluded.confidence),
                "risk_score": excluded.risk_score,
                "risk_level": excluded.risk_level,
                "risk_indicators": excluded.risk_indicators,
                "evidence": table.c.evidence.op("||")(excluded.evidence),
                "observed_count": excluded.observed_count,
                "first_seen_at": func.least(
                    table.c.first_seen_at, excluded.first_seen_at
                ),
                "last_seen_at": func.greatest(
                    table.c.last_seen_at, excluded.last_seen_at
                ),
                "updated_at": func.now(),
            },
        )
        await self.db.execute(
            statement.execution_options(
                skip_tenant_filter=True,
                tenant_scope_reason=(
                    "Tenant-scoped entity intelligence node upsert. "
                    "The repository explicitly binds tenant_id and uses the "
                    "tenant-scoped unique constraint for conflict resolution."
                ),
            )
        )
        relationship = await self.db.scalar(
            select(EntityIntelligenceRelationship).where(
                EntityIntelligenceRelationship.tenant_id == self.tenant_id,
                EntityIntelligenceRelationship.source_entity_id == source_entity_id,
                EntityIntelligenceRelationship.target_entity_id == target_entity_id,
                EntityIntelligenceRelationship.relationship_type == relationship_type,
            )
        )
        if relationship is None:
            raise RuntimeError("Entity relationship upsert did not persist a row.")
        return relationship

    async def get_relationship(
        self, relationship_id: UUID
    ) -> EntityIntelligenceRelationship | None:
        return await self.db.scalar(
            select(EntityIntelligenceRelationship).where(
                EntityIntelligenceRelationship.id == relationship_id,
                EntityIntelligenceRelationship.tenant_id == self.tenant_id,
            )
        )

    async def list_relationships_connected_to(
        self, entity_ids: set[UUID], *, limit: int
    ) -> list[EntityIntelligenceRelationship]:
        if not entity_ids:
            return []
        result = await self.db.scalars(
            select(EntityIntelligenceRelationship)
            .where(
                EntityIntelligenceRelationship.tenant_id == self.tenant_id,
                or_(
                    EntityIntelligenceRelationship.source_entity_id.in_(entity_ids),
                    EntityIntelligenceRelationship.target_entity_id.in_(entity_ids),
                ),
            )
            .order_by(
                EntityIntelligenceRelationship.risk_score.desc(),
                EntityIntelligenceRelationship.updated_at.desc(),
            )
            .limit(limit)
        )
        return list(result.all())

    async def get_nodes_by_ids(
        self, entity_ids: set[UUID]
    ) -> list[EntityIntelligenceNode]:
        if not entity_ids:
            return []
        result = await self.db.scalars(
            select(EntityIntelligenceNode).where(
                EntityIntelligenceNode.tenant_id == self.tenant_id,
                EntityIntelligenceNode.id.in_(entity_ids),
            )
        )
        return list(result.all())

    async def list_risk_relationships(
        self, *, min_risk_score: int = 40, limit: int = 100
    ) -> list[EntityIntelligenceRelationship]:
        result = await self.db.scalars(
            select(EntityIntelligenceRelationship)
            .where(
                EntityIntelligenceRelationship.tenant_id == self.tenant_id,
                EntityIntelligenceRelationship.risk_score >= min_risk_score,
            )
            .order_by(
                EntityIntelligenceRelationship.risk_score.desc(),
                EntityIntelligenceRelationship.updated_at.desc(),
            )
            .limit(limit)
        )
        return list(result.all())
