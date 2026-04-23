"""Tests for kb.converter module."""

from unittest.mock import Mock, patch

from ksearch.converter import ContentConverter


def test_content_converter_init():
    converter = ContentConverter(timeout=30)
    assert converter.timeout == 30


def test_content_converter_convert_url_success():
    mock_result = Mock()
    mock_result.text_content = "# Converted Content\n\nThis is markdown."

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