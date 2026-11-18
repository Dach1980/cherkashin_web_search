"""Current date and time from the host system clock."""

from datetime import datetime, timezone

from .contracts import DateTimeResponse


def _format_datetime(local_now: datetime) -> DateTimeResponse:
    """Format an aware local datetime with explicit timezone information."""
    if local_now.tzinfo is None or local_now.utcoffset() is None:
        raise ValueError("local_now must be timezone-aware")

    utc_now = local_now.astimezone(timezone.utc)
    local_iso = local_now.isoformat(timespec="seconds")

    return {
        "ok": True,
        "local_datetime": local_iso,
        "utc_datetime": utc_now.isoformat(timespec="seconds"),
        "date": local_now.date().isoformat(),
        "time": local_now.strftime("%H:%M:%S"),
        "weekday": local_now.isoweekday(),
        "timezone": local_now.tzname() or str(local_now.tzinfo),
        "utc_offset": local_iso[-6:],
        "unix_timestamp": int(local_now.timestamp()),
        "source": "system_clock",
    }


def get_current_datetime() -> DateTimeResponse:
    """Return the host's current local time and a UTC representation.

    The MCP server may run on a different computer or in a different timezone
    from the person using the model. The response therefore identifies the
    host timezone and UTC offset instead of assuming the user's location.
    """
    return _format_datetime(datetime.now().astimezone())
