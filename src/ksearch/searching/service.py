"""Search orchestration service."""

from typing import Optional

from ksearch.cache import CacheManager
from ksearch.converter import ContentConverter
from ksearch.models import ResultEntry, SearchResult
from ksearch.searxng import SearXNGClient


SKIP_URL_PATTERNS = [
    "youtube.com",
    "youtu.be",
    "vimeo.com",
    "tiktok.com",
    "dailymotion.com",
    "twitch.tv",
    "sputniknews.cn",
]


def should_skip_url(url: str) -> bool:
    """Check if URL should be skipped."""
    for pattern in SKIP_URL_PATTERNS:
        if pattern in url.lower():
            return True
    return False


class SearchEngine:
    """Orchestrates search flow: cache -> network -> convert -> store."""

    def __init__(
        self,
        cache: CacheManager,
        searxng: SearXNGClient,
        converter: ContentConverter,
    ):
        self.cache = cache
        self.searxng = searxng
        self.converter = converter

    def search(self, keyword: str, options: dict) -> list[ResultEntry]:
        """Execute search with given keyword and options."""
        results = []
        cached_urls = set()

        if not options.get("no_cache", False):
            exact = self.cache.exact_match(keyword)
            if exact:
                for entry in exact:
                    results.append(ResultEntry(
                        url=entry.url,
                        title=entry.title,
                        content=entry.content,
                        file_path=entry.file_path,
                        cached=True,
                        source=entry.engine,
                        cached_date=entry.cached_date,
                    ))
                return results

            partial = self.cache.partial_match(
                keyword,
                time_range=options.get("time_range"),
            )
            for entry in partial:
                cached_urls.add(entry.url)
                results.append(ResultEntry(
                    url=entry.url,
                    title=entry.title,
                    content=entry.content,
                    file_path=entry.file_path,
                    cached=True,
                    source=entry.engine,
                    cached_date=entry.cached_date,
                ))

        if not options.get("only_cache", False):
            network_results = self.searxng.search(
                query=keyword,
                time_range=options.get("time_range"),
                max_results=options.get("max_results", 10),
            )

            new_results = [r for r in network_results if r.url not in cached_urls]
            if new_results:
                filtered_results = [r for r in new_results if not should_skip_url(r.url)]
                if filtered_results:
                    converted_entries = self._convert_and_store(
                        filtered_results,
                        keyword,
                        timeout=options.get("timeout", 30),
                    )
                    results.extend(converted_entries)

        return results

    def _convert_and_store(
        self,
        results: list[SearchResult],
        keyword: str,
        timeout: int = 30,
    ) -> list[ResultEntry]:
        """Convert URLs to Markdown and store in cache."""
        entries = []
        for result in results:
            try:
                entry = self._process_result(result, keyword)
                if entry:
                    entries.append(entry)
            except Exception:
                continue

        return entries

    def _process_result(
        self,
        result: SearchResult,
        keyword: str,
    ) -> Optional[ResultEntry]:
        """Process single result: convert -> store."""
        try:
            content = self.converter.convert_url(result.url)
            if not content:
                return None

            file_path = self.cache.save(
                url=result.url,
                content=content,
                keyword=keyword,
                metadata={
                    "title": result.title,
                    "engine": result.engine,
                    "published_date": result.published_date,
                },
            )

            return ResultEntry(
                url=result.url,
                title=result.title,
                content=content,
                file_path=file_path,
                cached=False,
                source=result.engine,
                cached_date="",
            )
        except Exception:
            return None


__all__ = ["SearchEngine", "SKIP_URL_PATTERNS", "should_skip_url"]
