import httpx
import web_search_mcp.web_fetch as fetch_module


PUBLIC_IP = "93.184.216.34"


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


class FakeClient:
    def __init__(self, response=None, on_send=None, **kwargs):
        self.response = response or FakeStreamResponse(
            chunks=[b"<html><head><title>Example</title></head><body><main>Useful text</main></body></html>"]
        )
        self.on_send = on_send
        self.request = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def build_request(self, method, url, headers=None, extensions=None):
        return httpx.Request(method, url, headers=headers, extensions=extensions)

    def send(self, request, stream=False):
        self.request = request
        if self.on_send:
            return self.on_send(request)
        return self.response


def use_public_resolution(monkeypatch):
    monkeypatch.setattr(
        fetch_module,
        "_resolve_public_address",
        lambda url: (PUBLIC_IP, None),
    )


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
    use_public_resolution(monkeypatch)
    client = FakeClient(response=FakeStreamResponse(chunks=[html]))
    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: client)

    result = fetch_module.web_fetch("https://example.com/page")

    assert result["ok"] is True
    assert result["title"] == "Example title"
    assert "Hello Useful text" in result["text"]
    assert "ignore me" not in result["text"]


def test_connection_uses_pinned_ip_and_preserves_host_and_tls_sni(monkeypatch):
    dns_calls = []

    def fake_getaddrinfo(host, port, type):
        dns_calls.append((host, port))
        return [
            (2, 1, 6, "", (PUBLIC_IP, port)),
        ]

    monkeypatch.setattr(fetch_module.socket, "getaddrinfo", fake_getaddrinfo)
    client = FakeClient()
    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: client)

    result = fetch_module.web_fetch("https://example.com:8443/page")

    assert result["ok"] is True
    assert client.request.url.host == PUBLIC_IP
    assert client.request.url.port == 8443
    assert client.request.headers["host"] == "example.com:8443"
    assert client.request.extensions["sni_hostname"] == "example.com"
    assert dns_calls == [("example.com", 8443)]


def test_dns_rejects_mixed_public_and_private_answers(monkeypatch):
    def fake_getaddrinfo(host, port, type):
        return [
            (2, 1, 6, "", (PUBLIC_IP, port)),
            (2, 1, 6, "", ("127.0.0.1", port)),
        ]

    monkeypatch.setattr(fetch_module.socket, "getaddrinfo", fake_getaddrinfo)
    result = fetch_module.web_fetch("https://example.com/page")

    assert result["ok"] is False
    assert "private or non-global" in result["error"]


def test_redirect_to_loopback_is_rejected_before_second_request(monkeypatch):
    validation_calls = []

    def resolve(url):
        validation_calls.append(url)
        if "127.0.0.1" in url:
            return None, "Private, loopback, link-local, and non-global IP addresses are not allowed."
        return PUBLIC_IP, None

    monkeypatch.setattr(fetch_module, "_resolve_public_address", resolve)
    sent_requests = []

    def on_send(request):
        sent_requests.append(request)
        return FakeStreamResponse(
            status_code=302,
            headers={"location": "http://127.0.0.1/admin"},
        )

    client = FakeClient(on_send=on_send)
    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: client)

    result = fetch_module.web_fetch("https://example.com/redirect")

    assert result["ok"] is False
    assert "non-global IP" in result["error"]
    assert len(sent_requests) == 1
    assert sent_requests[0].url.host == PUBLIC_IP
    assert len(validation_calls) == 2


def test_rejects_body_over_byte_limit(monkeypatch):
    use_public_resolution(monkeypatch)
    too_large_chunk = b"x" * (fetch_module.MAX_RESPONSE_BYTES + 1)
    client = FakeClient(response=FakeStreamResponse(chunks=[too_large_chunk]))
    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: client)

    result = fetch_module.web_fetch("https://example.com/page")

    assert result["ok"] is False
    assert "byte limit" in result["error"]


def test_http_error_does_not_expose_exception_details(monkeypatch):
    use_public_resolution(monkeypatch)

    class BrokenClient(FakeClient):
        def send(self, request, stream=False):
            raise httpx.ConnectError("private network detail")

    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: BrokenClient())
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
    use_public_resolution(monkeypatch)
    client = FakeClient(response=FakeStreamResponse(chunks=[html]))
    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: client)

    result = fetch_module.web_fetch("https://example.com/page", max_chars=5)

    assert result["ok"] is True
    assert result["text"] == "abcde"
    assert result["truncated"] is True


def test_fetch_reports_http_status_error(monkeypatch):
    use_public_resolution(monkeypatch)
    client = FakeClient(response=FakeStreamResponse(
        status_code=503,
        headers={"content-type": "text/html"},
    ))
    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: client)

    result = fetch_module.web_fetch("https://example.com/page")

    assert result["ok"] is False
    assert result["status_code"] == 503
    assert "503" in result["error"]


def test_connection_pins_public_ipv6_address(monkeypatch):
    ipv6 = "2001:4860:4860::8888"

    def fake_getaddrinfo(host, port, type):
        return [
            (fetch_module.socket.AF_INET6, fetch_module.socket.SOCK_STREAM, 6, "", (ipv6, port, 0, 0)),
        ]

    monkeypatch.setattr(fetch_module.socket, "getaddrinfo", fake_getaddrinfo)
    client = FakeClient()
    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: client)

    result = fetch_module.web_fetch("https://example.com/ipv6")

    assert result["ok"] is True
    assert client.request.url.host == ipv6
    assert client.request.headers["host"] == "example.com"
    assert client.request.extensions["sni_hostname"] == "example.com"


def test_redirect_resolves_and_pins_each_new_hostname(monkeypatch):
    dns_calls = []

    def fake_getaddrinfo(host, port, type):
        dns_calls.append((host, port))
        ip = PUBLIC_IP if host == "example.com" else "8.8.8.8"
        return [(2, 1, 6, "", (ip, port))]

    monkeypatch.setattr(fetch_module.socket, "getaddrinfo", fake_getaddrinfo)
    requests = []
    responses = [
        FakeStreamResponse(status_code=302, headers={"location": "https://other.example/next"}),
        FakeStreamResponse(chunks=[b"<html><body><main>Final page</main></body></html>"]),
    ]

    class SequencedClient(FakeClient):
        def send(self, request, stream=False):
            requests.append(request)
            return responses.pop(0)

    monkeypatch.setattr(fetch_module.httpx, "Client", lambda **kwargs: SequencedClient())

    result = fetch_module.web_fetch("https://example.com/start")

    assert result["ok"] is True
    assert [request.url.host for request in requests] == [PUBLIC_IP, "8.8.8.8"]
    assert [request.extensions["sni_hostname"] for request in requests] == [
        "example.com", "other.example"
    ]
    assert dns_calls == [("example.com", 443), ("other.example", 443)]
