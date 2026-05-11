"""Tests for ksearch.converter module."""

import json
from unittest.mock import Mock, patch

from ksearch.debug_logging import finish_debug_session, start_debug_session
from ksearch.converter import ContentConverter, clean_content
from ksearch.web.extractor import ContentConverter as WebContentConverter
from ksearch.web.url_policy import should_skip_url


def test_content_converter_init():
    converter = ContentConverter(timeout=30)
    assert converter.timeout == 30


def test_content_converter_compatibility_alias():
    """Public converter API should remain an alias to the web extractor class."""
    assert ContentConverter is WebContentConverter


def test_should_skip_url_known_problematic_urls():
    assert should_skip_url("https://www.youtube.com/watch?v=abc123")
    assert should_skip_url("https://youtu.be/abc123")
    assert should_skip_url("https://sputniknews.cn/20240101/example.html")
    assert not should_skip_url("https://example.com/article")


def test_content_converter_convert_url_success():
    mock_result = Mock()
    # Use longer content to pass minimum length check (50 chars)
    mock_result.text_content = "# Converted Content\n\nThis is markdown content that should be preserved after cleaning."

    with patch("ksearch.web.extractor.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md.convert.return_value = mock_result
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/article")

        assert "# Converted Content" in result


def test_content_converter_convert_url_failure():
    with patch("ksearch.web.extractor.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md.convert.side_effect = Exception("Conversion failed")
        mock_md_class.return_value = mock_md

        converter = ContentConverter()

        result = converter.convert_url("https://bad-url.com")

        assert result == ""


def test_clean_content_removes_fallback_notice():
    content = "# Title\n\n*Notice:* This page displays a fallback because interactive scripts did not run.\n\nActual content here."
    cleaned = clean_content(content)
    assert "*Notice:*" not in cleaned
    assert "# Title" in cleaned
    assert "Actual content" in cleaned


def test_clean_content_removes_nav_links():
    content = "# Title\n\n[Menu](/menu)\n[Home](/)\n[About](/about)\n\nReal paragraph with text."
    cleaned = clean_content(content)
    # Nav block should be removed
    assert "[Menu](/menu)" not in cleaned
    assert "Real paragraph" in cleaned


def test_converter_returns_empty_for_short_content():
    """convert_url should return empty for very short content (redirect pages)."""
    mock_result = Mock()
    mock_result.text_content = "Redirecting to </>..."  # Only 21 chars

    with patch("ksearch.web.extractor.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md.convert.return_value = mock_result
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/redirect")

        assert result == ""


def test_converter_returns_empty_when_cleaned_content_drops_below_threshold():
    """Compatibility guard: short cleaned content should be treated as empty."""
    mock_result = Mock()
    mock_result.text_content = (
        "# Title\n\n"
        "[Menu](/menu)\n"
        "[Home](/)\n"
        "Short body.\n"
    )

    with patch("ksearch.web.extractor.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md.convert.return_value = mock_result
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/noisy-short")

        assert result == ""


def test_convert_url_prefers_main_content_extraction():
    """Prefer extracted article body over raw full-page conversion when available."""
    response = Mock()
    response.text = "<html><body><article><h1>Title</h1><p>Main content only.</p></article></body></html>"
    response.raise_for_status = Mock()

    with patch("ksearch.web.extractor.requests.get", return_value=response), patch(
        "ksearch.web.extractor.trafilatura_extract",
        return_value="# Title\n\nMain content only with enough detail to pass the length threshold.",
    ), patch("ksearch.web.extractor.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/article")

        assert "Main content only" in result
        mock_md.convert.assert_not_called()


def test_convert_url_falls_back_to_markitdown_when_extraction_unavailable():
    """Fallback to markitdown when main-content extraction does not produce usable text."""
    response = Mock()
    response.text = "<html><body>Fallback page</body></html>"
    response.raise_for_status = Mock()

    mock_result = Mock()
    mock_result.text_content = "# Converted Content\n\nThis is markdown content that should be preserved after cleaning."

    with patch("ksearch.web.extractor.requests.get", return_value=response), patch(
        "ksearch.web.extractor.trafilatura_extract",
        return_value="too short",
    ), patch("ksearch.web.extractor.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md.convert.return_value = mock_result
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/article")

        assert "# Converted Content" in result
        mock_md.convert.assert_called_once()


def test_clean_content_removes_comment_and_signup_boilerplate():
    content = """# Title

Main article paragraph with actual substance.

## 9 Comments

Add a comment

Sign up to request clarification or add additional context in comments.

Post Your Answer
"""

    cleaned = clean_content(content)

    assert "Main article paragraph" in cleaned
    assert "## 9 Comments" not in cleaned
    assert "Add a comment" not in cleaned
    assert "Post Your Answer" not in cleaned


def test_convert_url_logs_main_extraction_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    response = Mock()
    response.text = "<html><body><article><h1>Title</h1><p>Main content only.</p></article></body></html>"
    response.raise_for_status = Mock()

    session = start_debug_session(
        argv=["--debug", "search", "python"],
        cwd="/work/tree",
        command="search",
    )

    with patch("ksearch.web.extractor.requests.get", return_value=response), patch(
        "ksearch.web.extractor.trafilatura_extract",
        return_value="# Title\n\nMain content only with enough detail to pass the length threshold.",
    ), patch("ksearch.web.extractor.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/article")
        finish_debug_session(success=True, command="search", summary={"result_length": len(result)})

    events = [
        json.loads(line)
        for line in (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    extraction_events = [event for event in events if event["event"] == "main_content_extracted"]

    assert extraction_events
    assert extraction_events[-1]["data"]["content_preview"].startswith("# Title")


def test_convert_url_logs_markitdown_fallback_event(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    response = Mock()
    response.text = "<html><body>Fallback page</body></html>"
    response.raise_for_status = Mock()

    mock_result = Mock()
    mock_result.text_content = "# Converted Content\n\nThis is markdown content that should be preserved after cleaning."

    session = start_debug_session(
        argv=["--debug", "search", "python"],
        cwd="/work/tree",
        command="search",
    )

    with patch("ksearch.web.extractor.requests.get", return_value=response), patch(
        "ksearch.web.extractor.trafilatura_extract",
        return_value="too short",
    ), patch("ksearch.web.extractor.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md.convert.return_value = mock_result
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/article")
        finish_debug_session(success=True, command="search", summary={"result_length": len(result)})

    events = [
        json.loads(line)
        for line in (session.debug_dir / "events.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    event_names = [event["event"] for event in events]

    assert "main_content_short" in event_names
    assert "markitdown_converted" in event_names
