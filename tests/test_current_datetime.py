from datetime import datetime, timedelta, timezone

import pytest

import web_search_mcp.current_datetime as clock_module


def test_formats_local_time_timezone_and_utc():
    fixed = datetime(2026, 11, 18, 9, 42, 5, tzinfo=timezone(timedelta(hours=2)))

    result = clock_module._format_datetime(fixed)

    assert result["ok"] is True
    assert result["local_datetime"] == "2026-11-18T09:42:05+02:00"
    assert result["utc_datetime"] == "2026-11-18T07:42:05+00:00"
    assert result["date"] == "2026-11-18"
    assert result["time"] == "09:42:05"
    assert result["weekday"] == 3
    assert result["timezone"] == "UTC+02:00"
    assert result["utc_offset"] == "+02:00"
    assert result["unix_timestamp"] == int(fixed.timestamp())
    assert result["source"] == "system_clock"


def test_rejects_naive_datetime():
    with pytest.raises(ValueError, match="timezone-aware"):
        clock_module._format_datetime(datetime(2026, 11, 18, 9, 42, 5))
