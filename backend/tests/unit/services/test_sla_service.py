from datetime import datetime, timezone

from app.services.sla_service import SLAService
from app.utils.enums import SLAStatus


def test_sla_is_within_sla():
    created_at = datetime(
        2026,
        10,
        1,
        10,
        tzinfo=timezone.utc,
    )

    due_date = datetime(
        2026,
        10,
        3,
        10,
        tzinfo=timezone.utc,
    )

    now = datetime(
        2026,
        10,
        2,
        10,
        tzinfo=timezone.utc,
    )

    status = SLAService.calculate_status(
        created_at=created_at,
        due_date=due_date,
        now=now,
    )

    assert status == SLAStatus.WITHIN_SLA


def test_sla_is_approaching_deadline():
    created_at = datetime(
        2026,
        10,
        1,
        10,
        tzinfo=timezone.utc,
    )

    due_date = datetime(
        2026,
        10,
        3,
        10,
        tzinfo=timezone.utc,
    )

    now = datetime(
        2026,
        10,
        3,
        1,
        tzinfo=timezone.utc,
    )

    status = SLAService.calculate_status(
        created_at=created_at,
        due_date=due_date,
        now=now,
    )

    assert status == SLAStatus.APPROACHING_DEADLINE


def test_sla_is_breached():
    created_at = datetime(
        2026,
        10,
        1,
        10,
        tzinfo=timezone.utc,
    )

    due_date = datetime(
        2026,
        10,
        3,
        10,
        tzinfo=timezone.utc,
    )

    now = datetime(
        2026,
        10,
        3,
        11,
        tzinfo=timezone.utc,
    )

    status = SLAService.calculate_status(
        created_at=created_at,
        due_date=due_date,
        now=now,
    )

    assert status == SLAStatus.BREACHED


def test_completed_before_due_date_is_completed():
    created_at = datetime(
        2026,
        10,
        1,
        10,
        tzinfo=timezone.utc,
    )

    due_date = datetime(
        2026,
        10,
        3,
        10,
        tzinfo=timezone.utc,
    )

    completed_at = datetime(
        2026,
        10,
        3,
        9,
        tzinfo=timezone.utc,
    )

    status = SLAService.calculate_status(
        created_at=created_at,
        due_date=due_date,
        completed_at=completed_at,
    )

    assert status == SLAStatus.COMPLETED


def test_completed_after_due_date_is_breached():
    created_at = datetime(
        2026,
        10,
        1,
        10,
        tzinfo=timezone.utc,
    )

    due_date = datetime(
        2026,
        10,
        3,
        10,
        tzinfo=timezone.utc,
    )

    completed_at = datetime(
        2026,
        10,
        3,
        11,
        tzinfo=timezone.utc,
    )

    status = SLAService.calculate_status(
        created_at=created_at,
        due_date=due_date,
        completed_at=completed_at,
    )

    assert status == SLAStatus.BREACHED


def test_no_due_date_has_no_sla():
    status = SLAService.calculate_status(
        created_at=datetime(
            2026,
            10,
            1,
            10,
            tzinfo=timezone.utc,
        ),
        due_date=None,
    )

    assert status is None
