"""Source health checker — HTTP reachability, RSS/Atom shape, duplicate detection.

Only stdlib: urllib for HTTP, xml.etree for parsing.
"""
from __future__ import annotations

import socket
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from xml.etree import ElementTree as ET

from . import newsboat as nb


_USER_AGENT = "my-news-doctor/1 (+https://github.com/KaleLjl/my-news)"
_ATOM_NS = "{http://www.w3.org/2005/Atom}"
_RDF_NS = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"


@dataclass
class FeedReport:
    url: str
    tags: list[str] = field(default_factory=list)
    status: str = "ok"  # ok | feed_unreachable | not_a_feed | duplicate
    http_status: int | None = None
    content_type: str | None = None
    item_count: int | None = None
    note: str | None = None


def run(paths: nb.Paths, *, timeout: float) -> dict[str, Any]:
    """Probe every feed in feeds/urls. Returns a JSON-shaped report dict."""
    feeds = _read_urls(paths.urls)
    reports = [_probe(url, tags, timeout=timeout) for url, tags in feeds]
    _mark_duplicates(reports)

    return {
        "checked_at": datetime.now(tz=timezone.utc).astimezone().isoformat(),
        "feeds_file": str(paths.urls),
        "source_count": len(reports),
        "issue_count": sum(1 for r in reports if r.status != "ok"),
        "reports": [asdict(r) for r in reports],
    }


def _read_urls(urls_path) -> list[tuple[str, list[str]]]:
    if not urls_path.is_file():
        return []
    entries: list[tuple[str, list[str]]] = []
    for raw_line in urls_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = nb._tokenize_urls_line(line)
        if not tokens:
            continue
        url, *tags = tokens
        entries.append((url, tags))
    return entries


def probe_url(url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    """One-shot probe used by `add`. Returns a dict suitable for JSON output."""
    report = _probe(url, [], timeout=timeout)
    return {
        "ok": report.status == "ok",
        "status": report.status,
        "http_status": report.http_status,
        "content_type": report.content_type,
        "item_count": report.item_count,
        "note": report.note,
    }


def _probe(url: str, tags: list[str], *, timeout: float) -> FeedReport:
    report = FeedReport(url=url, tags=tags)
    req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            report.http_status = resp.status
            report.content_type = resp.headers.get("Content-Type")
            body = resp.read(2_000_000)  # 2MB cap per feed
    except urllib.error.HTTPError as e:
        report.http_status = e.code
        report.status = "feed_unreachable"
        report.note = f"HTTP {e.code} {e.reason}"
        return report
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        report.status = "feed_unreachable"
        report.note = f"{type(e).__name__}: {getattr(e, 'reason', e)}"
        return report
    except Exception as e:  # noqa: BLE001
        report.status = "feed_unreachable"
        report.note = f"{type(e).__name__}: {e}"
        return report

    item_count = _count_feed_items(body)
    if item_count is None:
        report.status = "not_a_feed"
        report.note = "response is not RSS/Atom (no <rss>/<feed>/<RDF> root)"
        return report
    report.item_count = item_count
    return report


def _count_feed_items(body: bytes) -> int | None:
    """Return item/entry count if body parses as RSS/Atom/RDF, else None."""
    try:
        root = ET.fromstring(body)
    except ET.ParseError:
        return None

    tag = root.tag
    if tag == "rss":
        return sum(1 for _ in root.iter("item"))
    if tag == f"{_ATOM_NS}feed":
        return sum(1 for _ in root.iter(f"{_ATOM_NS}entry"))
    if tag == f"{_RDF_NS}RDF":
        return sum(1 for _ in root.iter("{http://purl.org/rss/1.0/}item"))
    return None


def _mark_duplicates(reports: list[FeedReport]) -> None:
    """Mark exact-URL duplicates (after light normalization). First occurrence keeps its status."""
    seen: dict[str, int] = {}
    for idx, r in enumerate(reports):
        key = _normalize_url(r.url)
        if key in seen:
            first_idx = seen[key]
            # If the first occurrence is reachable, mark this one as duplicate.
            r.status = "duplicate"
            r.note = f"duplicate of line {first_idx + 1} ({reports[first_idx].url})"
        else:
            seen[key] = idx


def _normalize_url(url: str) -> str:
    u = url.strip().lower()
    # strip trailing slash for comparison only
    if u.endswith("/"):
        u = u[:-1]
    return u


# --- human-readable rendering ----------------------------------------------

_STATUS_GLYPH = {
    "ok": "✓",
    "feed_unreachable": "✗",
    "not_a_feed": "✗",
    "duplicate": "⚠",
}


def render_table(payload: dict[str, Any]) -> str:
    lines = [
        f"my-news doctor · {payload['source_count']} sources checked  ({payload['feeds_file']})",
        "",
    ]
    for r in payload["reports"]:
        glyph = _STATUS_GLYPH.get(r["status"], "?")
        http = str(r["http_status"]) if r["http_status"] is not None else "-"
        ctype = (r["content_type"] or "-").split(";")[0]
        count = f"{r['item_count']} items" if r["item_count"] is not None else "-"
        url_disp = r["url"]
        if len(url_disp) > 60:
            url_disp = url_disp[:57] + "..."
        line = f"  {glyph}  {url_disp:<60}  {http:<5} {ctype:<22} {count}"
        if r["note"]:
            line += f"   ({r['note']})"
        lines.append(line)
    lines.append("")
    issue = payload["issue_count"]
    if issue == 0:
        lines.append("All feeds healthy.")
    else:
        lines.append(f"{issue} issue(s) found.")
    return "\n".join(lines)


def has_unreachable(payload: dict[str, Any]) -> bool:
    return any(r["status"] in ("feed_unreachable", "not_a_feed") for r in payload["reports"])
