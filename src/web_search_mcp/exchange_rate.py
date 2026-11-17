"""Official exchange rates from the Bank of Russia XML service."""

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from xml.etree import ElementTree

import httpx

from .config import DEFAULT_TIMEOUT_SECONDS

CBR_DAILY_URL = "https://www.cbr.ru/scripts/XML_daily.asp"
CBR_SOURCE_URL = CBR_DAILY_URL
MAX_CBR_RESPONSE_BYTES = 2_000_000
RATE_QUANTUM = Decimal("0.00000001")


def _parse_cbr_rates(payload: bytes) -> tuple[str, dict[str, Decimal]]:
    """Parse CBR XML bytes; ElementTree handles the XML-declared Windows-1251 encoding."""
    root = ElementTree.fromstring(payload)
    effective_date = root.attrib.get("Date", "").strip()
    if not effective_date:
        raise ValueError("The Bank of Russia response has no effective date.")

    rates: dict[str, Decimal] = {"RUB": Decimal("1")}
    for item in root.findall("Valute"):
        code = (item.findtext("CharCode") or "").strip().upper()
        nominal_text = (item.findtext("Nominal") or "").strip()
        value_text = (item.findtext("Value") or "").strip().replace(",", ".")
        if len(code) != 3 or not code.isalpha():
            continue
        try:
            nominal = Decimal(nominal_text)
            value = Decimal(value_text)
        except InvalidOperation:
            continue
        if nominal <= 0 or value <= 0:
            continue
        rates[code] = value / nominal

    if len(rates) == 1:
        raise ValueError("The Bank of Russia response contains no currency rates.")
    return effective_date, rates


def get_exchange_rate(
    base_currency: str = "USD",
    quote_currency: str = "RUB",
) -> dict[str, object]:
    """Return an official CBR rate: units of quote_currency per one base_currency."""
    base = base_currency.strip().upper() if isinstance(base_currency, str) else ""
    quote = quote_currency.strip().upper() if isinstance(quote_currency, str) else ""
    if len(base) != 3 or not base.isalpha() or len(quote) != 3 or not quote.isalpha():
        return {
            "ok": False, "base_currency": base, "quote_currency": quote,
            "rate": None, "effective_date": None, "source": CBR_SOURCE_URL,
            "error": "Currency codes must be three-letter ISO codes, for example USD and RUB.",
        }

    try:
        response = httpx.get(
            CBR_DAILY_URL,
            timeout=DEFAULT_TIMEOUT_SECONDS,
            follow_redirects=False,
            headers={"User-Agent": "cherkashin-web-search/1.0"},
        )
        response.raise_for_status()
        if len(response.content) > MAX_CBR_RESPONSE_BYTES:
            raise ValueError("The Bank of Russia response exceeds the size limit.")
        effective_date, rates = _parse_cbr_rates(response.content)
        if base not in rates:
            raise ValueError(f"The Bank of Russia does not publish a daily rate for {base}.")
        if quote not in rates:
            raise ValueError(f"The Bank of Russia does not publish a daily rate for {quote}.")

        rate = (rates[base] / rates[quote]).quantize(RATE_QUANTUM, rounding=ROUND_HALF_UP)
        return {
            "ok": True,
            "base_currency": base,
            "quote_currency": quote,
            "rate": format(rate, "f"),
            "effective_date": effective_date,
            "source": CBR_SOURCE_URL,
            "error": None,
        }
    except (httpx.HTTPError, ElementTree.ParseError, InvalidOperation, ValueError) as error:
        return {
            "ok": False,
            "base_currency": base,
            "quote_currency": quote,
            "rate": None,
            "effective_date": None,
            "source": CBR_SOURCE_URL,
            "error": f"Bank of Russia rate request failed: {error}",
        }
