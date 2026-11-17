from app.core.config import settings
from app.core.database import get_database_pool_status


def test_database_pool_status_reports_both_engines():
    status = get_database_pool_status()

    assert set(status) == {"sync", "async"}

    assert status["sync"]["configured_size"] == settings.DATABASE_SYNC_POOL_SIZE
    assert status["sync"]["max_overflow"] == settings.DATABASE_SYNC_MAX_OVERFLOW
    assert status["sync"]["max_capacity"] == (
        settings.DATABASE_SYNC_POOL_SIZE + settings.DATABASE_SYNC_MAX_OVERFLOW
    )

    assert status["async"]["configured_size"] == settings.DATABASE_ASYNC_POOL_SIZE
    assert status["async"]["max_overflow"] == settings.DATABASE_ASYNC_MAX_OVERFLOW
    assert status["async"]["max_capacity"] == (
        settings.DATABASE_ASYNC_POOL_SIZE + settings.DATABASE_ASYNC_MAX_OVERFLOW
    )

    for pool_status in status.values():
        assert pool_status["checked_in"] >= 0
        assert pool_status["checked_out"] >= 0
        assert isinstance(pool_status["current_overflow"], int)
