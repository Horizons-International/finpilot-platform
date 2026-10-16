"""Entity-intelligence graph and relationship-risk endpoints."""

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.entity_intelligence import (
    EntityGraphResponse,
    EntityIntelligenceSyncResponse,
    EntityNodeCreate,
    EntityNodeResponse,
    EntityRelationshipCreate,
    EntityRelationshipResponse,
)
from app.services.entity_intelligence_service import EntityIntelligenceService
from app.utils.enums import UserRole

router = APIRouter(
    prefix="/api/v1/entity-intelligence",
    tags=["Entity Intelligence"],
)

_VIEW_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_MANAGER,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.REVIEWER,
    UserRole.ANALYST,
)
_WRITE_ROLES = (
    UserRole.ADMINISTRATOR,
    UserRole.ORGANIZATION_ADMIN,
    UserRole.COMPLIANCE_OFFICER,
    UserRole.ANALYST,
)


def _service(db: Session, current_user: dict[str, Any]) -> EntityIntelligenceService:
    return EntityIntelligenceService(db, tenant_id=UUID(current_user["tenant_id"]))


@router.post(
    "/entities",
    response_model=APIResponse[EntityNodeResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create or update an investigation entity",
)
def create_entity(
    payload: EntityNodeCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_WRITE_ROLES, resource_type="entity_intelligence")
    ),
) -> APIResponse[EntityNodeResponse]:
    node = _service(db, current_user).create_node(payload)
    return APIResponse(
        success=True,
        message="Entity stored successfully.",
        data=EntityNodeResponse.model_validate(node),
    )


@router.post(
    "/relationships",
    response_model=APIResponse[EntityRelationshipResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create or update an entity relationship",
)
def create_relationship(
    payload: EntityRelationshipCreate,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_WRITE_ROLES, resource_type="entity_intelligence")
    ),
) -> APIResponse[EntityRelationshipResponse]:
    relationship = _service(db, current_user).create_relationship(payload)
    return APIResponse(
        success=True,
        message="Entity relationship stored successfully.",
        data=EntityRelationshipResponse.model_validate(relationship),
    )


@router.post(
    "/customers/{customer_id}/sync",
    response_model=APIResponse[EntityIntelligenceSyncResponse],
    status_code=status.HTTP_200_OK,
    summary="Build the graph around a customer's retained transactions",
    description=(
        "Indexes tenant-owned transaction activity into customer, transaction, "
        "recipient and country nodes. Shared recipients create risk signals for review."
    ),
)
def synchronize_customer_graph(
    customer_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_WRITE_ROLES, resource_type="entity_intelligence")
    ),
) -> APIResponse[EntityIntelligenceSyncResponse]:
    result = _service(db, current_user).sync_customer_activity(customer_id)
    return APIResponse(
        success=True,
        message="Customer entity graph synchronized successfully.",
        data=result,
    )


@router.get(
    "/entities/{entity_id}",
    response_model=APIResponse[EntityNodeResponse],
    summary="Get an entity in the current tenant's graph",
)
def get_entity(
    entity_id: UUID,
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_VIEW_ROLES, resource_type="entity_intelligence")
    ),
) -> APIResponse[EntityNodeResponse]:
    node = _service(db, current_user).get_node(entity_id)
    return APIResponse(
        success=True,
        message="Entity retrieved successfully.",
        data=EntityNodeResponse.model_validate(node),
    )


@router.get(
    "/graph/{entity_id}",
    response_model=APIResponse[EntityGraphResponse],
    summary="Retrieve a graph suitable for visualization",
    description=(
        "Returns nodes and directed edges to render a graph. Risk edges are also "
        "returned separately for highlighting in an investigation UI."
    ),
)
def get_entity_graph(
    entity_id: UUID,
    depth: int = Query(default=2, ge=1, le=3),
    max_nodes: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_VIEW_ROLES, resource_type="entity_intelligence")
    ),
) -> APIResponse[EntityGraphResponse]:
    graph = _service(db, current_user).get_graph(
        entity_id, depth=depth, max_nodes=max_nodes
    )
    return APIResponse(
        success=True,
        message="Entity graph retrieved successfully.",
        data=graph,
    )


@router.get(
    "/risk-relationships",
    response_model=APIResponse[list[EntityRelationshipResponse]],
    summary="List potentially risky entity relationships",
)
def list_risk_relationships(
    min_risk_score: int = Query(default=40, ge=0, le=100),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: dict[str, Any] = Depends(
        require_roles(*_VIEW_ROLES, resource_type="entity_intelligence")
    ),
) -> APIResponse[list[EntityRelationshipResponse]]:
    relationships = _service(db, current_user).list_risk_relationships(
        min_risk_score=min_risk_score, limit=limit
    )
    return APIResponse(
        success=True,
        message=(
            "Risk relationships retrieved successfully. These are investigative "
            "signals and require contextual review."
        ),
        data=[
            EntityRelationshipResponse.model_validate(item) for item in relationships
        ],
    )
