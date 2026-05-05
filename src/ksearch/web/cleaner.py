"""Web content cleaning utilities."""

import re


# Lines that are clearly navigation/boilerplate (single line patterns)
NOISE_LINE_PATTERNS = [
    r"^\[Skip\]",
    r"^\[Close\]",
    r"^\[Menu\]",
    r"^\[Home\]",
    r"^\[Donate\]",
    r"^\[Log in\]",
    r"^\[Sign up\]",
    r"^\[Sign In\]",
    r"^\[Subscribe\]",
    r"^\[Get Certified\]",
    r"^\[Upgrade\]",
    r"^\[My.*\]",
    r"^\[All.*Services\]",
    r"^\[Your.*\]",
    r"^\[★",
    r"^Search.*field",
    r"^See More",
    r"^Toggle navigation",
    r"^Change language",
    r"^View desktop",
    r"^Menu$",
    r"^GO$",
    r"^Search This Site",
    r"^Add a comment$",
    r"^Post Your Answer$",
    r"^Reply$",
    r"^Copy link$",
    r"^Loading…$",
    r"^Loading\.\.\.$",
    r"^Sorry, something went wrong\.$",
    r"^Uh oh!$",
    r"^\*×\*$",
    r"^\*\*A A\*\*$",
    r"^Smaller$",
    r"^Larger$",
    r"^Reset$",
    r"^Socialize$",
    r"^\+ Smaller$",
    r"^\+ Larger$",
    r"^\+ Reset$",
    r"^\+ \[LinkedIn\]",
    r"^\+ \[Mastodon\]",
    r"^\+ \[.*\]",
    r"^\[[▼▲].*\]",
    r"^\*\*A A\*\*$",
]

# Block patterns to remove (multi-line)
NOISE_BLOCK_PATTERNS = [
    r"\*Notice:\*.*?(?:stylesheets?|run\.).*",
    r"This page displays a fallback.*",
    r"Please enable JavaScript.*",
    r"interactive scripts did not run.*",
    r"©.*(?:Copyright|Valve).*",
    r"All rights reserved.*",
    r"Terms of Service.*",
    r"Privacy Policy.*",
    r"Subscriber Agreement.*",
    r"Refunds.*",
    r"Cookies.*",
    r"Accessibility.*",
    r"Legal.*",
    r"advertisement.*",
    r"sponsored.*",
]

# Section headings or prompts where article content is usually over
NOISE_SECTION_PATTERNS = [
    r"^##\s+\d+\s+Comments?$",
    r"^##\s+Comments?(?:\s*\(\d+\))?$",
    r"^##\s+Related(?:\s+questions)?$",
    r"^##\s+Your Answer$",
    r"^##\s+Answers?$",
    r"^Sign up to request clarification.*",
    r"^To join this conversation.*",
    r"^Already have an account\?$",
    r"^Start asking to get answers$",
    r"^Explore related questions$",
    r"^Subscribe to RSS$",
    r"^Footer$",
]

NAV_LINK_BLOCK = r"(\* \[[^\]]+\]\([^\)]+\)[\s]*){4,}"


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
    lines = content.split("\n")
    cleaned_lines = []

    for line in lines:
        stripped = line.strip()

        if not stripped:
            cleaned_lines.append("")
            continue

        skip_line = False

        for pattern in NOISE_LINE_PATTERNS:
            if re.match(pattern, stripped, re.IGNORECASE):
                skip_line = True
                break
        if skip_line:
            continue

        for pattern in NOISE_BLOCK_PATTERNS:
            if re.search(pattern, stripped, re.IGNORECASE):
                skip_line = True
                break
        if skip_line:
            continue

        if re.match(r"^\[[^\]]+\]\([^\)]+\)$", stripped):
            continue
        if re.match(r"^[\*\+] \[[^\]]+\]\([^\)]+\)$", stripped):
            continue

        cleaned_lines.append(line)

    cleaned_lines = _truncate_at_noise_sections(cleaned_lines)
    content = "\n".join(cleaned_lines)
    content = re.sub(NAV_LINK_BLOCK, "", content)
    content = re.sub(r"\n{3,}", "\n\n", content)
    return content.strip()
