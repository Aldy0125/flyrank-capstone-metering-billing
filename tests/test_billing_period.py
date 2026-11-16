from datetime import datetime, timedelta, timezone

import pytest

from app.services.usage_metering_service import (
    get_utc_billing_period,
    get_seconds_until_next_utc_period,
)


def test_normal_utc_billing_period():
    now = datetime(
        2026, 11, 16, 7, 0,
        tzinfo=timezone.utc,
    )

    start, end = get_utc_billing_period(now)

    assert start.isoformat() == "2026-11-01"
    assert end.isoformat() == "2026-11-30"


def test_timezone_conversion_crosses_month_boundary():
    utc_plus_two = timezone(timedelta(hours=2))

    now = datetime(
        2026, 12, 1, 0, 30,
        tzinfo=utc_plus_two,
    )

    start, end = get_utc_billing_period(now)

    assert start.isoformat() == "2026-11-01"
    assert end.isoformat() == "2026-11-30"


def test_december_year_rollover():
    now = datetime(
        2026, 12, 31, 23, 59,
        tzinfo=timezone.utc,
    )

    start, end = get_utc_billing_period(now)

    assert start.isoformat() == "2026-12-01"
    assert end.isoformat() == "2026-12-31"


def test_leap_year_february():
    now = datetime(
        2024, 2, 15, 12, 0,
        tzinfo=timezone.utc,
    )

    start, end = get_utc_billing_period(now)

    assert start.isoformat() == "2024-02-01"
    assert end.isoformat() == "2024-02-29"


def test_non_leap_year_february():
    now = datetime(
        2025, 2, 15, 12, 0,
        tzinfo=timezone.utc,
    )

    start, end = get_utc_billing_period(now)

    assert start.isoformat() == "2025-02-01"
    assert end.isoformat() == "2025-02-28"


def test_retry_after_seconds_until_next_month():
    now = datetime(
        2026, 11, 30, 23, 59, 30,
        tzinfo=timezone.utc,
    )

    result = get_seconds_until_next_utc_period(now)

    assert result == 30


def test_retry_after_respects_timezone_conversion():
    utc_plus_two = timezone(timedelta(hours=2))

    now = datetime(
        2026, 12, 1, 0, 30,
        tzinfo=utc_plus_two,
    )

    result = get_seconds_until_next_utc_period(now)

    assert result == 5_400


@pytest.mark.parametrize(
    "function",
    [
        get_utc_billing_period,
        get_seconds_until_next_utc_period,
    ],
)
def test_naive_datetime_is_rejected(function):
    now = datetime(2026, 11, 16, 12, 0)

    with pytest.raises(
        ValueError,
        match="timezone-aware",
    ):
        function(now)
