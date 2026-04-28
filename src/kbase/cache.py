"""Cache management with SQLite index, file storage, and keyword index files."""

import hashlib
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from kbase.models import CacheEntry


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
    """Manages SQLite index, file storage, and keyword index files for cached content."""

    def __init__(self, db_path: str, store_dir: str):
        self.db_path = db_path
        self.store_dir = store_dir
        self.index_dir = os.path.join(store_dir, "_index")

        os.makedirs(store_dir, exist_ok=True)
        os.makedirs(self.index_dir, exist_ok=True)
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
        """Save content to file and index in SQLite + keyword index file."""
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

        # Update keyword index file
        self._update_keyword_index(keyword, {
            "url": url,
            "file_hash": file_hash,
            "title": metadata.get("title", ""),
            "cached_date": cached_date.split()[0],  # YYYY-MM-DD only
            "engine": metadata.get("engine", ""),
        })

        return file_path

    def _update_keyword_index(self, keyword: str, entry: dict) -> None:
        """Update or create keyword index file."""
        index_file = os.path.join(self.index_dir, f"{keyword}.json")

        # Load existing index
        if os.path.exists(index_file):
            with open(index_file) as f:
                data = json.load(f)
        else:
            data = {"keyword": keyword, "entries": []}

        # Remove existing entry with same URL (update case)
        data["entries"] = [e for e in data["entries"] if e["url"] != entry["url"]]

        # Add new entry
        data["entries"].append(entry)

        # Save index
        with open(index_file, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    def _load_keyword_index(self, keyword: str) -> dict | None:
        """Load keyword index file."""
        index_file = os.path.join(self.index_dir, f"{keyword}.json")
        if os.path.exists(index_file):
            with open(index_file) as f:
                return json.load(f)
        return None

    def _list_keyword_indices(self) -> list[str]:
        """List all keyword index files."""
        indices = []
        for f in os.listdir(self.index_dir):
            if f.endswith(".json"):
                indices.append(f[:-5])  # Remove .json
        return indices

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
        """Find entries with exact keyword match using index file."""
        index_data = self._load_keyword_index(keyword)
        if not index_data:
            return []

        entries = []
        for e in index_data["entries"]:
            file_path = os.path.join(self.store_dir, f"{e['file_hash']}.md")
            content = ""
            if os.path.exists(file_path):
                with open(file_path) as f:
                    content = f.read()

            entries.append(CacheEntry(
                url=e["url"],
                file_path=file_path,
                title=e.get("title", ""),
                keyword=keyword,
                cached_date=e.get("cached_date", ""),
                engine=e.get("engine", ""),
                content=content,
            ))
        return entries

    def partial_match(
        self,
        keyword: str,
        time_range: str | None = None,
    ) -> list[CacheEntry]:
        """Find entries with partial keyword match using index files."""
        entries = []

        # Find matching keyword indices
        for kw in self._list_keyword_indices():
            if keyword.lower() in kw.lower():
                index_data = self._load_keyword_index(kw)
                if index_data:
                    for e in index_data["entries"]:
                        file_path = os.path.join(self.store_dir, f"{e['file_hash']}.md")

                        # Time range filter
                        if time_range and time_range in VALID_TIME_RANGES:
                            cached_date = e.get("cached_date", "")
                            if cached_date:
                                # Compare dates using SQLite syntax reference
                                from datetime import datetime as dt
                                try:
                                    entry_date = dt.strptime(cached_date, "%Y-%m-%d")
                                    threshold_map = {
                                        "day": dt.now() - __import__("datetime").timedelta(days=1),
                                        "week": dt.now() - __import__("datetime").timedelta(days=7),
                                        "month": dt.now() - __import__("datetime").timedelta(days=30),
                                        "year": dt.now() - __import__("datetime").timedelta(days=365),
                                    }
                                    if entry_date < threshold_map[time_range]:
                                        continue
                                except ValueError:
                                    pass

                        content = ""
                        if os.path.exists(file_path):
                            with open(file_path) as f:
                                content = f.read()

                        entries.append(CacheEntry(
                            url=e["url"],
                            file_path=file_path,
                            title=e.get("title", ""),
                            keyword=kw,
                            cached_date=e.get("cached_date", ""),
                            engine=e.get("engine", ""),
                            content=content,
                        ))
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
        """Remove entries whose files are missing from SQLite and index files."""
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT url, file_path, keyword FROM cache")
            missing_urls = []

            for row in cursor.fetchall():
                if not os.path.exists(row["file_path"]):
                    missing_urls.append((row["url"], row["keyword"]))

            # Remove from SQLite
            for url, _ in missing_urls:
                conn.execute("DELETE FROM cache WHERE url = ?", (url,))
            conn.commit()

        # Remove from index files
        for url, keyword in missing_urls:
            self._remove_from_index(keyword, url)

        return len(missing_urls)

    def _remove_from_index(self, keyword: str, url: str) -> None:
        """Remove URL from keyword index file."""
        index_data = self._load_keyword_index(keyword)
        if index_data:
            index_data["entries"] = [e for e in index_data["entries"] if e["url"] != url]
            index_file = os.path.join(self.index_dir, f"{keyword}.json")
            with open(index_file, "w") as f:
                json.dump(index_data, f, indent=2, ensure_ascii=False)

    def rebuild_index_from_db(self) -> int:
        """Rebuild all keyword index files from SQLite database."""
        keyword_entries: dict[str, list[dict]] = {}

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute("SELECT * FROM cache")

            for row in cursor.fetchall():
                kw = row["keyword"]
                if kw not in keyword_entries:
                    keyword_entries[kw] = []

                cached_date = row["cached_date"] or ""
                if cached_date:
                    cached_date = cached_date.split()[0]  # YYYY-MM-DD only

                keyword_entries[kw].append({
                    "url": row["url"],
                    "file_hash": row["file_hash"],
                    "title": row["title"] or "",
                    "cached_date": cached_date,
                    "engine": row["engine"] or "",
                })

        # Write index files
        for kw, entries in keyword_entries.items():
            index_file = os.path.join(self.index_dir, f"{kw}.json")
            with open(index_file, "w") as f:
                json.dump({"keyword": kw, "entries": entries}, f, indent=2, ensure_ascii=False)

        return len(keyword_entries)

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
