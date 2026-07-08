from datetime import date

import pytest

from tg_digest.ranges import resolve_date_range


def test_default_range_includes_yesterday_and_today():
    resolved = resolve_date_range("yesterday-today", today=date(2026, 7, 8))

    assert resolved.start == date(2026, 7, 7)
    assert resolved.end == date(2026, 7, 8)
    assert resolved.label == "2026-07-07 to 2026-07-08"


def test_today_range_includes_only_today():
    resolved = resolve_date_range("today", today=date(2026, 7, 8))

    assert resolved.start == date(2026, 7, 8)
    assert resolved.end == date(2026, 7, 8)
    assert resolved.label == "2026-07-08"


def test_days_range_includes_today_plus_previous_days():
    resolved = resolve_date_range("days", today=date(2026, 7, 8), days=7)

    assert resolved.start == date(2026, 7, 2)
    assert resolved.end == date(2026, 7, 8)
    assert resolved.label == "2026-07-02 to 2026-07-08"


def test_custom_range_requires_valid_ordered_dates():
    resolved = resolve_date_range(
        "custom",
        today=date(2026, 7, 8),
        from_date="2026-07-01",
        to_date="2026-07-08",
    )

    assert resolved.start == date(2026, 7, 1)
    assert resolved.end == date(2026, 7, 8)


@pytest.mark.parametrize(
    ("range_name", "kwargs", "message"),
    [
        ("days", {"days": 0}, "--days must be greater than zero"),
        ("custom", {"from_date": "2026-07-09", "to_date": "2026-07-08"}, "--from must be before or equal to --to"),
        ("custom", {"from_date": "2026-07-01"}, "--from and --to are required"),
        ("unknown", {}, "Unsupported range"),
    ],
)
def test_invalid_ranges_raise_value_error(range_name, kwargs, message):
    with pytest.raises(ValueError, match=message):
        resolve_date_range(range_name, today=date(2026, 7, 8), **kwargs)
