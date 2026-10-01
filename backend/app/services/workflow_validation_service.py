from collections.abc import Mapping
from typing import TypeVar

from fastapi import HTTPException, status

StatusType = TypeVar("StatusType")


class WorkflowValidationService[StatusType]:
    def __init__(
        self,
        transitions: Mapping[StatusType, set[StatusType]],
    ) -> None:
        self.transitions = transitions

    def validate_transition(
        self,
        current_status: StatusType,
        new_status: StatusType,
    ) -> None:
        if current_status == new_status:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The verification case is already in this status.",
            )

        allowed_statuses = self.transitions.get(current_status, set())

        if new_status not in allowed_statuses:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(f"Invalid status transition: {current_status} → {new_status}."),
            )
