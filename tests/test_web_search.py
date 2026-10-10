import httpx
import web_search_mcp.web_search as search_module


def test_rejects_empty_query_without_network():
    result = search_module.web_search("   ")
    assert result["ok"] is False
    assert result["results"] == []


def test_rejects_boolean_as_result_limit():
    result = search_module.web_search("python", max_results=True)
    assert result["ok"] is False
    assert "integer" in result["error"]


def test_parses_search_results(monkeypatch):
    html = """
    <div class="result">
      <h2 class="result__title"><a href="https://example.com/article">Example article</a></h2>
      <a class="result__snippet">A useful summary.</a>
    </div>
    <div class="result">
      <h2 class="result__title"><a href="https://example.org/other">Other article</a></h2>
    </div>
    """
    request = httpx.Request("GET", "https://html.duckduckgo.com/html/")
    response = httpx.Response(200, text=html, request=request)
    monkeypatch.setattr(search_module.httpx, "get", lambda *args, **kwargs: response)
    result = search_module.web_search("python", max_results=2)
    assert result["ok"] is True
    assert len(result["results"]) == 2
    assert result["results"][0]["title"] == "Example article"
    assert result["results"][0]["url"] == "https://example.com/article"
    assert result["results"][0]["snippet"] == "A useful summary."


def test_network_error_is_returned_as_structured_result(monkeypatch):
    def fail(*args, **kwargs):
        raise httpx.ConnectError("simulated connection failure")
    monkeypatch.setattr(search_module.httpx, "get", fail)
    result = search_module.web_search("python")
    assert result["ok"] is False
    assert result["results"] == []
    assert "Search request failed" in result["error"]


def test_search_normalizes_query_and_passes_timeout(monkeypatch):
    html = '<div class="result"><h2 class="result__title"><a href="https://example.org">Example</a></h2></div>'
    request = httpx.Request("GET", "https://html.duckduckgo.com/html/")
    response = httpx.Response(200, text=html, request=request)
    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls.update(kwargs)
        return response

    monkeypatch.setattr(search_module.httpx, "get", fake_get)
    result = search_module.web_search("  Python MCP  ", max_results=1)

    assert result["ok"] is True
    assert result["query"] == "Python MCP"
    assert calls["params"] == {"q": "Python MCP"}
    assert calls["timeout"] == search_module.DEFAULT_TIMEOUT_SECONDS


def test_search_http_status_error_is_structured(monkeypatch):
    request = httpx.Request("GET", "https://html.duckduckgo.com/html/")
    response = httpx.Response(503, request=request)
    monkeypatch.setattr(search_module.httpx, "get", lambda *args, **kwargs: response)

    result = search_module.web_search("Python")

    assert result["ok"] is False
    assert result["results"] == []
    assert result["error"] is not None
