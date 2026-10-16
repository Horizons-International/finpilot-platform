"""Entity graph synchronization, traversal, and relationship-risk heuristics."""

from collections import defaultdict
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.entity_intelligence import (
    EntityIntelligenceNode,
    EntityIntelligenceRelationship,
)
from app.models.transaction_anomaly import TransactionAnomalyActivity
from app.repositories.entity_intelligence_repository import (
    EntityIntelligenceRepository,
    risk_level_for_score,
    shared_recipient_risk_score,
)
from app.schemas.entity_intelligence import (
    EntityGraphResponse,
    EntityIntelligenceSyncResponse,
    EntityNodeCreate,
    EntityNodeResponse,
    EntityRelationshipCreate,
    EntityRelationshipResponse,
)
from app.utils.errors import bad_request, not_found


class EntityIntelligenceService:
    """Build and query the graph within one authenticated tenant."""

    def __init__(self, db: Session, *, tenant_id: UUID) -> None:
        active_tenant = db.info.get("tenant_id")
        if active_tenant is not None and active_tenant != tenant_id:
            raise ValueError("The session is already bound to another tenant.")
        db.info["tenant_id"] = tenant_id
        self.db = db
        self.tenant_id = tenant_id
        self.repository = EntityIntelligenceRepository(db, tenant_id)

    def create_node(self, payload: EntityNodeCreate) -> EntityIntelligenceNode:
        node = self.repository.upsert_node(
            entity_type=payload.entity_type,
            entity_key=payload.entity_key,
            label=payload.label,
            source_type=payload.source_type,
            source_id=payload.source_id,
            attributes=payload.attributes,
            risk_score=payload.risk_score,
        )
        self.db.commit()
        self.db.refresh(node)
        return node

    def create_relationship(
        self, payload: EntityRelationshipCreate
    ) -> EntityIntelligenceRelationship:
        if payload.source_entity_id == payload.target_entity_id:
            raise bad_request("An entity cannot have a relationship to itself.")
        reserved_types = {
            "SENT_TRANSACTION",
            "PAID_TO",
            "DESTINATED_TO",
            "SHARES_RECIPIENT",
        }
        if payload.relationship_type in reserved_types:
            raise bad_request(
                "This relationship type is managed by graph synchronization."
            )
        source = self.repository.get_by_id(payload.source_entity_id)
        target = self.repository.get_by_id(payload.target_entity_id)
        if source is None:
            raise not_found("Source entity")
        if target is None:
            raise not_found("Target entity")
        relationship = self.repository.upsert_relationship(
            source_entity_id=source.id,
            target_entity_id=target.id,
            relationship_type=payload.relationship_type,
            confidence=payload.confidence,
            evidence=payload.evidence,
        )
        self.db.commit()
        self.db.refresh(relationship)
        return relationship

    def sync_customer_activity(
        self, customer_id: UUID
    ) -> EntityIntelligenceSyncResponse:
        customer = self.repository.get_customer(customer_id)
        if customer is None:
            raise not_found("Customer")

        own_activity = self.repository.list_customer_activity(customer_id)
        risk_activity = self.repository.list_customer_risk_transactions(customer_id)
        beneficiary_keys = {
            normalized
            for row in own_activity
            if (normalized := self._normalize_recipient(row.beneficiary_id)) is not None
        }
        shared_activity = self.repository.find_activities_for_beneficiaries(
            beneficiary_keys
        )
        activities_by_transaction: dict[UUID, TransactionAnomalyActivity] = {
            row.transaction_id: row for row in own_activity
        }
        for row in shared_activity:
            activities_by_transaction.setdefault(row.transaction_id, row)
        activities = list(activities_by_transaction.values())
        indexed_transaction_ids = set(activities_by_transaction)
        linked_risk_activity = [
            row
            for row in risk_activity
            if row.transaction_id not in indexed_transaction_ids
        ]

        customer_ids = {row.customer_id for row in activities}
        customer_ids.update(row.customer_id for row in linked_risk_activity)
        customers = {
            item.id: item for item in self.repository.get_customers(customer_ids)
        }
        customers[customer.id] = customer

        nodes_touched: set[UUID] = set()
        edges_touched: set[UUID] = set()
        customer_nodes: dict[UUID, EntityIntelligenceNode] = {}

        for linked_customer_id, linked_customer in customers.items():
            node = self.repository.upsert_node(
                entity_type="CUSTOMER",
                entity_key=str(linked_customer_id),
                label=self._customer_label(linked_customer),
                source_type="customers",
                source_id=str(linked_customer_id),
                attributes={
                    "status": getattr(
                        linked_customer.status, "value", str(linked_customer.status)
                    ),
                    "country_of_residence": linked_customer.country_of_residence,
                    "nationality": linked_customer.nationality,
                },
            )
            customer_nodes[linked_customer_id] = node
            nodes_touched.add(node.id)

        transaction_ids = {row.transaction_id for row in activities}
        transaction_ids.update(row.transaction_id for row in linked_risk_activity)
        anomaly_scores = self.repository.anomaly_scores_for_transactions(
            transaction_ids
        )
        recipient_nodes: dict[str, EntityIntelligenceNode] = {}
        recipient_customers: dict[str, set[UUID]] = defaultdict(set)
        recipient_transactions: dict[str, set[UUID]] = defaultdict(set)

        for activity in activities:
            customer_node = customer_nodes.get(activity.customer_id)
            if customer_node is None:
                # A stale activity row whose customer has been deleted is ignored.
                continue
            transaction_id = activity.transaction_id
            score = anomaly_scores.get(transaction_id, 0)
            transaction_node = self.repository.upsert_node(
                entity_type="TRANSACTION",
                entity_key=str(transaction_id),
                label=f"Transaction {str(transaction_id)[:8]}",
                source_type="transaction_anomaly_activity",
                source_id=str(transaction_id),
                risk_score=score,
                attributes={
                    "transaction_id": str(transaction_id),
                    "amount": str(activity.amount),
                    "currency": activity.currency,
                    "transaction_type": activity.transaction_type,
                    "occurred_at": activity.occurred_at.isoformat(),
                    "destination_country": activity.destination_country,
                },
                first_seen_at=activity.occurred_at,
                last_seen_at=activity.occurred_at,
            )
            nodes_touched.add(transaction_node.id)
            customer_edge = self.repository.upsert_relationship(
                source_entity_id=customer_node.id,
                target_entity_id=transaction_node.id,
                relationship_type="SENT_TRANSACTION",
                evidence={"transaction_id": str(transaction_id)},
                observed_at=activity.occurred_at,
            )
            edges_touched.add(customer_edge.id)

            beneficiary_key = self._normalize_recipient(activity.beneficiary_id)
            recipient_node: EntityIntelligenceNode | None = None
            if beneficiary_key:
                recipient_node = recipient_nodes.get(beneficiary_key)
                if recipient_node is None:
                    recipient_node = self.repository.upsert_node(
                        entity_type="RECIPIENT",
                        entity_key=beneficiary_key,
                        label=str(activity.beneficiary_id).strip(),
                        source_type="transaction_anomaly_activity",
                        attributes={
                            "recipient_reference": str(activity.beneficiary_id).strip()
                        },
                        first_seen_at=activity.occurred_at,
                        last_seen_at=activity.occurred_at,
                    )
                    recipient_nodes[beneficiary_key] = recipient_node
                nodes_touched.add(recipient_node.id)
                recipient_customers[beneficiary_key].add(activity.customer_id)
                recipient_transactions[beneficiary_key].add(transaction_id)
                paid_to_edge = self.repository.upsert_relationship(
                    source_entity_id=transaction_node.id,
                    target_entity_id=recipient_node.id,
                    relationship_type="PAID_TO",
                    evidence={"transaction_id": str(transaction_id)},
                    observed_at=activity.occurred_at,
                )
                edges_touched.add(paid_to_edge.id)

            if activity.destination_country and activity.destination_country.strip():
                country_label = activity.destination_country.strip().upper()
                country_node = self.repository.upsert_node(
                    entity_type="COUNTRY",
                    entity_key=country_label.casefold(),
                    label=country_label,
                    source_type="transaction_anomaly_activity",
                    attributes={"country_code_or_name": country_label},
                    first_seen_at=activity.occurred_at,
                    last_seen_at=activity.occurred_at,
                )
                nodes_touched.add(country_node.id)
                country_edge = self.repository.upsert_relationship(
                    source_entity_id=transaction_node.id,
                    target_entity_id=country_node.id,
                    relationship_type="DESTINATED_TO",
                    evidence={"transaction_id": str(transaction_id)},
                    observed_at=activity.occurred_at,
                )
                edges_touched.add(country_edge.id)
                if recipient_node is not None:
                    recipient_country_edge = self.repository.upsert_relationship(
                        source_entity_id=recipient_node.id,
                        target_entity_id=country_node.id,
                        relationship_type="ASSOCIATED_WITH_COUNTRY",
                        evidence={"transaction_id": str(transaction_id)},
                        observed_at=activity.occurred_at,
                    )
                    edges_touched.add(recipient_country_edge.id)

        for linked_activity in linked_risk_activity:
            customer_node = customer_nodes.get(linked_activity.customer_id)
            if customer_node is None:
                continue
            transaction_id = linked_activity.transaction_id
            score = anomaly_scores.get(transaction_id, 0)
            transaction_node = self.repository.upsert_node(
                entity_type="TRANSACTION",
                entity_key=str(transaction_id),
                label=f"Transaction {str(transaction_id)[:8]}",
                source_type="transaction_risk_transactions",
                source_id=str(transaction_id),
                risk_score=score,
                attributes={
                    "transaction_id": str(transaction_id),
                    "amount": str(linked_activity.amount),
                    "currency": linked_activity.currency,
                    "transaction_type": linked_activity.transaction_type,
                    "occurred_at": linked_activity.occurred_at.isoformat(),
                    "destination_country": linked_activity.destination_country,
                },
                first_seen_at=linked_activity.occurred_at,
                last_seen_at=linked_activity.occurred_at,
            )
            nodes_touched.add(transaction_node.id)
            customer_edge = self.repository.upsert_relationship(
                source_entity_id=customer_node.id,
                target_entity_id=transaction_node.id,
                relationship_type="SENT_TRANSACTION",
                evidence={"transaction_id": str(transaction_id)},
                observed_at=linked_activity.occurred_at,
            )
            edges_touched.add(customer_edge.id)
            if (
                linked_activity.destination_country
                and linked_activity.destination_country.strip()
            ):
                country_label = linked_activity.destination_country.strip().upper()
                country_node = self.repository.upsert_node(
                    entity_type="COUNTRY",
                    entity_key=country_label.casefold(),
                    label=country_label,
                    source_type="transaction_risk_transactions",
                    attributes={"country_code_or_name": country_label},
                    first_seen_at=linked_activity.occurred_at,
                    last_seen_at=linked_activity.occurred_at,
                )
                nodes_touched.add(country_node.id)
                country_edge = self.repository.upsert_relationship(
                    source_entity_id=transaction_node.id,
                    target_entity_id=country_node.id,
                    relationship_type="DESTINATED_TO",
                    evidence={"transaction_id": str(transaction_id)},
                    observed_at=linked_activity.occurred_at,
                )
                edges_touched.add(country_edge.id)

        risk_relationship_count = 0
        for recipient_key, linked_customer_ids in recipient_customers.items():
            distinct_customer_count = len(linked_customer_ids)
            risk_score = shared_recipient_risk_score(distinct_customer_count)
            if risk_score == 0:
                continue
            recipient_node = recipient_nodes[recipient_key]
            recipient_node.risk_score = max(recipient_node.risk_score, risk_score)
            recipient_node.risk_level = risk_level_for_score(recipient_node.risk_score)
            self.db.flush()
            evidence = {
                "distinct_customer_count": distinct_customer_count,
                "transaction_count": len(recipient_transactions[recipient_key]),
                "recipient_key": recipient_key,
                "assessment": (
                    "A recipient identifier is shared by multiple customers; "
                    "this is an investigative signal, not proof of wrongdoing."
                ),
            }
            indicators = ["SHARED_RECIPIENT_ACROSS_CUSTOMERS"]
            for linked_customer_id in linked_customer_ids:
                linked_node = customer_nodes.get(linked_customer_id)
                if linked_node is None:
                    continue
                relationship = self.repository.upsert_relationship(
                    source_entity_id=linked_node.id,
                    target_entity_id=recipient_node.id,
                    relationship_type="SHARES_RECIPIENT",
                    confidence=1.0,
                    risk_score=risk_score,
                    risk_indicators=indicators,
                    evidence=evidence,
                    observed_count=len(recipient_transactions[recipient_key]),
                )
                edges_touched.add(relationship.id)
                risk_relationship_count += 1

        self.db.commit()
        return EntityIntelligenceSyncResponse(
            customer_id=customer_id,
            transactions_indexed=len(
                {row.transaction_id for row in own_activity}
                | {row.transaction_id for row in risk_activity}
            ),
            nodes_indexed=len(nodes_touched),
            relationships_indexed=len(edges_touched),
            risk_relationships_identified=risk_relationship_count,
            message=(
                "Customer transaction relationships synchronized. Shared-recipient "
                "signals require investigator review and are not proof of misconduct."
            ),
        )

    def get_node(self, entity_id: UUID) -> EntityIntelligenceNode:
        node = self.repository.get_by_id(entity_id)
        if node is None:
            raise not_found("Entity")
        return node

    def get_graph(
        self, entity_id: UUID, *, depth: int = 2, max_nodes: int = 200
    ) -> EntityGraphResponse:
        root = self.get_node(entity_id)
        visited_nodes: dict[UUID, EntityIntelligenceNode] = {root.id: root}
        visited_relationships: dict[UUID, EntityIntelligenceRelationship] = {}
        frontier = {root.id}

        for _ in range(depth):
            if not frontier or len(visited_nodes) >= max_nodes:
                break
            edges = self.repository.list_relationships_connected_to(
                frontier, limit=max_nodes * 20
            )
            next_frontier: set[UUID] = set()
            candidate_ids: set[UUID] = set()
            for edge in edges:
                visited_relationships[edge.id] = edge
                if edge.source_entity_id not in visited_nodes:
                    candidate_ids.add(edge.source_entity_id)
                if edge.target_entity_id not in visited_nodes:
                    candidate_ids.add(edge.target_entity_id)
            available = max_nodes - len(visited_nodes)
            if available <= 0:
                break
            connected_nodes = self.repository.get_nodes_by_ids(candidate_ids)
            for node in connected_nodes:
                if len(visited_nodes) >= max_nodes:
                    break
                visited_nodes[node.id] = node
                next_frontier.add(node.id)
            frontier = next_frontier

        # Keep only edges with both endpoint nodes included in the graph payload.
        relationships = [
            visited_edge
            for visited_edge in visited_relationships.values()
            if visited_edge.source_entity_id in visited_nodes
            and visited_edge.target_entity_id in visited_nodes
        ]
        # Convert SQLAlchemy models into Pydantic response schemas.
        node_responses = [
            EntityNodeResponse.model_validate(node) for node in visited_nodes.values()
        ]
        relationship_responses = [
            EntityRelationshipResponse.model_validate(edge) for edge in relationships
        ]
        risky_responses = [
            relationship
            for relationship in relationship_responses
            if relationship.risk_score >= 40
        ]
        return EntityGraphResponse(
            root_entity_id=root.id,
            depth=depth,
            nodes=node_responses,
            relationships=relationship_responses,
            risk_relationships=risky_responses,
        )

    def list_risk_relationships(
        self, *, min_risk_score: int = 40, limit: int = 100
    ) -> list[EntityIntelligenceRelationship]:
        return self.repository.list_risk_relationships(
            min_risk_score=min_risk_score, limit=limit
        )

    @staticmethod
    def _normalize_recipient(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().casefold()
        return normalized or None

    @staticmethod
    def _customer_label(customer: Customer) -> str:
        name = " ".join(
            part.strip()
            for part in (
                customer.first_name,
                customer.middle_name or "",
                customer.last_name,
            )
            if part and part.strip()
        )
        return name or f"Customer {str(customer.id)[:8]}"
