from datetime import datetime, timedelta, timezone

import web_search_mcp.current_datetime as clock_module


def test_returns_local_time_timezone_and_utc(monkeypatch):
    fixed = datetime(2026, 11, 18, 9, 42, 5, tzinfo=timezone(timedelta(hours=2)))

    class FrozenDateTime:
        @classmethod
        def now(cls, tz=None):
            if tz is None:
                return fixed.replace(tzinfo=None)
            return fixed.astimezone(tz)

    monkeypatch.setattr(clock_module, "datetime", FrozenDateTime)

    result = clock_module.get_current_datetime()

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
