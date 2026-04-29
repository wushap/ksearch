"""Iterative kbase-first search orchestration."""

import time

from ksearch.cache import CacheManager
from ksearch.converter import ContentConverter
from ksearch.iterative_convergence import ConvergenceEvaluator, IterationBoundary
from ksearch.iterative_query import QueryClassifier
from ksearch.iterative_sufficiency import SufficiencyEvaluator
from ksearch.kbase import KnowledgeBase, KnowledgeBaseSearchResult
from ksearch.models import ResultEntry
from ksearch.searxng import SearXNGClient


class IterativeSearchEngine:
    """Orchestrates iterative kbase-first search with web fallback."""

    def __init__(
        self,
        kbase: KnowledgeBase,
        searxng_client: SearXNGClient,
        converter: ContentConverter,
        cache: CacheManager,
        config: dict,
    ):
        self.kbase = kbase
        self.searxng = searxng_client
        self.converter = converter
        self.cache = cache
        self.query_classifier = QueryClassifier()
        self.config = config
        self.sufficiency = SufficiencyEvaluator(
            fact_threshold=config.get("fact_threshold", SufficiencyEvaluator.FACT_THRESHOLD),
            exploration_threshold=config.get(
                "exploration_threshold",
                SufficiencyEvaluator.EXPLORATION_THRESHOLD,
            ),
            weights=config.get("scoring_weights"),
        )
        self.convergence = ConvergenceEvaluator()
        self.boundary = IterationBoundary(
            max_iterations=config.get("max_iterations", 5),
            max_time_seconds=config.get("max_time_seconds", 180),
        )

    def search(self, query: str) -> list[ResultEntry]:
        start_time = time.time()
        kbase_top_k = self.config.get("kbase_top_k", 10)
        max_results = self.config.get("max_results", 5)

        query_type = self.query_classifier.classify(query)
        threshold = self.sufficiency.get_threshold(query_type)

        kbase_results = self.kbase.search(query, top_k=kbase_top_k)
        score = self.sufficiency.score(kbase_results)
        if self.sufficiency.is_sufficient(score, threshold):
            return self._convert_kbase_results(kbase_results)

        iteration = 0
        prev_results = kbase_results
        all_web_entries = []
        seen_web_urls = set()

        while not self.boundary.check_limits(iteration, time.time() - start_time):
            web_urls = self.searxng.search(query, max_results=max_results)
            ingested_any = False

            for url_result in web_urls:
                if url_result.url in seen_web_urls or self.cache.exists(url_result.url):
                    continue
                seen_web_urls.add(url_result.url)

                content = self.converter.convert_url(url_result.url)
                if not content:
                    continue

                file_path = self.cache.save(
                    url=url_result.url,
                    content=content,
                    keyword=query,
                    metadata={
                        "title": getattr(url_result, "title", ""),
                        "engine": getattr(url_result, "engine", "web"),
                        "published_date": getattr(url_result, "published_date", ""),
                    },
                )

                self.kbase.ingest_file_from_content(
                    content,
                    metadata={
                        "source": "web",
                        "url": url_result.url,
                        "title": getattr(url_result, "title", ""),
                        "file_path": file_path,
                        "published_date": getattr(url_result, "published_date", ""),
                    },
                )
                ingested_any = True

                all_web_entries.append(ResultEntry(
                    url=url_result.url,
                    title=getattr(url_result, "title", ""),
                    content=content,
                    file_path=file_path,
                    cached=False,
                    source=getattr(url_result, "engine", "web"),
                    cached_date="",
                ))

            if not ingested_any:
                break

            iteration += 1
            current_results = self.kbase.search(query, top_k=kbase_top_k)
            score = self.sufficiency.score(current_results)
            if self.sufficiency.is_sufficient(score, threshold):
                kbase_results = current_results
                break

            convergence = self.convergence.check_convergence(prev_results, current_results)
            if convergence.is_converged:
                kbase_results = current_results
                break

            prev_results = current_results
            kbase_results = current_results

        return self._combine_results(kbase_results, all_web_entries)

    def _convert_kbase_results(self, kbase_results: list[KnowledgeBaseSearchResult]) -> list[ResultEntry]:
        entries = []
        seen_paths = set()
        for result in kbase_results:
            if result.file_path in seen_paths:
                continue
            seen_paths.add(result.file_path)
            entries.append(ResultEntry(
                url=result.metadata.get("url", result.file_path) if result.metadata else result.file_path,
                title=result.title or "",
                content=result.content,
                file_path=result.file_path,
                cached=True,
                source=result.source or "kbase",
                cached_date=result.metadata.get("created_at", "") if result.metadata else "",
            ))
        return entries

    def _combine_results(
        self,
        kbase_results: list[KnowledgeBaseSearchResult],
        web_entries: list[ResultEntry],
    ) -> list[ResultEntry]:
        kbase_entries = self._convert_kbase_results(kbase_results)
        seen_paths = {entry.file_path for entry in kbase_entries}
        return kbase_entries + [entry for entry in web_entries if entry.file_path not in seen_paths]
