"""Wrap the newsboat CLI + read its SQLite cache."""
from __future__ import annotations

import re
import shutil
import sqlite3
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .render import html_to_text, unix_to_iso


@dataclass
class Paths:
    root: Path

    @property
    def urls(self) -> Path:
        return self.root / "feeds" / "urls"

    @property
    def conf(self) -> Path:
        return self.root / "config" / "newsboat.conf"

    @property
    def cache(self) -> Path:
        return self.root / "data" / "cache.db"

    @property
    def error_log(self) -> Path:
        return self.root / "data" / "last-error.log"


def find_project_root(start: Path | None = None) -> Path:
    """Walk up until we find pyproject.toml. Falls back to ~/Workspace/my-news."""
    here = (start or Path(__file__)).resolve()
    for parent in (here, *here.parents):
        if (parent / "pyproject.toml").is_file():
            return parent
    fallback = Path.home() / "Workspace" / "my-news"
    if (fallback / "pyproject.toml").is_file():
        return fallback
    raise RuntimeError("Could not locate my-news project root (pyproject.toml not found)")


def reload_feeds(paths: Paths, *, timeout: int = 120) -> None:
    """Invoke `newsboat -x reload`. Errors are logged but not raised."""
    if not shutil.which("newsboat"):
        raise RuntimeError("newsboat not installed; run: brew install newsboat")
    if not paths.urls.is_file():
        raise RuntimeError(f"feeds/urls not found at {paths.urls}")

    paths.cache.parent.mkdir(parents=True, exist_ok=True)
    cmd = [
        "newsboat",
        "-x", "reload",
        "-u", str(paths.urls),
        "-c", str(paths.cache),
        "-C", str(paths.conf),
        "-d", str(paths.error_log),
        "-l", "3",
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        paths.error_log.write_text(
            f"[{datetime.now(timezone.utc).isoformat()}] newsboat reload timed out after {timeout}s\n"
            f"stderr: {e.stderr or ''}\n",
            encoding="utf-8",
        )
        return

    if result.returncode != 0 or result.stderr.strip():
        paths.error_log.write_text(
            f"[{datetime.now(timezone.utc).isoformat()}] newsboat exit={result.returncode}\n"
            f"stderr:\n{result.stderr}\n"
            f"stdout:\n{result.stdout}\n",
            encoding="utf-8",
        )


_DURATION_RE = re.compile(r"^\s*(\d+)\s*([smhd])\s*$", re.IGNORECASE)


def parse_since(spec: str) -> int:
    """Parse '24h', '30m', '7d' into seconds."""
    m = _DURATION_RE.match(spec)
    if not m:
        raise ValueError(f"Invalid --since value {spec!r}; expected like '24h', '30m', '7d'")
    n, unit = int(m.group(1)), m.group(2).lower()
    return n * {"s": 1, "m": 60, "h": 3600, "d": 86400}[unit]


def fetch_items(
    paths: Paths,
    *,
    unread_only: bool = False,
    since_seconds: int | None = None,
    feed_filter: str | None = None,
    limit: int | None = None,
    full_content: bool = False,
) -> list[dict[str, Any]]:
    """Query rss_item with optional filters. feed_filter matches feed title or URL (case-insensitive substring)."""
    if not paths.cache.is_file():
        return []
    with sqlite3.connect(paths.cache) as conn:
        conn.row_factory = sqlite3.Row
        clauses = ["i.deleted = 0"]
        params: list[Any] = []
        if unread_only:
            clauses.append("i.unread = 1")
        if since_seconds is not None:
            cutoff = int(datetime.now(tz=timezone.utc).timestamp()) - since_seconds
            clauses.append("i.pubDate >= ?")
            params.append(cutoff)
        if feed_filter:
            clauses.append("(LOWER(f.title) LIKE ? OR LOWER(f.rssurl) LIKE ?)")
            needle = f"%{feed_filter.lower()}%"
            params.extend([needle, needle])
        query = f"""
            SELECT i.id, i.title, i.url, i.author, i.pubDate, i.content,
                   i.unread, i.feedurl, f.title AS feed_title, f.rssurl
            FROM rss_item i
            JOIN rss_feed f ON i.feedurl = f.rssurl
            WHERE {' AND '.join(clauses)}
            ORDER BY i.pubDate DESC
        """
        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)
        rows = conn.execute(query, params).fetchall()

    tag_map = _read_tag_map(paths.urls)
    max_chars = None if full_content else 4000
    return [_row_to_item(r, tag_map, max_chars=max_chars) for r in rows]


def fetch_unread(paths: Paths, *, since_seconds: int | None = None) -> list[dict[str, Any]]:
    return fetch_items(paths, unread_only=True, since_seconds=since_seconds)


def fetch_one(paths: Paths, identifier: str) -> dict[str, Any] | None:
    """Look up a single item by integer id or by URL match (case-insensitive exact)."""
    if not paths.cache.is_file():
        return None
    with sqlite3.connect(paths.cache) as conn:
        conn.row_factory = sqlite3.Row
        try:
            int_id = int(identifier)
        except ValueError:
            int_id = None

        if int_id is not None:
            row = conn.execute(
                """
                SELECT i.id, i.title, i.url, i.author, i.pubDate, i.content,
                       i.unread, i.feedurl, f.title AS feed_title, f.rssurl
                FROM rss_item i
                JOIN rss_feed f ON i.feedurl = f.rssurl
                WHERE i.id = ? AND i.deleted = 0
                """,
                (int_id,),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT i.id, i.title, i.url, i.author, i.pubDate, i.content,
                       i.unread, i.feedurl, f.title AS feed_title, f.rssurl
                FROM rss_item i
                JOIN rss_feed f ON i.feedurl = f.rssurl
                WHERE LOWER(i.url) = LOWER(?) AND i.deleted = 0
                LIMIT 1
                """,
                (identifier,),
            ).fetchone()

    if row is None:
        return None
    tag_map = _read_tag_map(paths.urls)
    return _row_to_item(row, tag_map, max_chars=None)


def _row_to_item(row: sqlite3.Row, tag_map: dict[str, list[str]], *, max_chars: int | None) -> dict[str, Any]:
    raw_html = row["content"] or ""
    item: dict[str, Any] = {
        "id": row["id"],
        "title": row["title"] or "(无标题)",
        "url": row["url"],
        "author": row["author"] or None,
        "pub_date": unix_to_iso(row["pubDate"]),
        "unread": bool(row["unread"]),
        "content_text": html_to_text(raw_html, max_chars=max_chars),
        "feed_title": row["feed_title"] or row["rssurl"],
        "feed_url": row["rssurl"],
        "tags": tag_map.get(row["rssurl"], []),
    }
    if max_chars is None:
        item["content_html"] = raw_html
    return item


def mark_read(paths: Paths, ids: list[int]) -> None:
    if not ids or not paths.cache.is_file():
        return
    with sqlite3.connect(paths.cache) as conn:
        placeholders = ",".join("?" * len(ids))
        conn.execute(
            f"UPDATE rss_item SET unread = 0 WHERE id IN ({placeholders})",
            ids,
        )
        conn.commit()


def list_feeds(paths: Paths) -> list[dict[str, Any]]:
    tag_map = _read_tag_map(paths.urls)
    feeds = []
    for url, tags in tag_map.items():
        feeds.append({"url": url, "tags": tags})
    return feeds


def group_by_feed(items: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in items:
        grouped[item["feed_title"]].append(item)
    return dict(grouped)


def _read_tag_map(urls_path: Path) -> dict[str, list[str]]:
    if not urls_path.is_file():
        return {}
    tag_map: dict[str, list[str]] = {}
    for raw_line in urls_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        tokens = _tokenize_urls_line(line)
        if not tokens:
            continue
        url, *tags = tokens
        tag_map[url] = tags
    return tag_map


def _tokenize_urls_line(line: str) -> list[str]:
    """Split a newsboat urls line: URL plus optional "quoted" tags."""
    tokens: list[str] = []
    i, n = 0, len(line)
    while i < n:
        while i < n and line[i].isspace():
            i += 1
        if i >= n:
            break
        if line[i] == '"':
            j = line.find('"', i + 1)
            if j == -1:
                tokens.append(line[i + 1 :])
                break
            tokens.append(line[i + 1 : j])
            i = j + 1
        else:
            j = i
            while j < n and not line[j].isspace():
                j += 1
            tokens.append(line[i:j])
            i = j
    return tokens
