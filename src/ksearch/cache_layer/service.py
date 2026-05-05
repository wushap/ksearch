"""Compatibility cache manager assembled from store and repository layers."""

import os
import sqlite3
from datetime import datetime

from ksearch.cache_layer.repository import CacheRepository, normalize_engine_names
from ksearch.cache_layer.store import CacheStore, hash_url
from ksearch.models import CacheEntry


class CacheManager:
    """Manages SQLite index and file storage for cached content."""

    def __init__(self, db_path: str, store_dir: str):
        self.db_path = db_path
        self.store_dir = store_dir
        self.store = CacheStore(store_dir)
        self.repository = CacheRepository(db_path)

    def save(
        self,
        url: str,
        content: str,
        keyword: str,
        metadata: dict,
    ) -> str:
        """Save content to file and index in SQLite."""
        file_hash = hash_url(url)
        file_path = self.store.write(url, content)
        cached_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.repository.upsert(
            url=url,
            file_hash=file_hash,
            file_path=file_path,
            keyword=keyword,
            cached_date=cached_date,
            metadata=metadata,
        )
        return file_path

    def exists(self, url: str) -> bool:
        """Check if URL is already cached."""
        return self.repository.exists(url)

    def get_file_path(self, url: str) -> str:
        """Get file path for URL (regardless of cached status)."""
        return self.store.path_for(url)

    def exact_match(self, keyword: str) -> list[CacheEntry]:
        """Find entries with exact keyword match using SQLite."""
        rows = self.repository.exact_match_rows(keyword)
        return [self._load_entry_content(self._row_to_entry(row)) for row in rows]

    def partial_match(
        self,
        keyword: str,
        time_range: str | None = None,
    ) -> list[CacheEntry]:
        """Find entries with partial keyword match using SQLite."""
        rows = self.repository.partial_match_rows(keyword, time_range=time_range)
        return [self._load_entry_content(self._row_to_entry(row)) for row in rows]

    def _row_to_entry(self, row: sqlite3.Row) -> CacheEntry:
        """Convert SQLite row to CacheEntry."""
        return CacheEntry(
            url=row["url"],
            file_path=row["file_path"],
            title=row["title"] or "",
            keyword=row["keyword"],
            cached_date=row["cached_date"] or "",
            engine=row["engine"] or "",
            content="",
        )

    def _load_entry_content(self, entry: CacheEntry) -> CacheEntry:
        """Populate cached Markdown content for an entry when available."""
        if os.path.exists(entry.file_path):
            entry.content = self.store.read(entry.file_path)
        return entry

    def cleanup_missing_files(self) -> int:
        """Remove entries whose files are missing from SQLite."""
        missing_urls = []
        for row in self.repository.rows_for_cleanup():
            if not os.path.exists(row["file_path"]):
                missing_urls.append(row["url"])
        self.repository.delete_urls(missing_urls)
        return len(missing_urls)

    def rebuild_index_from_db(self) -> int:
        """Compatibility shim after removing keyword index files."""
        return self.repository.count_distinct_keywords()

    def stats(self) -> dict:
        """Summarize cache entry counts, size, keyword variety, and source distribution."""
        total_entries = 0
        keywords = set()
        total_size_bytes = 0
        engines: dict[str, int] = {}
        domains: dict[str, int] = {}
        missing_files = 0

        for row in self.repository.stats_rows():
            total_entries += 1
            keywords.add(row["keyword"])

            for engine in normalize_engine_names(row["engine"] or ""):
                engines[engine] = engines.get(engine, 0) + 1

            domain = self.repository.build_domain(row["url"])
            domains[domain] = domains.get(domain, 0) + 1

            file_path = row["file_path"]
            if os.path.exists(file_path):
                total_size_bytes += os.path.getsize(file_path)
            else:
                missing_files += 1

        return {
            "total_entries": total_entries,
            "keyword_count": len(keywords),
            "total_size_bytes": total_size_bytes,
            "engines": dict(sorted(engines.items(), key=lambda item: (-item[1], item[0]))),
            "domains": dict(sorted(domains.items(), key=lambda item: (-item[1], item[0]))),
            "missing_files": missing_files,
        }
