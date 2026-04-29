"""Cache management with SQLite index and Markdown file storage."""

import hashlib
import os
import sqlite3
from datetime import datetime
from urllib.parse import urlparse

from ksearch.models import CacheEntry


TIME_RANGE_SQL = {
    "day": "datetime('now', '-1 day')",
    "week": "datetime('now', '-7 days')",
    "month": "datetime('now', '-30 days')",
    "year": "datetime('now', '-365 days')",
}

VALID_TIME_RANGES = {"day", "week", "month", "year"}


def normalize_engine_names(engine_value: str) -> list[str]:
    """Normalize raw engine strings for statistics aggregation."""
    if not engine_value or not engine_value.strip():
        return ["unknown"]

    normalized = []
    for part in engine_value.split(","):
        name = part.strip().lower()
        if name:
            normalized.append(name)

    return normalized or ["unknown"]


def hash_url(url: str) -> str:
    """Generate SHA256 hash for URL."""
    return hashlib.sha256(url.encode()).hexdigest()


class CacheManager:
    """Manages SQLite index and file storage for cached content."""

    def __init__(self, db_path: str, store_dir: str):
        self.db_path = db_path
        self.store_dir = store_dir

        os.makedirs(store_dir, exist_ok=True)
        os.makedirs(os.path.dirname(db_path), exist_ok=True)

        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database with cache table."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS cache (
                    id INTEGER PRIMARY KEY,
                    url TEXT UNIQUE NOT NULL,
                    file_hash TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    title TEXT,
                    keyword TEXT NOT NULL,
                    cached_date TEXT,
                    published_date TEXT,
                    engine TEXT
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_keyword ON cache(keyword)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_url ON cache(url)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_cached_date ON cache(cached_date)")
            conn.commit()

    def save(
        self,
        url: str,
        content: str,
        keyword: str,
        metadata: dict,
    ) -> str:
        """Save content to file and index in SQLite."""
        file_hash = hash_url(url)
        file_path = os.path.join(self.store_dir, f"{file_hash}.md")

        # Save file
        with open(file_path, "w") as f:
            f.write(content)

        cached_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Index in SQLite
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO cache
                (url, file_hash, file_path, title, keyword, cached_date, published_date, engine)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                url,
                file_hash,
                file_path,
                metadata.get("title", ""),
                keyword,
                cached_date,
                metadata.get("published_date", ""),
                metadata.get("engine", ""),
            ))
            conn.commit()

        return file_path

    def exists(self, url: str) -> bool:
        """Check if URL is already cached."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM cache WHERE url = ? LIMIT 1",
                (url,)
            )
            return cursor.fetchone() is not None

    def get_file_path(self, url: str) -> str:
        """Get file path for URL (regardless of cached status)."""
        file_hash = hash_url(url)
        return os.path.join(self.store_dir, f"{file_hash}.md")

    def exact_match(self, keyword: str) -> list[CacheEntry]:
        """Find entries with exact keyword match using SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                """
                SELECT url, file_path, title, keyword, cached_date, engine
                FROM cache
                WHERE keyword = ?
                ORDER BY cached_date DESC, id DESC
                """,
                (keyword,),
            )
            return [self._load_entry_content(self._row_to_entry(row)) for row in cursor.fetchall()]

    def partial_match(
        self,
        keyword: str,
        time_range: str | None = None,
    ) -> list[CacheEntry]:
        """Find entries with partial keyword match using SQLite."""
        sql = [
            """
            SELECT url, file_path, title, keyword, cached_date, engine
            FROM cache
            WHERE lower(keyword) LIKE ?
            """
        ]
        params: list[str] = [f"%{keyword.lower()}%"]

        if time_range and time_range in VALID_TIME_RANGES:
            sql.append(f"AND datetime(cached_date) >= {TIME_RANGE_SQL[time_range]}")

        sql.append("ORDER BY cached_date DESC, id DESC")

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("\n".join(sql), params)
            return [self._load_entry_content(self._row_to_entry(row)) for row in cursor.fetchall()]

    def _row_to_entry(self, row: sqlite3.Row) -> CacheEntry:
        """Convert SQLite row to CacheEntry."""
        return CacheEntry(
            url=row["url"],
            file_path=row["file_path"],
            title=row["title"] or "",
            keyword=row["keyword"],
            cached_date=row["cached_date"] or "",
            engine=row["engine"] or "",
            content="",  # Loaded separately
        )

    def _load_entry_content(self, entry: CacheEntry) -> CacheEntry:
        """Populate cached Markdown content for an entry when available."""
        if os.path.exists(entry.file_path):
            with open(entry.file_path) as f:
                entry.content = f.read()
        return entry

    def cleanup_missing_files(self) -> int:
        """Remove entries whose files are missing from SQLite."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT url, file_path FROM cache")
            missing_urls = []

            for row in cursor.fetchall():
                if not os.path.exists(row["file_path"]):
                    missing_urls.append(row["url"])

            # Remove from SQLite
            for url in missing_urls:
                conn.execute("DELETE FROM cache WHERE url = ?", (url,))
            conn.commit()

        return len(missing_urls)

    def rebuild_index_from_db(self) -> int:
        """Compatibility shim after removing keyword index files.

        Returns the number of distinct keywords tracked in SQLite.
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(DISTINCT keyword) FROM cache")
            return int(cursor.fetchone()[0] or 0)

    def stats(self) -> dict:
        """Summarize cache entry counts, size, keyword variety, and source distribution."""
        total_entries = 0
        keywords = set()
        total_size_bytes = 0
        engines: dict[str, int] = {}
        domains: dict[str, int] = {}
        missing_files = 0

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT url, file_path, keyword, engine FROM cache")

            for row in cursor.fetchall():
                total_entries += 1
                keywords.add(row["keyword"])

                for engine in normalize_engine_names(row["engine"] or ""):
                    engines[engine] = engines.get(engine, 0) + 1

                domain = urlparse(row["url"]).netloc or "unknown"
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
