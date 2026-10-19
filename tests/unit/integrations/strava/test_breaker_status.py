from datetime import UTC, datetime, timedelta

from trainsync.integrations.strava.breaker import BreakerState
from trainsync.integrations.strava.breaker_status import BreakerReport, overall_state

NOW = datetime(2026, 10, 18, 9, 0, tzinfo=UTC)


def report(state: BreakerState, retry_in_s: int | None = None) -> BreakerReport:
    retry_at = NOW + timedelta(seconds=retry_in_s) if retry_in_s is not None else None
    return BreakerReport("p", state, retry_at, NOW)


def test_no_reports_is_closed() -> None:
    assert overall_state([], NOW) is BreakerState.CLOSED


def test_worst_state_wins() -> None:
    reports = [report(BreakerState.CLOSED), report(BreakerState.OPEN, 10)]
    assert overall_state(reports, NOW) is BreakerState.OPEN
    assert overall_state([report(BreakerState.CLOSED), report(BreakerState.HALF_OPEN)], NOW) is (
        BreakerState.HALF_OPEN
    )


def test_open_past_retry_time_reads_as_half_open() -> None:
    assert report(BreakerState.OPEN, -1).effective_state(NOW) is BreakerState.HALF_OPEN
    assert overall_state([report(BreakerState.OPEN, 0)], NOW) is BreakerState.HALF_OPEN
