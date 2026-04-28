"""Tests for ksearch.searxng module."""

import pytest
from unittest.mock import Mock, patch

from ksearch.searxng import SearXNGClient
from ksearch.models import SearchResult


def test_searxng_client_init():
    client = SearXNGClient("http://localhost:48888", timeout=30)
    assert client.base_url == "http://localhost:48888"
    assert client.timeout == 30


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