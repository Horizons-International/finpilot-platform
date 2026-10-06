from datetime import date, timedelta

from sqlalchemy.orm import Session

from app.analytics.repositories.customer_analytics_repository import (
    CustomerAnalyticsRepository,
)
from app.schemas.customer_analytics import (
    CustomerAnalyticsFilters,
    CustomerAnalyticsResponse,
    CustomerCountryCount,
    CustomerLifecycleAnalytics,
    CustomerOverview,
    CustomerVerificationStatusCount,
    NewCustomerTrendPoint,
)
from app.utils.date_time import utc_now
from app.utils.enums import CustomerStatus
from app.utils.errors import bad_request


class CustomerAnalyticsService:
    DEFAULT_LOOKBACK_DAYS = 30
    MAX_LOOKBACK_DAYS = 366

    def __init__(self, db: Session) -> None:
        self.repository = CustomerAnalyticsRepository(db)

    def get_customer_summary(
        self,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        country: str | None = None,
        status: CustomerStatus | None = None,
    ) -> CustomerAnalyticsResponse:
        normalized_end_date = end_date or utc_now().date()

        normalized_start_date = start_date or (
            normalized_end_date - timedelta(days=self.DEFAULT_LOOKBACK_DAYS - 1)
        )

        if normalized_start_date > normalized_end_date:
            raise bad_request(
                "start_date cannot be after end_date.",
            )

        lookback_days = (normalized_end_date - normalized_start_date).days + 1

        if lookback_days > self.MAX_LOOKBACK_DAYS:
            raise bad_request(
                "Analytics date range cannot exceed 366 days.",
            )

        normalized_country = (
            country.strip() if country is not None and country.strip() else None
        )

        (
            total_customers,
            active_customers,
            inactive_customers,
        ) = self.repository.get_customer_population_metrics(
            end_date=normalized_end_date,
            country=normalized_country,
            status=status,
        )

        new_customer_trend = self.repository.get_new_customer_trend(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
            country=normalized_country,
            status=status,
        )

        country_rows = self.repository.get_customers_by_country(
            end_date=normalized_end_date,
            country=normalized_country,
            status=status,
        )

        verification_status_rows = self.repository.get_customers_by_verification_status(
            end_date=normalized_end_date,
            country=normalized_country,
            status=status,
        )

        (
            verification_cases_created,
            verification_cases_completed,
            verification_cases_rejected,
            pending_verification_count,
        ) = self.repository.get_verification_lifecycle_metrics(
            start_date=normalized_start_date,
            end_date=normalized_end_date,
            country=normalized_country,
            status=status,
        )

        average_onboarding_hours = (
            self.repository.get_average_onboarding_completion_time_hours(
                start_date=normalized_start_date,
                end_date=normalized_end_date,
                country=normalized_country,
                status=status,
            )
        )

        verification_completion_rate = None

        if verification_cases_created > 0:
            verification_completion_rate = round(
                (verification_cases_completed / verification_cases_created) * 100,
                2,
            )

        verification_rejection_rate = None

        if verification_cases_completed > 0:
            verification_rejection_rate = round(
                (verification_cases_rejected / verification_cases_completed) * 100,
                2,
            )

        return CustomerAnalyticsResponse(
            generated_at=utc_now(),
            filters=CustomerAnalyticsFilters(
                start_date=normalized_start_date,
                end_date=normalized_end_date,
                country=normalized_country,
                status=status.value if status else None,
            ),
            overview=CustomerOverview(
                total_customers=total_customers,
                new_customers_during_period=sum(
                    count for _, count in new_customer_trend
                ),
                new_customers_trend=[
                    NewCustomerTrendPoint(
                        snapshot_date=snapshot_date,
                        new_customers=count,
                    )
                    for snapshot_date, count in new_customer_trend
                ],
                customers_by_country=[
                    CustomerCountryCount(
                        country=country_name,
                        customer_count=count,
                    )
                    for country_name, count in country_rows
                ],
                customers_by_verification_status=[
                    CustomerVerificationStatusCount(
                        status=verification_status,
                        customer_count=count,
                    )
                    for verification_status, count in verification_status_rows
                ],
                active_customers=active_customers,
                inactive_customers=inactive_customers,
            ),
            lifecycle=CustomerLifecycleAnalytics(
                average_onboarding_completion_time_hours=(average_onboarding_hours),
                verification_completion_rate_percentage=(verification_completion_rate),
                verification_rejection_rate_percentage=(verification_rejection_rate),
                pending_verification_count=(pending_verification_count),
            ),
        )
