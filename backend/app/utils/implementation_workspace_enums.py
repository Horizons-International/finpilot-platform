"""Enums for enterprise implementation workspaces."""

from enum import StrEnum


class ImplementationStage(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    CONFIGURATION = "CONFIGURATION"
    INTEGRATION = "INTEGRATION"
    TESTING = "TESTING"
    READY_FOR_PRODUCTION = "READY_FOR_PRODUCTION"


class ImplementationWorkStatus(StrEnum):
    NOT_STARTED = "NOT_STARTED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    BLOCKED = "BLOCKED"


class ImplementationTaskCategory(StrEnum):
    PROJECT = "PROJECT"
    TECHNICAL = "TECHNICAL"
    BUSINESS = "BUSINESS"


class ImplementationTaskPriority(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ImplementationMemberType(StrEnum):
    INTERNAL = "INTERNAL"
    CUSTOMER = "CUSTOMER"


class ImplementationMemberRole(StrEnum):
    MANAGER = "MANAGER"
    MEMBER = "MEMBER"
    VIEWER = "VIEWER"
