"""SearXNG API client."""

from typing import Optional

import requests

from ksearch.models import SearchResult


class SearXNGClient:
    """Client for SearXNG search API."""

    def __init__(self, base_url: str, timeout: int = 30):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def search(
        self,
        query: str,
        time_range: Optional[str] = None,
        max_results: int = 10,
    ) -> list[SearchResult]:
        """Search SearXNG and return results."""
        url = f"{self.base_url}/search"
        params = {
            "q": query,
            "format": "json",
        }

        if time_range:
            params["time_range"] = time_range

        response = requests.get(url, params=params, timeout=self.timeout)
        response.raise_for_status()

        data = response.json()
        results = []

        for item in data.get("results", [])[:max_results]:
            engines = item.get("engines")
            if engines and isinstance(engines, list):
                engine = ", ".join(engines)
            else:
                engine = item.get("engine", "")

            published_date = item.get("publishedDate")
            if published_date:
                published_date = str(published_date)
            else:
                published_date = ""

            results.append(
                SearchResult(
                    url=item.get("url", ""),
                    title=item.get("title", ""),
                    content=item.get("content", ""),
                    engine=engine,
                    published_date=published_date,
                )
            )

        return results
