"""Content converter using markitdown with noise cleaning."""

import re
from markitdown import MarkItDown


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

# Consecutive link block (nav menu)
NAV_LINK_BLOCK = r'(\* \[[^\]]+\]\([^\)]+\)[\s]*){4,}'


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

    def convert_url(self, url: str) -> str:
        """Convert URL content to Markdown and clean noise."""
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

        # Clean the content
        cleaned = clean_content(raw_content)

        # Return empty if too short after cleaning (redirect pages)
        if len(cleaned) < 50:
            return ""

        return cleaned