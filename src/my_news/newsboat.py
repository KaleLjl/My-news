"""Wrap the newsboat CLI + read its SQLite cache."""
from __future__ import annotations

import os
import re
import shutil
import sqlite3
import subprocess
import sys
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .render import html_to_text, unix_to_iso


_DEFAULT_URLS_TEMPLATE = """\
# my-news feeds — one feed per line, newsboat format.
# URL [optional "quoted tags"]
# Example:
# https://simonwillison.net/atom/everything/    "ai" "blog"
"""


def _xdg_dir(env_var: str, default: Path) -> Path:
    raw = os.environ.get(env_var)
    if raw:
        return Path(raw).expanduser()
    return default


def default_config_dir() -> Path:
    """`$MY_NEWS_CONFIG` if set, else `$XDG_CONFIG_HOME/my-news` (default `~/.config/my-news`)."""
    override = os.environ.get("MY_NEWS_CONFIG")
    if override:
        return Path(override).expanduser()
    base = _xdg_dir("XDG_CONFIG_HOME", Path.home() / ".config")
    return base / "my-news"


def default_data_dir() -> Path:
    """`$MY_NEWS_DATA` if set, else `$XDG_DATA_HOME/my-news` (default `~/.local/share/my-news`)."""
    override = os.environ.get("MY_NEWS_DATA")
    if override:
        return Path(override).expanduser()
    base = _xdg_dir("XDG_DATA_HOME", Path.home() / ".local" / "share")
    return base / "my-news"


@dataclass
class Paths:
    urls: Path
    conf: Path
    cache: Path
    error_log: Path
    digests: Path

    @property
    def config_dir(self) -> Path:
        return self.urls.parent.parent

    @property
    def data_dir(self) -> Path:
        return self.cache.parent

    @classmethod
    def from_env(cls) -> "Paths":
        """User-dir layout (XDG): config under `~/.config/my-news`, data under `~/.local/share/my-news`."""
        cfg = default_config_dir()
        data = default_data_dir()
        return cls(
            urls=cfg / "feeds" / "urls",
            conf=cfg / "config" / "newsboat.conf",
            cache=data / "cache.db",
            error_log=data / "last-error.log",
            digests=data / "digests",
        )

    @classmethod
    def from_root(cls, root: Path) -> "Paths":
        """Legacy in-repo layout. Kept behind `--root` for dev/test."""
        return cls(
            urls=root / "feeds" / "urls",
            conf=root / "config" / "newsboat.conf",
            cache=root / "data" / "cache.db",
            error_log=root / "data" / "last-error.log",
            digests=root / "digests",
        )


def ensure_feeds_file(paths: Paths) -> bool:
    """Create an empty feeds/urls with a template if missing. Returns True if just created."""
    if paths.urls.is_file():
        return False
    paths.urls.parent.mkdir(parents=True, exist_ok=True)
    paths.urls.write_text(_DEFAULT_URLS_TEMPLATE, encoding="utf-8")
    print(
        f"[my-news] created empty feeds file at {paths.urls}\n"
        f"          edit it to add your RSS sources (one per line), then re-run.",
        file=sys.stderr,
    )
    return True


def find_project_root(start: Path | None = None) -> Path | None:
    """Walk up looking for a my-news repo (pyproject.toml with name='my-news'). Returns None if not found."""
    here = (start or Path.cwd()).resolve()
    for parent in (here, *here.parents):
        pyproject = parent / "pyproject.toml"
        if pyproject.is_file():
            try:
                if 'name = "my-news"' in pyproject.read_text(encoding="utf-8"):
                    return parent
            except OSError:
                continue
    return None


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
    return [_row_to_item(r, tag_map, include_html=False) for r in rows]


def fetch_unread(paths: Paths, *, since_seconds: int | None = None) -> list[dict[str, Any]]:
    return fetch_items(paths, unread_only=True, since_seconds=since_seconds)


_EXTRACTED_CONTENT_SCHEMA = """
CREATE TABLE IF NOT EXISTS extracted_content (
    item_id INTEGER PRIMARY KEY,
    url TEXT NOT NULL,
    fetched_at INTEGER NOT NULL,
    status TEXT NOT NULL,
    length INTEGER NOT NULL,
    text TEXT NOT NULL
)
"""


def _ensure_extracted_table(conn: sqlite3.Connection) -> None:
    conn.execute(_EXTRACTED_CONTENT_SCHEMA)


def get_cached_extract(paths: Paths, item_id: int) -> dict[str, Any] | None:
    if not paths.cache.is_file():
        return None
    with sqlite3.connect(paths.cache) as conn:
        conn.row_factory = sqlite3.Row
        _ensure_extracted_table(conn)
        row = conn.execute(
            "SELECT url, fetched_at, status, length, text FROM extracted_content WHERE item_id = ?",
            (item_id,),
        ).fetchone()
    if row is None:
        return None
    return {
        "status": row["status"],
        "fetched_at": unix_to_iso(row["fetched_at"]),
        "length": row["length"],
        "text": row["text"],
    }


def save_extract(
    paths: Paths,
    item_id: int,
    url: str,
    *,
    status: str,
    text: str,
    length: int,
) -> None:
    ts = int(datetime.now(tz=timezone.utc).timestamp())
    with sqlite3.connect(paths.cache) as conn:
        _ensure_extracted_table(conn)
        conn.execute(
            """
            INSERT INTO extracted_content (item_id, url, fetched_at, status, length, text)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_id) DO UPDATE SET
                url = excluded.url,
                fetched_at = excluded.fetched_at,
                status = excluded.status,
                length = excluded.length,
                text = excluded.text
            """,
            (item_id, url, ts, status, length, text),
        )
        conn.commit()


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
    return _row_to_item(row, tag_map, include_html=True)


def _row_to_item(row: sqlite3.Row, tag_map: dict[str, list[str]], *, include_html: bool) -> dict[str, Any]:
    raw_html = row["content"] or ""
    item: dict[str, Any] = {
        "id": row["id"],
        "title": row["title"] or "(无标题)",
        "url": row["url"],
        "author": row["author"] or None,
        "pub_date": unix_to_iso(row["pubDate"]),
        "unread": bool(row["unread"]),
        "content_text": html_to_text(raw_html, max_chars=None),
        "feed_title": row["feed_title"] or row["rssurl"],
        "feed_url": row["rssurl"],
        "tags": tag_map.get(row["rssurl"], []),
    }
    if include_html:
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
