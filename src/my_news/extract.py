"""Fetch an article URL and extract readable body via trafilatura."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import trafilatura

Status = Literal["ok", "fetch_failed", "extract_failed", "empty"]


@dataclass
class Extracted:
    status: Status
    text: str
    length: int


def extract_article(url: str) -> Extracted:
    """Download `url` and return its main article body as Markdown.

    Never raises — returns a status field instead so callers can cache failures.
    """
    try:
        downloaded = trafilatura.fetch_url(url)
    except Exception:
        return Extracted("fetch_failed", "", 0)

    if downloaded is None:
        return Extracted("fetch_failed", "", 0)

    try:
        text = trafilatura.extract(
            downloaded,
            output_format="markdown",
            favor_precision=True,
            include_links=True,
            include_comments=False,
        )
    except Exception:
        return Extracted("extract_failed", "", 0)

    if not text:
        return Extracted("empty", "", 0)
    return Extracted("ok", text, len(text))
