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
