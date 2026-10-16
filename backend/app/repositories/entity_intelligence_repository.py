"""Tenant-scoped persistence operations for the entity-intelligence graph."""

from collections.abc import Iterable
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

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
from app.repositories.tenant_scoped_repository import TenantScopedRepository


class EntityIntelligenceRepository(TenantScopedRepository[EntityIntelligenceNode]):
    """Repository that prevents graph reads and writes crossing tenant boundaries."""

    def __init__(self, db: Session, tenant_id: UUID) -> None:
        super().__init__(db=db, model=EntityIntelligenceNode, tenant_id=tenant_id)

    def get_customer(self, customer_id: UUID) -> Customer | None:
        return (
            self.db.query(Customer)
            .filter(Customer.id == customer_id, Customer.tenant_id == self.tenant_id)
            .first()
        )

    def get_customers(self, customer_ids: Iterable[UUID]) -> list[Customer]:
        ids = set(customer_ids)
        if not ids:
            return []
        return (
            self.db.query(Customer)
            .filter(Customer.tenant_id == self.tenant_id, Customer.id.in_(ids))
            .all()
        )

    def list_customer_activity(
        self, customer_id: UUID, *, limit: int = 5000
    ) -> list[TransactionAnomalyActivity]:
        statement = (
            select(TransactionAnomalyActivity)
            .where(
                TransactionAnomalyActivity.tenant_id == self.tenant_id,
                TransactionAnomalyActivity.customer_id == customer_id,
            )
            .order_by(TransactionAnomalyActivity.occurred_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

    def list_customer_risk_transactions(
        self, customer_id: UUID, *, limit: int = 5000
    ) -> list[TransactionRiskTransaction]:
        statement = (
            select(TransactionRiskTransaction)
            .where(
                TransactionRiskTransaction.tenant_id == self.tenant_id,
                TransactionRiskTransaction.customer_id == customer_id,
            )
            .order_by(TransactionRiskTransaction.occurred_at.desc())
            .limit(limit)
        )
        return list(self.db.scalars(statement).all())

    def find_activities_for_beneficiaries(
        self, beneficiary_keys: set[str], *, limit: int = 10000
    ) -> list[TransactionAnomalyActivity]:
        """Find tenant-local activity sharing normalized recipient identifiers."""
        if not beneficiary_keys:
            return []
        statement = (
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
        return list(self.db.scalars(statement).all())

    def anomaly_scores_for_transactions(
        self, transaction_ids: set[UUID]
    ) -> dict[UUID, int]:
        if not transaction_ids:
            return {}
        rows = self.db.execute(
            select(
                TransactionAnomaly.transaction_id,
                func.max(TransactionAnomaly.risk_score),
            )
            .where(
                TransactionAnomaly.tenant_id == self.tenant_id,
                TransactionAnomaly.transaction_id.in_(transaction_ids),
            )
            .group_by(TransactionAnomaly.transaction_id)
        ).all()
        result: dict[UUID, int] = {}
        for transaction_id, score in rows:
            if score is not None:
                result[transaction_id] = int(score)
        return result

    def get_node_by_type_key(
        self, entity_type: str, entity_key: str
    ) -> EntityIntelligenceNode | None:
        return (
            self.query()
            .filter(
                EntityIntelligenceNode.entity_type == entity_type,
                EntityIntelligenceNode.entity_key == entity_key,
            )
            .first()
        )

    def upsert_node(
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
        node = self.get_node_by_type_key(entity_type, entity_key)
        if node is None:
            node = EntityIntelligenceNode(
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
            self.db.add(node)
            self.db.flush()
            self.db.refresh(node)
            return node

        node.label = label
        node.attributes = {**(node.attributes or {}), **(attributes or {})}
        if source_type is not None:
            node.source_type = source_type
        if source_id is not None:
            node.source_id = source_id
        node.risk_score = max(node.risk_score, risk_score)
        node.risk_level = risk_level_for_score(node.risk_score)
        if first_seen_at is not None and (
            node.first_seen_at is None or first_seen_at < node.first_seen_at
        ):
            node.first_seen_at = first_seen_at
        if last_seen_at is not None and (
            node.last_seen_at is None or last_seen_at > node.last_seen_at
        ):
            node.last_seen_at = last_seen_at
        self.db.flush()
        return node

    def upsert_relationship(
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
        owned_node_ids = {
            node_id
            for (node_id,) in self.db.query(EntityIntelligenceNode.id)
            .filter(
                EntityIntelligenceNode.tenant_id == self.tenant_id,
                EntityIntelligenceNode.id.in_({source_entity_id, target_entity_id}),
            )
            .all()
        }
        if owned_node_ids != {source_entity_id, target_entity_id}:
            raise ValueError("Both relationship endpoints must belong to this tenant.")
        if observed_count < 1:
            raise ValueError("Observed count must be at least one.")
        relationship = (
            self.db.query(EntityIntelligenceRelationship)
            .filter(
                EntityIntelligenceRelationship.tenant_id == self.tenant_id,
                EntityIntelligenceRelationship.source_entity_id == source_entity_id,
                EntityIntelligenceRelationship.target_entity_id == target_entity_id,
                EntityIntelligenceRelationship.relationship_type == relationship_type,
            )
            .first()
        )
        indicators = list(dict.fromkeys(risk_indicators or []))
        if relationship is None:
            relationship = EntityIntelligenceRelationship(
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
            self.db.add(relationship)
            self.db.flush()
            self.db.refresh(relationship)
            return relationship

        relationship.confidence = max(relationship.confidence, confidence)
        relationship.risk_score = risk_score
        relationship.risk_level = risk_level_for_score(risk_score)
        relationship.risk_indicators = indicators
        relationship.evidence = {**(relationship.evidence or {}), **(evidence or {})}
        relationship.observed_count = observed_count
        if observed_at is not None and (
            relationship.first_seen_at is None
            or observed_at < relationship.first_seen_at
        ):
            relationship.first_seen_at = observed_at
        if observed_at is not None and (
            relationship.last_seen_at is None or observed_at > relationship.last_seen_at
        ):
            relationship.last_seen_at = observed_at
        self.db.flush()
        return relationship

    def get_relationship(
        self, relationship_id: UUID
    ) -> EntityIntelligenceRelationship | None:
        return (
            self.db.query(EntityIntelligenceRelationship)
            .filter(
                EntityIntelligenceRelationship.id == relationship_id,
                EntityIntelligenceRelationship.tenant_id == self.tenant_id,
            )
            .first()
        )

    def list_relationships_connected_to(
        self, entity_ids: set[UUID], *, limit: int
    ) -> list[EntityIntelligenceRelationship]:
        if not entity_ids:
            return []
        return (
            self.db.query(EntityIntelligenceRelationship)
            .filter(
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
            .all()
        )

    def get_nodes_by_ids(self, entity_ids: set[UUID]) -> list[EntityIntelligenceNode]:
        if not entity_ids:
            return []
        return self.query().filter(EntityIntelligenceNode.id.in_(entity_ids)).all()

    def list_risk_relationships(
        self, *, min_risk_score: int = 40, limit: int = 100
    ) -> list[EntityIntelligenceRelationship]:
        return (
            self.db.query(EntityIntelligenceRelationship)
            .filter(
                EntityIntelligenceRelationship.tenant_id == self.tenant_id,
                EntityIntelligenceRelationship.risk_score >= min_risk_score,
            )
            .order_by(
                EntityIntelligenceRelationship.risk_score.desc(),
                EntityIntelligenceRelationship.updated_at.desc(),
            )
            .limit(limit)
            .all()
        )


def risk_level_for_score(score: int) -> str:
    if score >= 85:
        return "CRITICAL"
    if score >= 70:
        return "HIGH"
    if score >= 40:
        return "MEDIUM"
    return "LOW"


def shared_recipient_risk_score(distinct_customer_count: int) -> int:
    """Heuristic signal only: sharing alone does not establish criminal activity."""
    if distinct_customer_count < 2:
        return 0
    return min(100, 50 + (distinct_customer_count - 2) * 10)
