"""How Jira's values read: timestamps as dates and ages, and any field value as short text."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from typing import Any

from acli_py.domain import adf


def moment(value: str | datetime | None) -> datetime | None:
    """Return a Jira timestamp ('2024-05-01T10:00:00.000+0000') as a datetime, or None."""
    if value is None or isinstance(value, datetime):
        return value
    for layout, text in (
        ("%Y-%m-%dT%H:%M:%S%z", value[:19] + value[23:28]),  # with milliseconds
        ("%Y-%m-%dT%H:%M:%S%z", value),
        ("%Y-%m-%dT%H:%M:%S", value[:19]),
    ):
        try:
            return datetime.strptime(text, layout)
        except ValueError:
            continue
    return None


def day(value: str | None) -> date | None:
    """Return a Jira date ('2024-05-01') as a date, or None."""
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def when(value: str | datetime | None, with_time: bool = True) -> str:
    """Return a timestamp as 'YYYY-MM-DD HH:MM', in the offset Jira sent it with."""
    if not value:
        return ""
    parsed = moment(value)
    if parsed is None:
        return str(value)
    return parsed.strftime("%Y-%m-%d %H:%M" if with_time else "%Y-%m-%d")


def ago(value: str | datetime | None, now: datetime | None = None) -> str:
    """Return a timestamp as a short age: 5m, 3h, 2d, 6w, or the date when it is old."""
    if not value:
        return ""
    parsed = moment(value)
    if parsed is None or parsed.tzinfo is None:
        return when(value, with_time=False)
    seconds = ((now or datetime.now(UTC)) - parsed).total_seconds()
    for unit, size in (("w", 604800), ("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            if unit == "w" and seconds > 604800 * 20:
                return parsed.strftime("%Y-%m-%d")
            return f"{int(seconds // size)}{unit}"
    return "now"


def text(value: Any) -> str:
    """Return any Jira field value as short text."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return f"{value:g}"
    if isinstance(value, (str, int)):
        return str(value)
    if isinstance(value, list):
        return ", ".join(t for t in (text(v) for v in value) if t)
    if isinstance(value, dict):
        if adf.is_adf(value):
            return " ".join(adf.to_text(value).split())
        for key in ("displayName", "name", "value", "key", "title", "id"):
            if key in value and value[key] not in (None, ""):
                inner = value.get("child")
                shown = str(value[key])
                return f"{shown} > {text(inner)}" if inner else shown
        return json.dumps(value, ensure_ascii=False)
    return str(value)
