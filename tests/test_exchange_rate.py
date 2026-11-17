import httpx

import web_search_mcp.exchange_rate as rate_module


SAMPLE_XML = b"""<?xml version="1.0" encoding="windows-1251"?>
<ValCurs Date="18.11.2026" name="Foreign Currency Market">
  <Valute ID="R01235">
    <NumCode>840</NumCode><CharCode>USD</CharCode><Nominal>1</Nominal>
    <Name>US Dollar</Name><Value>80,1234</Value>
  </Valute>
  <Valute ID="R01239">
    <NumCode>978</NumCode><CharCode>EUR</CharCode><Nominal>1</Nominal>
    <Name>Euro</Name><Value>92,5678</Value>
  </Valute>
  <Valute ID="R01375">
    <NumCode>392</NumCode><CharCode>JPY</CharCode><Nominal>100</Nominal>
    <Name>Japanese Yen</Name><Value>51,0000</Value>
  </Valute>
</ValCurs>
"""


def test_returns_default_usd_rub_rate(monkeypatch):
    request = httpx.Request("GET", rate_module.CBR_DAILY_URL)
    response = httpx.Response(200, content=SAMPLE_XML, request=request)
    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return response

    monkeypatch.setattr(rate_module.httpx, "get", fake_get)
    result = rate_module.get_exchange_rate()

    assert result["ok"] is True
    assert result["base_currency"] == "USD"
    assert result["quote_currency"] == "RUB"
    assert result["rate"] == "80.12340000"
    assert result["effective_date"] == "18.11.2026"
    assert result["source"] == rate_module.CBR_SOURCE_URL
    assert calls["url"] == rate_module.CBR_DAILY_URL
    assert calls["follow_redirects"] is False


def test_calculates_cross_rate_and_respects_nominal(monkeypatch):
    request = httpx.Request("GET", rate_module.CBR_DAILY_URL)
    response = httpx.Response(200, content=SAMPLE_XML, request=request)
    monkeypatch.setattr(rate_module.httpx, "get", lambda *args, **kwargs: response)

    cross = rate_module.get_exchange_rate("USD", "EUR")
    jpy = rate_module.get_exchange_rate("JPY", "RUB")

    assert cross["ok"] is True
    assert cross["rate"] == "0.86571991"
    assert jpy["ok"] is True
    assert jpy["rate"] == "0.51000000"


def test_rejects_invalid_currency_code_without_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("Network must not be used for invalid currency codes")

    monkeypatch.setattr(rate_module.httpx, "get", fail)
    result = rate_module.get_exchange_rate("US", "RUB")

    assert result["ok"] is False
    assert "three-letter ISO" in result["error"]


def test_reports_currency_not_published_by_cbr(monkeypatch):
    request = httpx.Request("GET", rate_module.CBR_DAILY_URL)
    response = httpx.Response(200, content=SAMPLE_XML, request=request)
    monkeypatch.setattr(rate_module.httpx, "get", lambda *args, **kwargs: response)

    result = rate_module.get_exchange_rate("GBP", "RUB")

    assert result["ok"] is False
    assert "does not publish" in result["error"]


def test_network_error_is_structured(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("simulated connection failure")

    monkeypatch.setattr(rate_module.httpx, "get", fail)
    result = rate_module.get_exchange_rate()

    assert result["ok"] is False
    assert result["rate"] is None
    assert "request failed" in result["error"]


def test_rejects_oversized_cbr_response(monkeypatch):
    request = httpx.Request("GET", rate_module.CBR_DAILY_URL)
    response = httpx.Response(
        200,
        content=b"x" * (rate_module.MAX_CBR_RESPONSE_BYTES + 1),
        request=request,
    )
    monkeypatch.setattr(rate_module.httpx, "get", lambda *args, **kwargs: response)

    result = rate_module.get_exchange_rate()

    assert result["ok"] is False
    assert "size limit" in result["error"]
