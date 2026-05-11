"""Web content extraction and conversion."""

import threading

import requests
from markitdown import MarkItDown

from ksearch.debug_logging import log_event
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
            log_event(
                "ksearch.web.extractor",
                "main_content_unavailable",
                {"url": url, "reason": "trafilatura_missing"},
                level="WARNING",
            )
            return ""

        try:
            response = requests.get(url, headers=self._headers, timeout=self.url_timeout)
            response.raise_for_status()
        except Exception as exc:
            log_event(
                "ksearch.web.extractor",
                "main_content_fetch_failed",
                {"url": url, "message": str(exc)},
                level="WARNING",
            )
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
            log_event(
                "ksearch.web.extractor",
                "main_content_missing",
                {"url": url},
                level="WARNING",
            )
            return ""
        cleaned = clean_content(extracted)
        log_event(
            "ksearch.web.extractor",
            "main_content_extracted",
            {"url": url, "content_preview": cleaned},
        )
        return cleaned

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
            log_event(
                "ksearch.web.extractor",
                "markitdown_timeout",
                {"url": url},
                level="WARNING",
            )
            return ""
        if exception_container:
            log_event(
                "ksearch.web.extractor",
                "markitdown_failed",
                {"url": url, "message": str(exception_container[0])},
                level="WARNING",
            )
            return ""

        raw_content = result_container[0] if result_container else ""
        cleaned = clean_content(raw_content)
        log_event(
            "ksearch.web.extractor",
            "markitdown_converted",
            {"url": url, "content_preview": cleaned},
        )
        return cleaned

    def convert_url(self, url: str) -> str:
        """Convert URL content to Markdown and clean noise."""
        cleaned = self._extract_main_content(url)
        if len(cleaned) < 50:
            if cleaned:
                log_event(
                    "ksearch.web.extractor",
                    "main_content_short",
                    {"url": url, "content_preview": cleaned},
                    level="WARNING",
                )
            cleaned = self._convert_with_markitdown(url)
        if len(cleaned) < 50:
            log_event(
                "ksearch.web.extractor",
                "conversion_empty",
                {"url": url},
                level="WARNING",
            )
            return ""
        return cleaned


ContentConverter = WebContentConverter
