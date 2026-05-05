"""Web content extraction and conversion."""

import threading

import requests
from markitdown import MarkItDown

from ksearch.web.cleaner import clean_content

try:
    from trafilatura import extract as trafilatura_extract
except ImportError:
    trafilatura_extract = None


class WebContentConverter:
    """Converts URLs to Markdown using main-content extraction and cleanup."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        self.url_timeout = min(timeout, 10)
        self._md = MarkItDown()
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }

    def _extract_main_content(self, url: str) -> str:
        """Fetch page HTML and extract the primary article body when possible."""
        if trafilatura_extract is None:
            return ""

        try:
            response = requests.get(url, headers=self._headers, timeout=self.url_timeout)
            response.raise_for_status()
        except Exception:
            return ""

        extracted = trafilatura_extract(
            response.text,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
        )
        if not extracted:
            return ""
        return clean_content(extracted)

    def _convert_with_markitdown(self, url: str) -> str:
        """Fallback conversion path using markitdown."""
        result_container = []
        exception_container = []

        def worker():
            try:
                result = self._md.convert(url)
                result_container.append(result.text_content)
            except Exception as exc:
                exception_container.append(exc)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=self.url_timeout)

        if thread.is_alive():
            return ""
        if exception_container:
            return ""

        raw_content = result_container[0] if result_container else ""
        return clean_content(raw_content)

    def convert_url(self, url: str) -> str:
        """Convert URL content to Markdown and clean noise."""
        cleaned = self._extract_main_content(url)
        if len(cleaned) < 50:
            cleaned = self._convert_with_markitdown(url)
        if len(cleaned) < 50:
            return ""
        return cleaned


ContentConverter = WebContentConverter
