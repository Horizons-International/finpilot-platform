from enum import StrEnum


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"


class HealthStatus(StrEnum):
    HEALTHY = "healthy"
    READY = "ready"
    NOT_READY = "not_ready"
