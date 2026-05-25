"""Command-line entry point for my-news (Typer-based)."""
from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import typer

from . import newsboat as nb

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Fetch unread RSS items via newsboat and emit JSON.",
)


def _resolve_paths(root: Optional[Path]) -> nb.Paths:
    if root is not None:
        return nb.Paths.from_root(root.resolve())
    return nb.Paths.from_env()


@app.callback()
def _main(
    ctx: typer.Context,
    root: Optional[Path] = typer.Option(
        None,
        "--root",
        help="Legacy in-repo layout override (hidden; dev use).",
        hidden=True,
    ),
) -> None:
    ctx.obj = _resolve_paths(root)


def _print_json(payload: object) -> None:
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()


@app.command(help="Reload feeds, output unread items as JSON, mark read.")
def fetch(
    ctx: typer.Context,
    no_reload: bool = typer.Option(False, "--no-reload", help="Skip newsboat reload; read DB only."),
    no_mark: bool = typer.Option(False, "--no-mark", help="Do not mark items as read."),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        metavar="DURATION",
        help="Only items with pubDate within DURATION (e.g. 24h, 30m, 7d).",
    ),
) -> None:
    paths: nb.Paths = ctx.obj
    since_seconds = nb.parse_since(since) if since else None

    nb.ensure_feeds_file(paths)
    if not no_reload:
        nb.reload_feeds(paths)

    items = nb.fetch_unread(paths, since_seconds=since_seconds)
    by_feed = nb.group_by_feed(items)
    _print_json(
        {
            "fetched_at": datetime.now(tz=timezone.utc).astimezone().isoformat(),
            "count": len(items),
            "feed_count": len(by_feed),
            "by_feed": by_feed,
        }
    )

    if items and not no_mark:
        nb.mark_read(paths, [item["id"] for item in items])


@app.command(
    "list",
    help="List items from the cache without the unread filter (does not mark anything).",
)
def list_cmd(
    ctx: typer.Context,
    feed: Optional[str] = typer.Option(None, "--feed", metavar="QUERY",
                                       help="Filter by feed title or URL (case-insensitive substring)."),
    limit: int = typer.Option(50, "--limit", help="Max items to return."),
    since: Optional[str] = typer.Option(None, "--since", metavar="DURATION",
                                        help="Only items within DURATION (e.g. 24h, 7d)."),
    unread_only: bool = typer.Option(False, "--unread-only", help="Restrict to unread items."),
    no_reload: bool = typer.Option(False, "--no-reload", help="Skip newsboat reload; read DB only."),
) -> None:
    paths: nb.Paths = ctx.obj
    since_seconds = nb.parse_since(since) if since else None

    nb.ensure_feeds_file(paths)
    if not no_reload:
        nb.reload_feeds(paths)

    items = nb.fetch_items(
        paths,
        unread_only=unread_only,
        since_seconds=since_seconds,
        feed_filter=feed,
        limit=limit,
    )
    by_feed = nb.group_by_feed(items)
    _print_json(
        {
            "fetched_at": datetime.now(tz=timezone.utc).astimezone().isoformat(),
            "count": len(items),
            "feed_count": len(by_feed),
            "filter": {"feed": feed, "since": since, "unread_only": unread_only, "limit": limit},
            "by_feed": by_feed,
        }
    )


@app.command(help="Show one item's full content (no truncation). identifier is the item id or its URL.")
def show(
    ctx: typer.Context,
    identifier: str = typer.Argument(..., help="Item id (integer) or full URL."),
    full: bool = typer.Option(False, "--full",
                              help="Also fetch the article URL and extract readable body via trafilatura."),
    refresh: bool = typer.Option(False, "--refresh",
                                 help="With --full, ignore the cached extraction and re-fetch."),
) -> None:
    paths: nb.Paths = ctx.obj
    item = nb.fetch_one(paths, identifier)
    if item is None:
        _print_json({"error": "not_found", "identifier": identifier})
        raise typer.Exit(code=1)

    if full:
        item["extracted"] = _resolve_extracted(paths, item, refresh=refresh)

    _print_json(item)


def _resolve_extracted(paths: nb.Paths, item: dict, *, refresh: bool) -> dict:
    from . import extract as ex

    if not refresh:
        cached = nb.get_cached_extract(paths, item["id"])
        if cached is not None:
            return {**cached, "source": "cache"}

    result = ex.extract_article(item["url"])
    nb.save_extract(
        paths,
        item_id=item["id"],
        url=item["url"],
        status=result.status,
        text=result.text,
        length=result.length,
    )
    cached = nb.get_cached_extract(paths, item["id"])
    assert cached is not None
    return {**cached, "source": "fresh"}


@app.command(help="List configured feeds (from feeds/urls).")
def feeds(ctx: typer.Context) -> None:
    paths: nb.Paths = ctx.obj
    nb.ensure_feeds_file(paths)
    items = nb.list_feeds(paths)
    _print_json({"count": len(items), "feeds": items})


@app.command(help="Print the resolved config/data paths as JSON.")
def paths(ctx: typer.Context) -> None:
    p: nb.Paths = ctx.obj
    _print_json(
        {
            "config_dir": str(p.config_dir),
            "data_dir": str(p.data_dir),
            "feeds_file": str(p.urls),
            "newsboat_conf": str(p.conf),
            "cache_db": str(p.cache),
            "error_log": str(p.error_log),
            "digests_dir": str(p.digests),
        }
    )


@app.command(help="Move legacy in-repo data (data/, feeds/, config/, digests/) to the user dirs.")
def migrate(
    ctx: typer.Context,
    src: Optional[Path] = typer.Option(
        None, "--from",
        help="Legacy repo root to migrate from (default: walk up from CWD looking for a my-news repo).",
    ),
) -> None:
    target: nb.Paths = ctx.obj
    src_root = src.resolve() if src else nb.find_project_root()
    if src_root is None:
        typer.echo("[my-news migrate] no source repo found (pass --from <repo-root>).", err=True)
        raise typer.Exit(code=1)

    legacy = nb.Paths.from_root(src_root)
    report: dict[str, str] = {}

    for source, dst in (
        (legacy.urls, target.urls),
        (legacy.conf, target.conf),
        (legacy.cache, target.cache),
        (legacy.error_log, target.error_log),
    ):
        if not source.exists():
            report[str(source)] = "skipped: source missing"
            continue
        if dst.exists():
            report[str(source)] = f"skipped: {dst} already exists"
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dst)
        report[str(source)] = f"copied -> {dst}"

    if legacy.digests.is_dir():
        target.digests.mkdir(parents=True, exist_ok=True)
        moved, skipped = 0, 0
        for entry in legacy.digests.iterdir():
            dst = target.digests / entry.name
            if dst.exists():
                skipped += 1
                continue
            if entry.is_dir():
                shutil.copytree(entry, dst)
            else:
                shutil.copy2(entry, dst)
            moved += 1
        report[str(legacy.digests)] = f"copied {moved} entries, skipped {skipped} existing -> {target.digests}"

    _print_json(
        {
            "src": str(src_root),
            "config_dir": str(target.config_dir),
            "data_dir": str(target.data_dir),
            "actions": report,
        }
    )


def main(argv: Optional[list[str]] = None) -> int:
    """Entry point for `my-news = "my_news.cli:main"`."""
    try:
        app(args=argv, standalone_mode=False)
    except typer.Exit as e:
        return int(e.exit_code or 0)
    except SystemExit as e:
        return int(e.code or 0)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
