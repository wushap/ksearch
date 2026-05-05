"""URL-level web extraction policies."""

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
    lowered = url.lower()
    for pattern in SKIP_URL_PATTERNS:
        if pattern in lowered:
            return True
    return False
