"""Content converter using markitdown."""

from markitdown import MarkItDown


class ContentConverter:
    """Converts URLs to Markdown using markitdown."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self._md = MarkItDown()

    def convert_url(self, url: str) -> str:
        """Convert URL content to Markdown."""
        try:
            result = self._md.convert(url)
            return result.text_content
        except Exception:
            return ""