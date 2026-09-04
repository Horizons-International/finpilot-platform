import enum
from enum import StrEnum


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    READY = "ready"
    NOT_READY = "not_ready"


class CustomerStatus(StrEnum):
    NEW = "new"
    PENDING_VERIFICATION = "pending_verification"
    VERIFIED = "verified"
    SUSPENDED = "suspended"
    REJECTED = "rejected"


class AuditEventType(str, enum.Enum):
    LOGIN_SUCCESS = "LOGIN_SUCCESS"
    LOGIN_FAILURE = "LOGIN_FAILURE"
    LOGOUT = "LOGOUT"
    PASSWORD_CHANGE = "PASSWORD_CHANGE"

    FILE_UPLOAD = "FILE_UPLOAD"
    FILE_DOWNLOAD = "FILE_DOWNLOAD"
    FILE_DELETE = "FILE_DELETE"

    USER_CREATED = "USER_CREATED"
    USER_UPDATED = "USER_UPDATED"
    USER_DELETED = "USER_DELETED"
    USER_STATUS_CHANGED = "USER_STATUS_CHANGED"

    CUSTOMER_CREATED = "CUSTOMER_CREATED"
    CUSTOMER_UPDATED = "CUSTOMER_UPDATED"
    CUSTOMER_STATUS_CHANGED = "CUSTOMER_STATUS_CHANGED"

    ACCESS_DENIED = "ACCESS_DENIED"


class UserStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    LOCKED = "locked"


class UserRole(str, enum.Enum):
    ADMINISTRATOR = "Administrator"
    REVIEWER = "Reviewer"
    COMPLIANCE_OFFICER = "Compliance Officer"
    AUDITOR = "Auditor"


class AddressType(str, enum.Enum):
    RESIDENTIAL = "residential"
    MAILING = "mailing"


class PreferredContactMethod(str, enum.Enum):
    PHONE = "phone"
    EMAIL = "email"
