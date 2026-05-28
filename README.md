# my-news

A personal RSS workflow for first-hand sources only — **built for agents, not humans**.

- **CLI** (`my-news`): pulls feeds via newsboat and emits JSON. No LLM calls, no rendering. Pure data layer.
- **Skill** (`skills/my-news/`): mountable in Claude Code / Hermes / any agent that can run a shell, turns the CLI output into a readable digest.

## Install

```bash
npx skills add https://github.com/KaleLjl/my-news.git
```

That's it. The first time you trigger the skill in an agent, it self-checks whether the `my-news` CLI is ready and prompts you to install anything missing (`uv` / `newsboat` / the CLI itself).

## Usage

Once installed, just talk to your agent in plain language:

| What you want | What to say |
|---|---|
| See what's new today | "show me today's news" / "give the feeds a refresh" / `/my-news` |
| Subscribe to a feed | "subscribe me to https://simonwillison.net/atom/everything/" |
| Unsubscribe | "remove the hnrss feed" |
| List a single feed | "list simonw's latest 20 items" |
| Get the full article | "give me the full text of id 1042" / "what does https://... say" |
| Which feed is broken | "looks like there's no data from machine-learning blog" → skill runs `doctor` automatically |

The digest is written to `~/.local/share/my-news/digests/<timestamp>.md` for later review or for scripts to push elsewhere.

## Use the CLI directly

You don't have to go through an agent:

```bash
my-news add https://simonwillison.net/atom/everything/ --tag blog
my-news fetch                  # emit unread items as JSON and mark them read
my-news list --feed simon      # read the cache without touching unread state
my-news show 1042 --full       # fetch a single item's full text (trafilatura extracts the article body)
my-news doctor                 # feed health check
my-news --help                 # see all commands
```

Every command emits JSON — stdout is data, stderr is status — following the agent-native CLI convention.

## File locations

| Path | Purpose |
|---|---|
| `~/.config/my-news/feeds/urls` | Subscription list (newsboat format) |
| `~/.local/share/my-news/cache.db` | newsboat + trafilatura cache |
| `~/.local/share/my-news/digests/` | Digest markdown written by the skill |

The `MY_NEWS_CONFIG` / `MY_NEWS_DATA` environment variables override the default locations.

## Design principles

- **The CLI never calls an LLM**: anything that spends tokens lives in the skill layer
- **JSON-first output**: easy for agents to consume, still readable by humans
- **State lives in XDG user directories**: decoupled from the repo, agent-agnostic

## Development

```bash
git clone https://github.com/KaleLjl/my-news.git
cd my-news && uv sync
uv run my-news --help
```

For detailed install/troubleshooting notes (Ubuntu 24.04 snap workaround, Hermes deployment, etc.) see [install.md](skills/my-news/references/install.md).

## License

MIT
