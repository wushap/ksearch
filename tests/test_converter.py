"""Tests for ksearch.converter module."""

from unittest.mock import Mock, patch

from ksearch.converter import ContentConverter, clean_content


def test_content_converter_init():
    converter = ContentConverter(timeout=30)
    assert converter.timeout == 30


def test_content_converter_convert_url_success():
    mock_result = Mock()
    # Use longer content to pass minimum length check (50 chars)
    mock_result.text_content = "# Converted Content\n\nThis is markdown content that should be preserved after cleaning."

    with patch("ksearch.converter.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md.convert.return_value = mock_result
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/article")

        assert "# Converted Content" in result


def test_content_converter_convert_url_failure():
    with patch("ksearch.converter.MarkItDown") as mock_md_class:
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

    with patch("ksearch.converter.MarkItDown") as mock_md_class:
        mock_md = Mock()
        mock_md.convert.return_value = mock_result
        mock_md_class.return_value = mock_md

        converter = ContentConverter()
        result = converter.convert_url("https://example.com/redirect")

        assert result == ""