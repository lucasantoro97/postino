from __future__ import annotations

import re

_URL_RE = re.compile(r"https?://[^\s<>()\"']+")
_TRAILING_PUNCT = ".,;:!?)\"]}'"

_MEETING_HOST_HINTS = (
    "meet.google.com",
    "zoom.us",
    "teams.microsoft.com",
    "webex.com",
    "gotomeeting.com",
)


def extract_urls(text: str) -> list[str]:
    """Extract URLs from free-form text, preserving order and trimming trailing punctuation."""
    if not text:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for m in _URL_RE.finditer(text):
        url = m.group(0).rstrip(_TRAILING_PUNCT)
        if not url or url in seen:
            continue
        seen.add(url)
        out.append(url)
    return out


def extract_meeting_links(text: str) -> list[str]:
    """Extract likely video-call links; if none found, return all URLs."""
    urls = extract_urls(text)
    if not urls:
        return []
    meeting = [u for u in urls if any(hint in u.lower() for hint in _MEETING_HOST_HINTS)]
    return meeting if meeting else urls
