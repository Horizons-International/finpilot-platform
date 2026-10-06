from datetime import date, datetime

from pydantic import BaseModel


class CustomerAnalyticsFilters(BaseModel):
    start_date: date
    end_date: date
    country: str | None = None
    status: str | None = None


class NewCustomerTrendPoint(BaseModel):
    snapshot_date: date
    new_customers: int


class CustomerCountryCount(BaseModel):
    country: str
    customer_count: int


class CustomerVerificationStatusCount(BaseModel):
    status: str
    customer_count: int


class CustomerOverview(BaseModel):
    total_customers: int
    new_customers_during_period: int
    new_customers_trend: list[NewCustomerTrendPoint]
    customers_by_country: list[CustomerCountryCount]
    customers_by_verification_status: list[CustomerVerificationStatusCount]
    active_customers: int
    inactive_customers: int


class CustomerLifecycleAnalytics(BaseModel):
    average_onboarding_completion_time_hours: float | None
    verification_completion_rate_percentage: float | None
    verification_rejection_rate_percentage: float | None
    pending_verification_count: int


class CustomerAnalyticsResponse(BaseModel):
    generated_at: datetime
    filters: CustomerAnalyticsFilters
    overview: CustomerOverview
    lifecycle: CustomerLifecycleAnalytics
