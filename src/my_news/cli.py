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
    if args.command == "feeds":
        return _cmd_feeds(args, paths)
    raise SystemExit(f"Unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
