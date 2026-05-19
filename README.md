# my-news

只看一手资料的个人 RSS 工作流。CLI 用 newsboat 抓源、以 JSON 输出（含完整正文，不截断）；Claude Code skill 负责把 JSON 整理成中文简报或单条原文展示；调度器（cron / Hermes / Claude Code 计划任务等）负责按需推送。

设计原则：**CLI 是纯数据层**（不调 LLM、不格式化、不做内容判断），**skill 才做 LLM 整理**。这样 CLI 单独可用、可被任何 LLM 客户端复用，skill 也可以独立换。

## 架构

```
feeds/urls  ──┐
              ├──> newsboat reload ──> data/cache.db ──> CLI 查询 ──> JSON
config/      ─┘                              │
                                             ├──> 标记已读 (fetch)
                                             ├──> 只读不动 (list)
                                             └──> 单条 + 可选抓网页 (show --full)
                                                            │
                                                            ▼
                                          ~/.claude/skills/my-news (Claude Code)
                                                            │
                                                            ▼
                                           简报 / 列表 / 原文 (chat + digests/*.md)
```

## 安装

### 一键脚本（推荐）

克隆仓库后跑：

```bash
bash skills/my-news/scripts/setup.sh
```

会依次：装 newsboat / uv → `uv sync` → 把 `skills/my-news/` symlink 到 `~/.claude/skills/my-news`。重跑无害。

### 手动安装

```bash
# 1. 系统依赖
brew install newsboat
brew install uv          # 或者 pipx install uv

# 2. Python 依赖
uv sync

# 3. 让 Claude Code 看到 skill
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/my-news" ~/.claude/skills/my-news

# 4. （可选）项目不在 ~/Workspace/my-news 时，固定路径
echo 'export MY_NEWS_HOME="'"$(pwd)"'"' >> ~/.zshrc
```

详细步骤、Linux 安装、排错速查见 [`skills/my-news/references/install.md`](skills/my-news/references/install.md)。

## CLI

四个子命令，所有输出都是 UTF-8 JSON（除 `feeds` 是文本）。

### `fetch` — 拉新内容（会标记已读）

```bash
uv run my-news fetch
uv run my-news fetch --no-reload     # 不联网刷新，只读缓存
uv run my-news fetch --no-mark       # 预览，不消耗未读状态
uv run my-news fetch --since 24h     # 只看最近 24 小时发布的
```

适合"看看今天有什么新的"或定时简报。

### `list` — 翻看缓存（不标记任何东西）

```bash
uv run my-news list                                   # 缓存里最近 50 条
uv run my-news list --feed simon --limit 20           # 源标题或 URL 子串过滤
uv run my-news list --since 48h                       # 最近 48 小时
uv run my-news list --unread-only                     # 只看未读
```

适合"列出 simonw 最近 20 条"、"看看缓存里都有什么"。和 `fetch` 的关键区别：**绝不动 unread 状态**。

### `show` — 取单条完整内容

```bash
uv run my-news show 1042                              # 按 id（来自 fetch/list 的 id 字段）
uv run my-news show https://example.com/post          # 按 URL
uv run my-news show 1042 --full                       # 额外用 trafilatura 抓网页正文
uv run my-news show 1042 --full --refresh             # 强制重抓，绕过缓存
```

默认返回 RSS 自带内容（`content_text` + `content_html`）。加 `--full` 会去抓**文章 URL** 用 trafilatura 抽 Markdown 正文，结果存进 `extracted_content` 表第二次秒回。

适合"把这条原文展开"、"HN 那条只有 metadata，把正文抓回来"。

### `feeds` — 列已配置的源

```bash
uv run my-news feeds
```

## 在 Claude Code 里用

仓库里带了 `.claude/skills/my-news/`，会被 Claude Code 自动识别。直接说：

- "看看今天的新闻" / "/my-news" → `fetch` 路径，出深度简报，落地到 `digests/<YYYY-MM-DD-HHMM>.md`
- "列出 cloudflare 的最近文章" → `list` 路径，目录式输出，不写文件
- "把 id 1042 的原文给我" / "总结一下那条" → `show` 路径，必要时自动加 `--full`

skill 自己会判断走哪条分支，你不用 care 命令。

## 输出格式

`fetch` 和 `list` 的 JSON 结构：

```json
{
  "fetched_at": "2026-05-19T12:15:23+08:00",
  "count": 13,
  "feed_count": 4,
  "by_feed": {
    "<源标题>": [
      {
        "id": 1042,
        "title": "...",
        "url": "...",
        "author": "...",
        "pub_date": "ISO",
        "unread": true,
        "content_text": "去 HTML 的完整正文，不截断",
        "feed_url": "...",
        "tags": ["..."]
      }
    ]
  }
}
```

`show` 返回**单条**对象，额外带 `content_html`（原始 HTML），加 `--full` 时再多一个 `extracted` 字段：

```json
"extracted": {
  "status": "ok | fetch_failed | extract_failed | empty",
  "source": "cache | fresh",
  "fetched_at": "ISO",
  "length": 12345,
  "text": "<Markdown 正文>"
}
```

`content_text` 在所有命令里都是 RSS 给多少就出多少，**不截断**。

## 加 / 改源

编辑 `feeds/urls`，newsboat 格式：

```
https://example.com/feed.xml             "tag1" "tag2"
https://another.example.com/atom.xml     "ai"
```

下一次 `fetch` / `list`（如果没 `--no-reload`）会自动 reload 拉新数据。

## 文件结构

| 路径 | 作用 |
|---|---|
| `feeds/urls` | RSS 源列表（newsboat 格式：URL + 可选 tag） |
| `config/newsboat.conf` | newsboat 行为配置（缓存路径、超时等） |
| `src/my_news/` | CLI 实现（仅依赖 stdlib + trafilatura） |
| `.claude/skills/my-news/` | Claude Code skill，定义简报 / 列表 / 原文三种输出格式 |
| `data/cache.db` | newsboat SQLite 缓存（自动生成、不进 git） |
| `data/extracted.db` | trafilatura 抽取缓存（自动生成、不进 git） |
| `data/last-error.log` | newsboat 刷新错误日志（per-feed 失败查这里） |
| `digests/` | skill 写出的简报 markdown |

## 调度推送

CLI 是纯 stdout JSON，方便接任何调度器。两种常见用法：

```bash
# 直接拿 JSON
0 8 * * *  cd ~/Workspace/my-news && uv run my-news fetch > /tmp/news-$(date +\%F).json

# 触发 Claude Code skill 生成简报到 digests/，再推到 IM / 邮件
0 8 * * *  claude code --skill my-news "今天的简报"
```

`fetch` 在 `count == 0` 时 skill 会输出固定字符串 `📭 没有新内容（最近一次刷新：...）`，调度器可以靠这个判断要不要推送。

## 不做的事

- **不存档全文** —— 抓回来的内容只走 newsboat 默认保留策略（cache.db），过期就过期；trafilatura 抽出的正文按 URL 缓存，但同样不是"我的资料库"。需要长期存档请自己往别处导。
- **不去重 / 不打分 / 不个性化推荐** —— 排序就是 pub_date 倒序，挑选交给 skill 或你自己。
- **不调 LLM** —— CLI 永远不动网络以外的 AI 服务，token 花在哪由 skill 这层决定。

## 许可

MIT
