"""Command-line entry point for my-news."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from . import newsboat as nb


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="my-news",
        description="Fetch unread RSS items via newsboat and emit JSON.",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="Override project root (default: auto-detect from pyproject.toml).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    fetch = sub.add_parser("fetch", help="Reload feeds, output unread items as JSON, mark read.")
    fetch.add_argument("--no-reload", action="store_true", help="Skip newsboat reload; read DB only.")
    fetch.add_argument("--no-mark", action="store_true", help="Do not mark items as read.")
    fetch.add_argument(
        "--since",
        metavar="DURATION",
        help="Only items with pubDate within DURATION (e.g. 24h, 30m, 7d).",
    )

    listcmd = sub.add_parser(
        "list",
        help="List items from the cache without the unread filter (does not mark anything).",
    )
    listcmd.add_argument("--feed", metavar="QUERY", help="Filter by feed title or URL (case-insensitive substring).")
    listcmd.add_argument("--limit", type=int, default=50, help="Max items to return (default 50).")
    listcmd.add_argument("--since", metavar="DURATION", help="Only items within DURATION (e.g. 24h, 7d).")
    listcmd.add_argument("--unread-only", action="store_true", help="Restrict to unread items.")
    listcmd.add_argument("--no-reload", action="store_true", help="Skip newsboat reload; read DB only.")

    show = sub.add_parser(
        "show",
        help="Show one item's full content (no truncation). Argument is either the item id or its URL.",
    )
    show.add_argument("identifier", help="Item id (integer) or full URL.")
    show.add_argument(
        "--full",
        action="store_true",
        help="Also fetch the article URL and extract readable body via trafilatura (cached after first run).",
    )
    show.add_argument(
        "--refresh",
        action="store_true",
        help="With --full, ignore the cached extraction and re-fetch.",
    )

    sub.add_parser("feeds", help="List configured feeds (from feeds/urls).")
    return parser


def _cmd_fetch(args: argparse.Namespace, paths: nb.Paths) -> int:
    since_seconds = nb.parse_since(args.since) if args.since else None

    if not args.no_reload:
        nb.reload_feeds(paths)

    items = nb.fetch_unread(paths, since_seconds=since_seconds)
    by_feed = nb.group_by_feed(items)

    output = {
        "fetched_at": datetime.now(tz=timezone.utc).astimezone().isoformat(),
        "count": len(items),
        "feed_count": len(by_feed),
        "by_feed": by_feed,
    }
    json.dump(output, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    sys.stdout.flush()

    if items and not args.no_mark:
        nb.mark_read(paths, [item["id"] for item in items])

    return 0


def _cmd_list(args: argparse.Namespace, paths: nb.Paths) -> int:
    since_seconds = nb.parse_since(args.since) if args.since else None

    if not args.no_reload:
        nb.reload_feeds(paths)

    items = nb.fetch_items(
        paths,
        unread_only=args.unread_only,
        since_seconds=since_seconds,
        feed_filter=args.feed,
        limit=args.limit,
    )
    by_feed = nb.group_by_feed(items)
    json.dump(
        {
            "fetched_at": datetime.now(tz=timezone.utc).astimezone().isoformat(),
            "count": len(items),
            "feed_count": len(by_feed),
            "filter": {
                "feed": args.feed,
                "since": args.since,
                "unread_only": args.unread_only,
                "limit": args.limit,
            },
            "by_feed": by_feed,
        },
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


def _cmd_show(args: argparse.Namespace, paths: nb.Paths) -> int:
    item = nb.fetch_one(paths, args.identifier)
    if item is None:
        json.dump(
            {"error": "not_found", "identifier": args.identifier},
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        sys.stdout.write("\n")
        return 1

    if args.full:
        item["extracted"] = _resolve_extracted(paths, item, refresh=args.refresh)

    json.dump(item, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


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


def _cmd_feeds(_args: argparse.Namespace, paths: nb.Paths) -> int:
    feeds = nb.list_feeds(paths)
    json.dump(
        {"count": len(feeds), "feeds": feeds},
        sys.stdout,
        ensure_ascii=False,
        indent=2,
    )
    sys.stdout.write("\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    root = args.root.resolve() if args.root else nb.find_project_root()
    paths = nb.Paths(root=root)

    if args.command == "fetch":
        return _cmd_fetch(args, paths)
    if args.command == "list":
        return _cmd_list(args, paths)
    if args.command == "show":
        return _cmd_show(args, paths)
    if args.command == "feeds":
        return _cmd_feeds(args, paths)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
