"""Current date and time from the host system clock."""

from datetime import datetime, timezone

from .contracts import DateTimeResponse


def get_current_datetime() -> DateTimeResponse:
    """Return the host's current local time and a UTC representation.

    The MCP server may run on a different computer or in a different timezone
    from the person using the model. The response therefore identifies the
    host timezone and UTC offset instead of assuming the user's location.
    """
    local_now = datetime.now().astimezone()
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
