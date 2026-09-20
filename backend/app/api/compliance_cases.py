from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Query, status

from app.core.dependencies import (
    get_compliance_service,
)
from app.core.responses import APIResponse
from app.core.security import require_roles
from app.schemas.compliance_case import (
    ComplianceCaseAssignment,
    ComplianceCaseCreate,
    ComplianceCaseHistoryResponse,
    ComplianceCaseResponse,
    ComplianceCaseStatusUpdate,
    ComplianceCaseUpdate,
)
from app.services.compliance_service import ComplianceService
from app.utils.enums import (
    ComplianceCaseStatus,
    ComplianceCaseType,
    UserRole,
)

router = APIRouter(
    prefix="/api/v1/compliance-cases",
    tags=["Compliance Cases"],
)


@router.post(
    "",
    response_model=APIResponse[ComplianceCaseResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Create compliance case",
    description="Create a compliance case for a customer.",
)
def create_compliance_case(
    case_data: ComplianceCaseCreate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="case",
        )
    ),
    service: ComplianceService = Depends(
        get_compliance_service,
    ),
) -> APIResponse[ComplianceCaseResponse]:
    case = service.create_case(
        case_data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Compliance case created successfully.",
        data=ComplianceCaseResponse.model_validate(case),
    )


@router.get(
    "",
    response_model=APIResponse[list[ComplianceCaseResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get compliance cases",
    description="Retrieve compliance cases.",
)
def get_compliance_cases(
    status: ComplianceCaseStatus | None = Query(
        default=None,
    ),
    case_type: ComplianceCaseType | None = Query(
        default=None,
    ),
    assigned_to: UUID | None = Query(
        default=None,
    ),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="case",
        )
    ),
    service: ComplianceService = Depends(
        get_compliance_service,
    ),
) -> APIResponse[list[ComplianceCaseResponse]]:
    cases = service.get_cases(
        status=status,
        case_type=case_type,
        assigned_to=assigned_to,
    )

    return APIResponse(
        success=True,
        message="Compliance cases retrieved successfully.",
        data=[ComplianceCaseResponse.model_validate(case) for case in cases],
    )


@router.get(
    "/{case_id}",
    response_model=APIResponse[ComplianceCaseResponse],
    status_code=status.HTTP_200_OK,
    summary="Get compliance case",
    description="Retrieve a compliance case by ID.",
)
def get_compliance_case(
    case_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="case",
        )
    ),
    service: ComplianceService = Depends(
        get_compliance_service,
    ),
) -> APIResponse[ComplianceCaseResponse]:
    case = service.get_case(case_id)

    return APIResponse(
        success=True,
        message="Compliance case retrieved successfully.",
        data=ComplianceCaseResponse.model_validate(case),
    )


@router.get(
    "/customer/{customer_id}",
    response_model=APIResponse[list[ComplianceCaseResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get customer compliance cases",
    description="Retrieve all compliance cases for a customer.",
)
def get_customer_compliance_cases(
    customer_id: UUID,
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="case",
        )
    ),
    service: ComplianceService = Depends(
        get_compliance_service,
    ),
) -> APIResponse[list[ComplianceCaseResponse]]:
    cases = service.get_cases_by_customer(
        customer_id,
    )

    return APIResponse(
        success=True,
        message="Customer compliance cases retrieved successfully.",
        data=[ComplianceCaseResponse.model_validate(case) for case in cases],
    )


@router.put(
    "/{case_id}",
    response_model=APIResponse[ComplianceCaseResponse],
    status_code=status.HTTP_200_OK,
    summary="Update compliance case",
    description="Update a compliance case.",
)
def update_compliance_case(
    case_id: UUID,
    case_data: ComplianceCaseUpdate,
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="case",
        )
    ),
    service: ComplianceService = Depends(
        get_compliance_service,
    ),
) -> APIResponse[ComplianceCaseResponse]:
    case = service.update_case(
        case_id,
        case_data,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Compliance case updated successfully.",
        data=ComplianceCaseResponse.model_validate(case),
    )


@router.patch(
    "/{case_id}/assignment",
    response_model=APIResponse[ComplianceCaseResponse],
    status_code=status.HTTP_200_OK,
    summary="Assign compliance case",
    description="Assign compliance case to a compliance officer",
)
def assign_compliance_case(
    case_id: UUID,
    assignment: ComplianceCaseAssignment,
    service: ComplianceService = Depends(get_compliance_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="case",
        )
    ),
) -> APIResponse[ComplianceCaseResponse]:
    case = service.assign_case(
        case_id,
        assignment.assigned_to,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
    )

    return APIResponse(
        success=True,
        message="Compliance case assigned successfully.",
        data=ComplianceCaseResponse.model_validate(case),
    )


@router.patch(
    "/{case_id}/status",
    response_model=APIResponse[ComplianceCaseResponse],
    status_code=status.HTTP_200_OK,
    summary="Update compliance case status",
    description="Update the status of compliance case.",
)
def update_compliance_case_status(
    case_id: UUID,
    status_data: ComplianceCaseStatusUpdate,
    service: ComplianceService = Depends(get_compliance_service),
    current_user: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            resource_type="case",
        )
    ),
) -> APIResponse[ComplianceCaseResponse]:
    case = service.update_case_status(
        case_id,
        status_data.status,
        user_id=UUID(current_user["sub"]),
        email=current_user["email"],
        resolution_reason=status_data.resolution_reason,
    )

    return APIResponse(
        success=True,
        message="Compliance case status updated successfully.",
        data=ComplianceCaseResponse.model_validate(case),
    )


@router.get(
    "/{case_id}/history",
    response_model=APIResponse[list[ComplianceCaseHistoryResponse]],
    status_code=status.HTTP_200_OK,
    summary="Get compliance case history",
    description="Retrieve the history of a compliance case",
)
def get_compliance_case_history(
    case_id: UUID,
    service: ComplianceService = Depends(get_compliance_service),
    _: dict[str, Any] = Depends(
        require_roles(
            UserRole.ADMINISTRATOR,
            UserRole.COMPLIANCE_OFFICER,
            UserRole.REVIEWER,
            resource_type="case",
        )
    ),
) -> APIResponse[list[ComplianceCaseHistoryResponse]]:
    history = service.get_case_history(case_id)

    return APIResponse(
        success=True,
        message="Compliance case history retrieved successfully.",
        data=[ComplianceCaseHistoryResponse.model_validate(item) for item in history],
    )
