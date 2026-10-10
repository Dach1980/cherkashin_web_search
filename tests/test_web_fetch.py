import httpx
import web_search_mcp.web_fetch as fetch_module


class FakeStreamResponse:
    def __init__(self, status_code=200, headers=None, chunks=None, encoding="utf-8"):
        self.status_code = status_code
        self.headers = headers or {"content-type": "text/html; charset=utf-8"}
        self._chunks = chunks or []
        self.encoding = encoding

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def iter_bytes(self):
        yield from self._chunks


def test_rejects_loopback_ip_without_network():
    result = fetch_module.web_fetch("http://127.0.0.1/secret")
    assert result["ok"] is False
    assert "non-global IP" in result["error"]


def test_rejects_non_http_scheme():
    result = fetch_module.web_fetch("file:///etc/passwd")
    assert result["ok"] is False
    assert "http and https" in result["error"]


def test_rejects_max_chars_above_configured_limit():
    result = fetch_module.web_fetch("https://example.com", max_chars=999_999_999)
    assert result["ok"] is False
    assert "max_chars" in result["error"]


def test_extracts_title_and_readable_text(monkeypatch):
    html = (b"<html><head><title>Example title</title></head><body><nav>Menu</nav>"
            b"<main><h1>Hello</h1><p>Useful text</p><script>ignore me</script></main></body></html>")
    monkeypatch.setattr(fetch_module, "_validate_public_url", lambda url: None)
    monkeypatch.setattr(fetch_module.httpx, "stream", lambda *args, **kwargs: FakeStreamResponse(chunks=[html]))
    result = fetch_module.web_fetch("https://example.com/page")
    assert result["ok"] is True
    assert result["title"] == "Example title"
    assert "Hello Useful text" in result["text"]
    assert "ignore me" not in result["text"]


def test_redirect_to_loopback_is_rejected_before_second_request(monkeypatch):
    validation_calls = []

    def validate(url):
        validation_calls.append(url)
        if "127.0.0.1" in url:
            return "Private, loopback, link-local, and non-global IP addresses are not allowed."
        return None

    monkeypatch.setattr(fetch_module, "_validate_public_url", validate)
    calls = []
    def fake_stream(*args, **kwargs):
        calls.append(args[1])
        return FakeStreamResponse(status_code=302, headers={"location": "http://127.0.0.1/admin"})
    monkeypatch.setattr(fetch_module.httpx, "stream", fake_stream)
    result = fetch_module.web_fetch("https://example.com/redirect")
    assert result["ok"] is False
    assert "non-global IP" in result["error"]
    assert calls == ["https://example.com/redirect"]
    assert len(validation_calls) == 2


def test_rejects_body_over_byte_limit(monkeypatch):
    monkeypatch.setattr(fetch_module, "_validate_public_url", lambda url: None)
    too_large_chunk = b"x" * (fetch_module.MAX_RESPONSE_BYTES + 1)
    monkeypatch.setattr(fetch_module.httpx, "stream", lambda *args, **kwargs: FakeStreamResponse(chunks=[too_large_chunk]))
    result = fetch_module.web_fetch("https://example.com/page")
    assert result["ok"] is False
    assert "byte limit" in result["error"]


def test_http_error_does_not_expose_exception_details(monkeypatch):
    monkeypatch.setattr(fetch_module, "_validate_public_url", lambda url: None)
    class BrokenStream:
        def __enter__(self):
            raise httpx.ConnectError("private network detail")
        def __exit__(self, exc_type, exc, traceback):
            return False
    monkeypatch.setattr(fetch_module.httpx, "stream", lambda *args, **kwargs: BrokenStream())
    result = fetch_module.web_fetch("https://example.com/page")
    assert result["ok"] is False
    assert result["error"] == "Request failed: ConnectError."
    assert "private network detail" not in result["error"]


def test_fetch_rejects_bool_max_chars():
    result = fetch_module.web_fetch("https://example.com", max_chars=True)
    assert result["ok"] is False
    assert "integer" in result["error"]


def test_fetch_marks_text_as_truncated(monkeypatch):
    html = b"<html><head><title>Long</title></head><body><main>abcdefghij</main></body></html>"
    monkeypatch.setattr(fetch_module, "_validate_public_url", lambda url: None)
    monkeypatch.setattr(
        fetch_module.httpx,
        "stream",
        lambda *args, **kwargs: FakeStreamResponse(chunks=[html]),
    )

    result = fetch_module.web_fetch("https://example.com/page", max_chars=5)

    assert result["ok"] is True
    assert result["text"] == "abcde"
    assert result["truncated"] is True


def test_fetch_reports_http_status_error(monkeypatch):
    monkeypatch.setattr(fetch_module, "_validate_public_url", lambda url: None)
    monkeypatch.setattr(
        fetch_module.httpx,
        "stream",
        lambda *args, **kwargs: FakeStreamResponse(status_code=503, headers={"content-type": "text/html"}),
    )

    result = fetch_module.web_fetch("https://example.com/page")

    assert result["ok"] is False
    assert result["status_code"] == 503
    assert "503" in result["error"]
