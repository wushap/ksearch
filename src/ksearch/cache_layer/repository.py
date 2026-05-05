"""SQLite repository for cache metadata and query operations."""

import os
import sqlite3
from urllib.parse import urlparse


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


class CacheRepository:
    """Owns SQLite schema and metadata queries."""

    def __init__(self, db_path: str):
        self.db_path = db_path
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.init_db()

    def init_db(self) -> None:
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

    def upsert(
        self,
        *,
        url: str,
        file_hash: str,
        file_path: str,
        keyword: str,
        cached_date: str,
        metadata: dict,
    ) -> None:
        """Insert or replace a cache metadata row."""
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

    def exists(self, url: str) -> bool:
        """Check if URL is already cached."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "SELECT 1 FROM cache WHERE url = ? LIMIT 1",
                (url,),
            )
            return cursor.fetchone() is not None

    def exact_match_rows(self, keyword: str) -> list[sqlite3.Row]:
        """Find rows with exact keyword match."""
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
            return cursor.fetchall()

    def partial_match_rows(
        self,
        keyword: str,
        time_range: str | None = None,
    ) -> list[sqlite3.Row]:
        """Find rows with partial keyword match."""
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
            return cursor.fetchall()

    def rows_for_cleanup(self) -> list[sqlite3.Row]:
        """Get rows used to remove missing file entries."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT url, file_path FROM cache").fetchall()

    def delete_urls(self, urls: list[str]) -> None:
        """Delete cache rows for URL list."""
        if not urls:
            return
        with sqlite3.connect(self.db_path) as conn:
            for url in urls:
                conn.execute("DELETE FROM cache WHERE url = ?", (url,))
            conn.commit()

    def count_distinct_keywords(self) -> int:
        """Count distinct keywords in SQLite cache table."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("SELECT COUNT(DISTINCT keyword) FROM cache")
            return int(cursor.fetchone()[0] or 0)

    def stats_rows(self) -> list[sqlite3.Row]:
        """Read rows used by cache stats."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT url, file_path, keyword, engine FROM cache").fetchall()

    @staticmethod
    def build_domain(url: str) -> str:
        """Extract domain for stats aggregation."""
        return urlparse(url).netloc or "unknown"
