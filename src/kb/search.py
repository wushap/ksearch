"""Search orchestration module."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from kb.cache import CacheManager
from kb.searxng import SearXNGClient
from kb.converter import ContentConverter
from kb.models import ResultEntry, SearchResult


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

        # Step 1: Check cache (unless no_cache)
        if not options.get("no_cache", False):
            exact = self.cache.exact_match(keyword)
            if exact:
                # Exact match: return cached only
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

            # Partial match
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

        # Step 2: Network search (unless only_cache)
        if not options.get("only_cache", False):
            network_results = self.searxng.search(
                query=keyword,
                time_range=options.get("time_range"),
                max_results=options.get("max_results", 10),
            )

            # Filter out already cached URLs
            new_results = [r for r in network_results if r.url not in cached_urls]

            # Step 3: Convert and store new results
            if new_results:
                converted_entries = self._convert_and_store(
                    new_results,
                    keyword,
                )
                results.extend(converted_entries)

        return results

    def _convert_and_store(
        self,
        results: list[SearchResult],
        keyword: str,
    ) -> list[ResultEntry]:
        """Convert URLs to Markdown and store in cache."""
        entries = []

        # Parallel conversion
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {
                executor.submit(
                    self._process_result,
                    result,
                    keyword,
                ): result
                for result in results
            }

            for future in as_completed(futures):
                entry = future.result()
                if entry:
                    entries.append(entry)

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
            # Individual failure, return None to continue processing other results
            return None