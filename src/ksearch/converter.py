"""Content converter using markitdown with noise cleaning."""

import re

import requests
from markitdown import MarkItDown

try:
    from trafilatura import extract as trafilatura_extract
except ImportError:
    trafilatura_extract = None


# Lines that are clearly navigation/boilerplate (single line patterns)
NOISE_LINE_PATTERNS = [
    r'^\[Skip\]',
    r'^\[Close\]',
    r'^\[Menu\]',
    r'^\[Home\]',
    r'^\[Donate\]',
    r'^\[Log in\]',
    r'^\[Sign up\]',
    r'^\[Sign In\]',
    r'^\[Subscribe\]',
    r'^\[Get Certified\]',
    r'^\[Upgrade\]',
    r'^\[My.*\]',
    r'^\[All.*Services\]',
    r'^\[Your.*\]',
    r'^\[★',
    r'^Search.*field',
    r'^See More',
    r'^Toggle navigation',
    r'^Change language',
    r'^View desktop',
    r'^Menu$',
    r'^GO$',
    r'^Search This Site',
    r'^Add a comment$',
    r'^Post Your Answer$',
    r'^Reply$',
    r'^Copy link$',
    r'^Loading…$',
    r'^Loading\.\.\.$',
    r'^Sorry, something went wrong\.$',
    r'^Uh oh!$',
    r'^\*×\*$',
    r'^\*\*A A\*\*$',
    r'^Smaller$',
    r'^Larger$',
    r'^Reset$',
    r'^Socialize$',
    r'^\+ Smaller$',
    r'^\+ Larger$',
    r'^\+ Reset$',
    r'^\+ \[LinkedIn\]',
    r'^\+ \[Mastodon\]',
    r'^\+ \[.*\]',
    r'^\[[▼▲].*\]',
    r'^\*\*A A\*\*$',  # font size controls
]

# Block patterns to remove (multi-line)
NOISE_BLOCK_PATTERNS = [
    # Fallback notices
    r'\*Notice:\*.*?(?:stylesheets?|run\.).*',
    r'This page displays a fallback.*',
    r'Please enable JavaScript.*',
    r'interactive scripts did not run.*',

    # Copyright/footer blocks
    r'©.*(?:Copyright|Valve).*',
    r'All rights reserved.*',
    r'Terms of Service.*',
    r'Privacy Policy.*',
    r'Subscriber Agreement.*',
    r'Refunds.*',
    r'Cookies.*',
    r'Accessibility.*',
    r'Legal.*',

    # Ad patterns
    r'advertisement.*',
    r'sponsored.*',
]

# Section headings or prompts where article content is usually over
NOISE_SECTION_PATTERNS = [
    r'^##\s+\d+\s+Comments?$',
    r'^##\s+Comments?(?:\s*\(\d+\))?$',
    r'^##\s+Related(?:\s+questions)?$',
    r'^##\s+Your Answer$',
    r'^##\s+Answers?$',
    r'^Sign up to request clarification.*',
    r'^To join this conversation.*',
    r'^Already have an account\?$',
    r'^Start asking to get answers$',
    r'^Explore related questions$',
    r'^Subscribe to RSS$',
    r'^Footer$',
]

# Consecutive link block (nav menu)
NAV_LINK_BLOCK = r'(\* \[[^\]]+\]\([^\)]+\)[\s]*){4,}'


def _truncate_at_noise_sections(lines: list[str]) -> list[str]:
    """Drop trailing discussion/footer sections once main content is present."""
    contentful_lines = 0
    truncated = []

    for line in lines:
        stripped = line.strip()
        if stripped:
            contentful_lines += 1

        if contentful_lines >= 3:
            for pattern in NOISE_SECTION_PATTERNS:
                if re.match(pattern, stripped, re.IGNORECASE):
                    return truncated

        truncated.append(line)

    return truncated


def clean_content(content: str) -> str:
    """Remove navigation boilerplate and noise from converted content."""

    lines = content.split('\n')
    cleaned_lines = []

    skip_line = False
    for line in lines:
        stripped = line.strip()

        # Keep empty lines for now (compact later)
        if not stripped:
            cleaned_lines.append('')
            continue

        skip_line = False

        # Check noise line patterns
        for pattern in NOISE_LINE_PATTERNS:
            if re.match(pattern, stripped, re.IGNORECASE):
                skip_line = True
                break

        if skip_line:
            continue

        # Check noise block patterns
        for pattern in NOISE_BLOCK_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                skip_line = True
                break

        if skip_line:
            continue

        # Skip pure nav links (short link-only lines)
        if re.match(r'^\[[^\]]+\]\([^\)]+\)$', stripped):
            skip_line = True
            continue

        # Skip list-item nav links (* [link](url) or + [link](url))
        if re.match(r'^[\*\+] \[[^\]]+\]\([^\)]+\)$', stripped):
            skip_line = True
            continue

        cleaned_lines.append(line)

    cleaned_lines = _truncate_at_noise_sections(cleaned_lines)

    # Rejoin and remove nav link blocks (list format)
    content = '\n'.join(cleaned_lines)
    content = re.sub(NAV_LINK_BLOCK, '', content)

    # Clean up excessive blank lines
    content = re.sub(r'\n{3,}', '\n\n', content)

    # Trim
    content = content.strip()

    return content


class ContentConverter:
    """Converts URLs to Markdown using markitdown with noise cleaning."""

    def __init__(self, timeout: int = 30):
        self.timeout = timeout
        # Per-URL timeout should be shorter (10s) to avoid blocking
        self.url_timeout = min(timeout, 10)
        self._md = MarkItDown()
        self._headers = {
            "User-Agent": (
                "Mozilla/5.0 (X11; Linux x86_64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }

    def _extract_main_content(self, url: str) -> str:
        """Fetch page HTML and extract the primary article body when possible."""
        if trafilatura_extract is None:
            return ""

        try:
            response = requests.get(url, headers=self._headers, timeout=self.url_timeout)
            response.raise_for_status()
        except Exception:
            return ""

        extracted = trafilatura_extract(
            response.text,
            url=url,
            output_format="markdown",
            include_comments=False,
            include_tables=False,
            favor_precision=True,
            deduplicate=True,
        )
        if not extracted:
            return ""

        return clean_content(extracted)

    def _convert_with_markitdown(self, url: str) -> str:
        """Fallback conversion path using markitdown."""
        import threading

        result_container = []
        exception_container = []

        def worker():
            try:
                result = self._md.convert(url)
                result_container.append(result.text_content)
            except Exception as e:
                exception_container.append(e)

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout=self.url_timeout)

        if thread.is_alive():
            # Timed out - thread still running
            return ""

        if exception_container:
            return ""

        raw_content = result_container[0] if result_container else ""
        return clean_content(raw_content)

    def convert_url(self, url: str) -> str:
        """Convert URL content to Markdown and clean noise."""
        cleaned = self._extract_main_content(url)
        if len(cleaned) < 50:
            cleaned = self._convert_with_markitdown(url)

        # Return empty if too short after cleaning (redirect pages)
        if len(cleaned) < 50:
            return ""

        return cleaned
