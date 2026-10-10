from web_search_mcp.contracts import FetchResponse, SearchResponse, SearchResult


def test_search_result_contract_fields_are_documented():
    example: SearchResult = {
        "title": "Example",
        "url": "https://example.org",
        "snippet": "Description",
    }

    assert set(example) == {"title", "url", "snippet"}


def test_search_response_has_stable_success_and_failure_shape():
    success: SearchResponse = {
        "ok": True,
        "query": "Python",
        "results": [{"title": "Example", "url": "https://example.org", "snippet": "Description"}],
        "error": None,
    }
    failure: SearchResponse = {
        "ok": False,
        "query": "Python",
        "results": [],
        "error": "Search failed",
    }

    assert set(success) == set(failure) == {"ok", "query", "results", "error"}
    assert success["ok"] is True
    assert failure["ok"] is False


def test_fetch_response_has_stable_success_and_failure_shape():
    success: FetchResponse = {
        "ok": True,
        "url": "https://example.org",
        "status_code": 200,
        "title": "Example",
        "text": "Readable text",
        "truncated": False,
        "error": None,
    }
    failure: FetchResponse = {
        "ok": False,
        "url": "https://example.org",
        "status_code": None,
        "title": "",
        "text": "",
        "truncated": False,
        "error": "Connection failed",
    }

    assert set(success) == set(failure) == {
        "ok", "url", "status_code", "title", "text", "truncated", "error"
    }
    assert success["ok"] is True
    assert failure["ok"] is False
