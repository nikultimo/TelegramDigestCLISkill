from dataclasses import dataclass
from datetime import date, timedelta


@dataclass(frozen=True)
class DigestDateRange:
    start: date
    end: date
    label: str
    output_stem: str


def resolve_date_range(
    range_name: str = "yesterday-today",
    *,
    today: date | None = None,
    days: int | None = None,
    from_date: str | None = None,
    to_date: str | None = None,
) -> DigestDateRange:
    today = today or date.today()

    if range_name == "yesterday-today":
        start = today - timedelta(days=1)
        end = today
        return _range(start, end, output_stem=end.isoformat())

    if range_name == "today":
        return _range(today, today, output_stem=today.isoformat())

    if range_name == "yesterday":
        yesterday = today - timedelta(days=1)
        return _range(yesterday, yesterday, output_stem=yesterday.isoformat())

    if range_name == "days":
        if days is None:
            raise ValueError("--days is required when --range days is used")
        if days <= 0:
            raise ValueError("--days must be greater than zero")
        start = today - timedelta(days=days - 1)
        end = today
        return _range(start, end, output_stem=end.isoformat())

    if range_name == "custom":
        if not from_date or not to_date:
            raise ValueError("--from and --to are required when --range custom is used")
        start = _parse_date(from_date, "--from")
        end = _parse_date(to_date, "--to")
        if start > end:
            raise ValueError("--from must be before or equal to --to")
        return _range(start, end, output_stem=f"{start.isoformat()}_to_{end.isoformat()}")

    raise ValueError(f"Unsupported range: {range_name}")


def _range(start: date, end: date, *, output_stem: str) -> DigestDateRange:
    label = start.isoformat() if start == end else f"{start.isoformat()} to {end.isoformat()}"
    return DigestDateRange(start=start, end=end, label=label, output_stem=output_stem)


def _parse_date(value: str, option_name: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{option_name} must use YYYY-MM-DD") from exc
