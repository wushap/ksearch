"""Tests for ksearch.searxng module."""

import json
import pytest
from unittest.mock import Mock, patch

from ksearch.debug_logging import finish_debug_session, start_debug_session
from ksearch.searxng import SearXNGClient
from ksearch.models import SearchResult
from ksearch.web.search_client import SearXNGClient as WebSearXNGClient


def test_searxng_client_init():
    client = SearXNGClient("http://localhost:48888", timeout=30)
    assert client.base_url == "http://localhost:48888"
    assert client.timeout == 30


def test_searxng_client_compatibility_alias():
    assert SearXNGClient is WebSearXNGClient


def test_searxng_client_search_success():
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "url": "https://example.com/article",
                "title": "Example Article",
                "content": "Article snippet",
                "engine": "google",
                "publishedDate": None,
            }
        ]
    }

    with patch("requests.get", return_value=mock_response):
        client = SearXNGClient("http://localhost:48888")
        results = client.search("test query")

        assert len(results) == 1
        assert results[0].url == "https://example.com/article"
        assert results[0].title == "Example Article"
        assert results[0].engine == "google"


def test_searxng_client_search_with_time_range():
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"results": []}

    with patch("requests.get") as mock_get:
        mock_get.return_value = mock_response

        client = SearXNGClient("http://localhost:48888")
        client.search("test query", time_range="week")

        call_kwargs = mock_get.call_args[1]
        assert call_kwargs["params"]["time_range"] == "week"


def test_searxng_client_search_max_results():
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {"url": f"https://example.com/{i}", "title": f"Title {i}", "content": "", "engine": "google", "publishedDate": None}
            for i in range(20)
        ]
    }

    with patch("requests.get", return_value=mock_response):
        client = SearXNGClient("http://localhost:48888")
        results = client.search("test query", max_results=5)

        assert len(results) == 5


def test_searxng_client_search_connection_error():
    with patch("requests.get", side_effect=Exception("Connection failed")):
        client = SearXNGClient("http://localhost:48888")

        with pytest.raises(Exception):
            client.search("test query")


def test_searxng_client_logs_request_and_response_events(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "results": [
            {
                "url": "https://example.com/article",
                "title": "Example Article",
                "content": "Article snippet",
                "engine": "google",
                "publishedDate": None,
            }
        ]
    }

    with patch("requests.get", return_value=mock_response):
        session = start_debug_session(
            argv=["--debug", "search", "python"],
            cwd="/work/tree",
            command="search",
        )
        client = SearXNGClient("http://localhost:48888")
        results = client.search("python", time_range="week", max_results=5)
        finish_debug_session(success=True, command="search", summary={"result_count": len(results)})

    events = [
        json.loads(line)
        for line in (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_names = [event["event"] for event in events]

    assert "request_start" in event_names
    assert "response_received" in event_names
