# my-news

只看一手资料的个人 RSS 工作流。

- **CLI**（`my-news`）：用 newsboat 拉源，输出 JSON 给任何 LLM / 脚本用。不调 LLM，不格式化，纯数据层。
- **Skill**（`skills/my-news/`）：给 agent（Claude Code / Hermes / 其他）用的壳，把 CLI 的 JSON 整理成中文简报 / 列表 / 单条原文。

两个都装上，在你的 agent 里说"看看今天的新闻"就行。

---

## 安装（macOS / Linux 通用）

```bash
# 1. 系统依赖
brew install newsboat uv          # macOS / Linuxbrew
# Debian/Ubuntu ≤22.04: sudo apt install newsboat && curl -LsSf https://astral.sh/uv/install.sh | sh
# Ubuntu 24.04+: apt 没有 newsboat，推荐 Linuxbrew；详见 install.md §I.5

# 2. CLI
uv tool install git+https://github.com/KaleLjl/my-news.git

# 3. Skill（按你用的 agent 拷到对应目录）
git clone https://github.com/KaleLjl/my-news.git /tmp/my-news
mkdir -p ~/.claude/skills && cp -r /tmp/my-news/skills/my-news ~/.claude/skills/my-news   # Claude Code
# mkdir -p ~/.hermes/skills && cp -r /tmp/my-news/skills/my-news ~/.hermes/skills/my-news   # Hermes
```

验证：

```bash
my-news --help        # CLI 在 PATH 上
my-news paths         # 看 config / data / digests 目录
my-news doctor        # 跑一遍源健康检查
```

如果 `my-news` 找不到，跑一次 `uv tool update-shell` 重开终端。

详细安装/排错（含 Ubuntu 24.04 snap workaround、Hermes 部署）见 [`skills/my-news/references/install.md`](skills/my-news/references/install.md)。

---

## 加 RSS 源

第一次跑 `my-news fetch`（或 `feeds`）会自动在 `~/.config/my-news/feeds/urls` 生成空模板。编辑它，newsboat 格式，一行一个：

```
https://simonwillison.net/atom/everything/    "ai" "blog"
https://hnrss.org/newest                       "hn"
https://blog.cloudflare.com/rss/               "infra"
```

下次 `fetch` / `list` 会自动 reload 拉新数据。

---

## 在 agent 里用 Skill（推荐）

Skill 装好后（Claude Code / Hermes / 其他），直接说人话就行：

| 你想干啥 | 说法 |
|---|---|
| 看今天有什么新的 | "看看今天的新闻" / "刷一下源" / `/my-news`（Claude Code）/ `@my-news`（Hermes） |
| 罗列某个源的最近文章 | "列一下 simonw 最近 20 条" |
| 把某条原文给我 | "把 id 1042 的原文给我" / "总结一下那条" |
| 把某个 URL 展开 | "https://xxx 这篇讲了什么" |
| 哪个源挂了 | "机器之心好像没数据" → skill 自动跑 `my-news doctor` |

Skill 自动判断走 `fetch` / `list` / `show` / `doctor`，简报会写一份到 `~/.local/share/my-news/digests/<时间戳>.md`，方便回看或被脚本推送。

首次部署遇到 backlog 几百条时，skill 会先用 `fetch --no-mark --summary-only --limit 5` 侦察 `count`，按量分级处理（不会塞爆上下文）。

---

## 直接用 CLI（不走 agent 也行）

六个子命令，输出都是 UTF-8 JSON（`feeds` 和 `doctor` 默认是文本，加 `--json` 走 JSON）。

### `fetch` — 拉新内容，标记已读

```bash
my-news fetch                                      # 默认：reload + 输出所有 unread + 标已读
my-news fetch --no-reload                          # 只读缓存不联网
my-news fetch --no-mark                            # 预览，不消耗 unread 状态
my-news fetch --since 24h                          # 只看最近 24h 发布的
my-news fetch --limit 50                           # 只取最近 50 条 unread；只对这 50 条 mark_read
my-news fetch --summary-only                       # content_text 截断到 2000 字符（防爆上下文）
```

### `list` — 翻缓存，绝不动 unread

```bash
my-news list                                       # 缓存里最近 50 条
my-news list --feed simon --limit 20               # 按源标题/URL 子串过滤
my-news list --since 48h --unread-only
my-news list --summary-only                        # 同 fetch 的截断
```

### `doctor` — 源健康检查

```bash
my-news doctor                  # 表格输出，对每个源实拉 HTTP + 检查 RSS/Atom 形状 + 标记重复 URL
my-news doctor --json           # 机器可读
my-news doctor --timeout 20     # 慢源放宽超时
```

退出码：全 ok 返 0；有 `feed_unreachable` / `not_a_feed` 返 1；只有 `duplicate` 返 0（警告而非错误）。

### `show` — 取单条完整原文

```bash
my-news show 1042                  # 按 id（来自 fetch/list 输出）
my-news show https://example.com/post
my-news show 1042 --full           # 额外用 trafilatura 抓网页正文（Markdown）
my-news show 1042 --full --refresh # 强制重抓
```

`--full` 抓的正文会缓存，第二次秒回。

### `feeds` — 列已配置的源

### `paths` — 看 CLI 解析出的目录（JSON）

### `migrate` — 从老仓库布局搬数据

```bash
my-news migrate --from /path/to/old/my-news-repo
```

把老版本仓库里的 `data/cache.db`、`feeds/urls`、`config/newsboat.conf`、`digests/` 搬到 `~/.config/my-news/` 和 `~/.local/share/my-news/`。幂等，目标已存在则跳过。

---

## 文件去哪了

| 路径 | 作用 |
|---|---|
| `~/.config/my-news/feeds/urls` | 你的 RSS 源列表 |
| `~/.config/my-news/config/newsboat.conf` | newsboat 配置 |
| `~/.local/share/my-news/cache.db` | newsboat + trafilatura 缓存 |
| `~/.local/share/my-news/digests/` | Skill 写的简报 markdown |
| `~/.local/share/my-news/last-error.log` | newsboat 刷新错误 |

想换地方：设 `MY_NEWS_CONFIG` / `MY_NEWS_DATA` 环境变量（snap newsboat 用户必看 [install.md §I.5](skills/my-news/references/install.md)）。`--summary-only` 截断阈值由 `MY_NEWS_SUMMARY_MAX_CHARS` 控制（默认 2000）。

---

## 输出 JSON 结构

`fetch` 和 `list`：

```json
{
  "fetched_at": "2026-05-25T12:15:23+08:00",
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

`show` 返回单条，额外带 `content_html`；加 `--full` 再多个 `extracted` 字段。

---

## 调度推送

CLI 是纯 stdout JSON，接任何调度器都行：

```bash
# 通用：直接落 JSON，谁需要就 cat
0 8 * * *  my-news fetch > /tmp/news-$(date +\%F).json

# Claude Code：触发 skill 生成简报到 digests/
0 8 * * *  claude code --skill my-news "今天的简报"

# Hermes（以 Hermes CLI 实际语法为准）
# 0 8 * * *  hermes run my-news "今天的简报"
```

`fetch` 没新内容时 Skill 会输出固定字符串 `📭 没有新内容（最近一次刷新：...）`，方便调度器判断要不要推。

---

## 不做的事

- **不存档全文**：缓存按 newsboat 的默认策略保留，过期就过期。需要长期归档自己搬走。
- **不去重 / 不打分 / 不推荐**：排序就是 pub_date 倒序，挑选交给 Skill 或你。
- **CLI 不调 LLM**：花 token 的事在 Skill 这一层决定。

---

## 贡献者

```bash
git clone https://github.com/KaleLjl/my-news.git
cd my-news
uv sync
uv run my-news --help

# 改完 skill 后（按你用的 agent 挑一个）
cp -r skills/my-news ~/.claude/skills/my-news    # Claude Code
# cp -r skills/my-news ~/.hermes/skills/my-news    # Hermes
```

## 许可

MIT
