"""Search orchestration service."""

from typing import Optional

from ksearch.cache import CacheManager
from ksearch.converter import ContentConverter
from ksearch.debug_logging import log_event
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
        exact_count = 0
        partial_count = 0

        if not options.get("no_cache", False):
            exact = self.cache.exact_match(keyword)
            exact_count = len(exact)
            if exact:
                log_event(
                    "ksearch.search",
                    "cache_lookup",
                    {"keyword": keyword, "exact_count": exact_count, "partial_count": 0},
                )
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
                log_event(
                    "ksearch.search",
                    "search_complete",
                    {"keyword": keyword, "result_count": len(results), "source": "exact_cache"},
                )
                return results

            partial = self.cache.partial_match(
                keyword,
                time_range=options.get("time_range"),
            )
            partial_count = len(partial)
            log_event(
                "ksearch.search",
                "cache_lookup",
                {
                    "keyword": keyword,
                    "exact_count": exact_count,
                    "partial_count": partial_count,
                },
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
        else:
            log_event(
                "ksearch.search",
                "cache_lookup",
                {"keyword": keyword, "skipped": True},
            )

        if not options.get("only_cache", False):
            log_event(
                "ksearch.search",
                "network_search_start",
                {
                    "keyword": keyword,
                    "time_range": options.get("time_range"),
                    "max_results": options.get("max_results", 10),
                },
            )
            network_results = self.searxng.search(
                query=keyword,
                time_range=options.get("time_range"),
                max_results=options.get("max_results", 10),
            )

            new_results = [r for r in network_results if r.url not in cached_urls]
            if new_results:
                filtered_results = [r for r in new_results if not should_skip_url(r.url)]
                log_event(
                    "ksearch.search",
                    "network_search_results",
                    {
                        "keyword": keyword,
                        "raw_count": len(network_results),
                        "deduped_count": len(new_results),
                        "skipped_count": len(new_results) - len(filtered_results),
                        "candidate_count": len(filtered_results),
                    },
                )
                if filtered_results:
                    converted_entries = self._convert_and_store(
                        filtered_results,
                        keyword,
                        timeout=options.get("timeout", 30),
                    )
                    results.extend(converted_entries)
            else:
                log_event(
                    "ksearch.search",
                    "network_search_results",
                    {
                        "keyword": keyword,
                        "raw_count": len(network_results),
                        "deduped_count": 0,
                        "skipped_count": 0,
                        "candidate_count": 0,
                    },
                )

        log_event(
            "ksearch.search",
            "search_complete",
            {
                "keyword": keyword,
                "result_count": len(results),
                "cached_count": partial_count + exact_count,
                "network_count": len([entry for entry in results if not entry.cached]),
            },
        )
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

        log_event(
            "ksearch.search",
            "conversion_complete",
            {
                "keyword": keyword,
                "requested_count": len(results),
                "stored_count": len(entries),
            },
        )
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
