"""Markdown file store for cache content."""

import hashlib
import os


def hash_url(url: str) -> str:
    """Generate SHA256 hash for URL."""
    return hashlib.sha256(url.encode()).hexdigest()


class CacheStore:
    """Handles cache file path resolution and markdown persistence."""

    def __init__(self, store_dir: str):
        self.store_dir = store_dir
        os.makedirs(store_dir, exist_ok=True)

    def path_for(self, url: str) -> str:
        """Get deterministic cache file path for a URL."""
        return os.path.join(self.store_dir, f"{hash_url(url)}.md")

    def write(self, url: str, content: str) -> str:
        """Write markdown content for a URL and return the cache file path."""
        file_path = self.path_for(url)
        with open(file_path, "w") as f:
            f.write(content)
        return file_path

    def read(self, file_path: str) -> str:
        """Read markdown content from a file path."""
        with open(file_path) as f:
            return f.read()
