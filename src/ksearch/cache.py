"""Cache management with SQLite index and file storage."""

import hashlib
import os
import sqlite3
from datetime import datetime
from pathlib import Path

from ksearch.models import CacheEntry


TIME_RANGE_SQL = {
    "day": "datetime('now', '-1 day')",
    "week": "datetime('now', '-7 days')",
    "month": "datetime('now', '-30 days')",
    "year": "datetime('now', '-365 days')",
}

VALID_TIME_RANGES = {"day", "week", "month", "year"}


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

        # Index in SQLite
        cached_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

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
        """Find entries with exact keyword match."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT * FROM cache WHERE keyword = ?",
                (keyword,)
            )
            return [self._row_to_entry(row) for row in cursor.fetchall()]

    def partial_match(
        self,
        keyword: str,
        time_range: str | None = None,
    ) -> list[CacheEntry]:
        """Find entries with partial keyword match."""
        sql = "SELECT * FROM cache WHERE keyword LIKE ?"
        params = [f"%{keyword}%"]

        if time_range and time_range in VALID_TIME_RANGES:
            sql += f" AND cached_date >= {TIME_RANGE_SQL[time_range]}"

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(sql, params)
            entries = [self._row_to_entry(row) for row in cursor.fetchall()]

            # Load content from files
            for entry in entries:
                if os.path.exists(entry.file_path):
                    with open(entry.file_path) as f:
                        entry.content = f.read()

            return entries

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

    def cleanup_missing_files(self) -> int:
        """Remove entries whose files are missing."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT url, file_path FROM cache")
            missing_urls = []

            for row in cursor.fetchall():
                if not os.path.exists(row[1]):
                    missing_urls.append(row[0])

            for url in missing_urls:
                conn.execute("DELETE FROM cache WHERE url = ?", (url,))

            conn.commit()
            return len(missing_urls)