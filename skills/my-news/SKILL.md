---
name: my-news
description: 拉取用户订阅的一手 RSS 源里的内容，按需整理成中文简报、列出全量条目、或返回某条原文。触发：用户提到"简报"、"news digest"、"看看 RSS"、"my-news"、"今日新闻"、"有什么新的"、"刷一下源"、"列出文章"、"给我 X 的原文"、"总结 X 这一条"等，或斜杠/at 形式如 `/my-news`、`@my-news`。Agent 无关，Claude Code / Hermes / 其他 agent 都可用。
---

# my-news — 一手 RSS 简报

本 skill 是个壳，真正干活的是 PATH 上的 `my-news` CLI（基于 newsboat + trafilatura，状态走 XDG 用户目录）。**Agent 无关**：只要 CLI 在 PATH 上，Claude Code / Hermes / 其它能跑 shell 的 agent 都能用。根据用户意图分支为三种动作：**简报**（新内容深度整理）、**列表**（罗列已抓取的所有条目，不消耗 unread 状态）、**取单条**（按 id/URL 拿完整原文）；外加一个 **诊断**（`doctor`，查源是否还活着）。

## 0. 前置检查（每次会话首次触发时跑一次即可）

```bash
command -v my-news
```

- **有输出** → 直接进入后面的命令分支。
- **没输出** → CLI 没装。**先停下来征求用户同意**，然后用一行装上：

  ```bash
  uv tool install git+https://github.com/KaleLjl/my-news.git
  ```

  前置依赖（缺哪个补哪个）：
  - `uv`：`brew install uv`（macOS）或 `curl -LsSf https://astral.sh/uv/install.sh | sh`（其它）
  - `newsboat`：`brew install newsboat`（macOS / Linuxbrew）/ `sudo apt install newsboat`（Debian / Ubuntu ≤22.04）/ `sudo pacman -S newsboat`（Arch）
  - **Ubuntu 24.04+ 注意**：apt 源里没有 newsboat。详细方案（Linuxbrew 推荐 / snap + 环境变量 workaround / 源码编译）见 `references/install.md` §I.5。

  装完再走下一步，不需要重开 shell（`~/.local/bin` 已在 PATH 时 `my-news` 立即可用）。

**老仓库数据迁移**：如果用户曾用过老版本（仓库里的 `data/cache.db`、`feeds/urls` 等），且 `my-news paths` 显示的 `data_dir` 还是空的，问一下要不要把老数据搬过去：

```bash
my-news migrate --from <老仓库路径>
```

`migrate` 是幂等的，已存在的目标会跳过。

**关键原则**：检查失败时**不要硬跑命令然后让用户看一屏 traceback**。先报清楚问题，再问要不要让你帮装。

## 1. 三个 CLI 子命令

所有命令直接调 `my-news ...`（已在 PATH 上）。不需要 `cd` 到任何目录，状态走 XDG 用户目录。

### `fetch` — 新内容简报用

```bash
my-news fetch [--no-reload] [--no-mark] [--since 24h]
```

- 默认：newsboat reload → 输出所有 unread 条目 JSON → **标记已读**
- 用于"看看今天有什么新的" / 定时简报
- `content_text` 完整不截断（RSS 给多少就是多少）

### `list` — 罗列已抓取的条目（不消耗 unread）

```bash
my-news list [--no-reload] [--feed QUERY] [--limit N] [--since 24h] [--unread-only]
```

- 不过滤 unread，能看到所有还在缓存里的条目（包括已读历史）
- `--feed simon` 按源标题或 URL 子串过滤（不区分大小写）
- `--limit 50` 默认上限
- **不会**标记任何条目已读
- 用于"列出 simonw 最近 30 条" / "看看缓存里都有什么"

### `show` — 取单条完整原文

```bash
my-news show <id|url> [--full] [--refresh]
```

- 参数可以是数字 id（来自 `fetch`/`list` 的 `id` 字段），也可以是文章 URL
- 默认返回 RSS 自带内容：单条 JSON，`content_text` 完整 + 多带 `content_html` 原始 HTML（fetch/list 不带 html）
- `--full`：另外去抓**文章 URL** 用 trafilatura 抽正文（Markdown 格式），结果缓存在 `extracted_content` 表里，第二次秒回。返回结构里多一个 `extracted` 字段：
  ```json
  "extracted": {
    "status": "ok|fetch_failed|extract_failed|empty",
    "source": "cache|fresh",
    "fetched_at": "ISO",
    "length": <数字>,
    "text": "<Markdown 正文>"
  }
  ```
- `--refresh`：强制重抓覆盖缓存
- 找不到 id/url 时退出码 1 + `{"error": "not_found", ...}`
- 用于"把第 X 条的原文给我" / "把 https://... 这篇展开"

### `feeds` — 已配置的源

```bash
my-news feeds
```

### `paths` — 查路径（供 skill 自己用）

```bash
my-news paths
```

返回 JSON：`config_dir` / `data_dir` / `feeds_file` / `newsboat_conf` / `cache_db` / `digests_dir`。Skill 在写简报时**先调一次它拿 `digests_dir`**，避免硬编码路径。

## 2. 输出 JSON 形状

`fetch` 和 `list`：

```json
{
  "fetched_at": "ISO 时间戳",
  "count": <数字>,
  "feed_count": <数字>,
  "by_feed": {
    "<源标题>": [
      {"id": <数字>, "title": "...", "url": "...", "author": "...",
       "pub_date": "ISO", "unread": true|false,
       "content_text": "去 HTML 的正文（完整，不截断）",
       "feed_url": "...", "tags": ["..."]}
    ]
  }
}
```

`show` 单条额外带 `"content_html": "<原始 HTML>"`。`content_text` 在所有命令里都是完整不截断的。

## 3. 分支决策：用户想要什么？

| 用户意图 | 用哪个命令 |
|---|---|
| "看看今天的新闻" / "刷一下" / "/my-news" | `fetch` |
| "看看最近 24 小时" | `fetch --since 24h` |
| "预览一下，先别标已读" | `fetch --no-mark` |
| "列一下 cloudflare 的所有文章" / "罗列 simonw 最近 20 条" | `list --feed <name> --limit 20` |
| "看看缓存里都有什么" / "全部列出来" | `list --limit 100` |
| "把第 N 条 / 标题为 X 的原文给我" | 从上次 fetch/list 找到对应 `id` → `show <id>`；若 `content_text` 太短（RSS 只给了 metadata）→ 自动追加 `show <id> --full` 抓网页正文 |
| "https://xxx 这篇是什么" | `show <url> --full` |
| "总结一下 [某条]" | `show <id> --full` 拿完整 `extracted.text` → 用 LLM 总结 |
| "重新抓一下 X" | `show <id> --full --refresh`（绕过缓存）|
| "我都订了什么源" | `feeds` |
| "新加一个源" | 提醒编辑 `my-news paths` 返回的 `feeds_file`（默认 `~/.config/my-news/feeds/urls`，newsboat 格式：URL + 可选 `"tag1" "tag2"`） |

**关键点**：`fetch` 会"消耗" unread 状态。如果用户只是想浏览/查询/取原文，**优先用 `list` 和 `show`**，不要用 `fetch`。

### 首次大 backlog 处理（防爆上下文）

首次部署 / 长时间没刷 / 加了很多源时，`fetch` 可能一下子返回几百条，塞爆 LLM 窗口。**应当先侦察再决定**：

1. **低成本侦察**（不消耗 unread、内容截断）：

   ```bash
   my-news fetch --no-mark --summary-only --limit 5
   ```

   只看返回 JSON 的 `count` 字段。

2. **按 count 分级降级**：

   | count | 怎么走 |
   |---|---|
   | `<= 50` | 正常 `my-news fetch`，全量整理 |
   | `50 < count <= 200` | `my-news fetch --since 24h`，告诉用户"另有 N 条更老的，要不要追？" |
   | `> 200` | `my-news fetch --since 24h --limit 50 --summary-only`，明确告诉用户在分批；剩余下次会话再处理 |

3. **`--limit N` 的语义**：只输出最近 N 条 unread，**只对这 N 条 mark_read**，剩余 unread 保留供下次。所以分批安全，不会丢条目。

4. **`--summary-only` 的语义**：每条 `content_text` 截断到 2000 字符（可用 `MY_NEWS_SUMMARY_MAX_CHARS` 调），并在 item 上加 `"content_text_truncated": true` 标记。需要全文：`show <id> --full`（trafilatura 抓网页正文）。

## 4. 简报输出格式（仅 `fetch` 路径）

### 空检查

`count == 0` 时输出：

```
📭 没有新内容（最近一次刷新：<fetched_at>）
```

**直接结束，不调 LLM 生成内容**。这让外部调度器（cron / systemd / Hermes 等）能靠是否包含"没有新内容"判断要不要推送。

### 有内容时的简报结构

```markdown
# 📰 my-news 简报 · <YYYY-MM-DD HH:MM>

共 **<count>** 条新条目，覆盖 **<feed_count>** 个源。

## 🎯 今日要点

跨源提炼 3-5 条最重要的更新，每条 1 句话讲清楚是什么 + 为什么值得注意。

- **<要点标题>**：<一句话本质>。([来源](URL))

## 📚 分主题

如果多条围绕同一话题，合并讲、对比异同。没有跨源主题就跳过。

## 📰 按源全量

每个源下按 pub_date 倒序列出所有新条目，给 1-2 句中文摘要 + 原文链接。

### <源标题> (<n> 条)

- **<标题>** · <pub_date 简化>  
  <中文摘要 1-2 句>  
  [原文](URL) · `id: <id>`

如果某条 `content_text_truncated: true`（用了 `--summary-only`），摘要只写一句话 + 链接，注明"全文需 `show <id> --full`"，不要假装看完了全文。

## 🔖 推荐精读

挑 2-3 条最值得点开看完的，说明"为什么推荐"。
```

**带上 `id`**：让用户后续可以说"给我 id 1042 的原文"，skill 直接调 `show 1042`。

### 写到文件

简报输出到聊天的同时，也写一份到 `my-news paths` 返回的 `digests_dir` 下：

```
<digests_dir>/<YYYY-MM-DD-HHMM>.md
```

（默认是 `~/.local/share/my-news/digests/<YYYY-MM-DD-HHMM>.md`）

`digests_dir` 不存在就 `mkdir -p` 一下。路径稳定可预测，方便调度器 `cat` 后推送。

## 5. 列表输出格式（`list` 路径）

```markdown
# 📋 my-news 列表 · 共 <count> 条
<过滤条件回显：feed=xxx limit=N since=24h>

## <源标题> (<n> 条)

- `[id: 1042]` **<标题>** · <pub_date> · <unread ? "🆕" : "✓">  
  <如果 content_text 够长，给一句话摘要；不够长就略>  
  [原文](URL)
```

列表模式**不**写 digests 文件、**不**生成深度简报、**不**做跨源主题分析 — 这是"目录索引"，不是简报。

## 6. 单条原文输出格式（`show` 路径）

```markdown
# 📄 <标题>

- **源**：<feed_title>
- **作者**：<author>
- **发布**：<pub_date>
- **URL**：<url>
- **状态**：<unread ? "未读" : "已读">
- **标签**：<tags>

---

<content_text 全文，原样保留分段>
```

如果 `content_text` 极短（< 200 字符，像 HN 那种只有 metadata 的源）：**立即追加 `show <id> --full`** 调 trafilatura 抓网页正文，然后用 `extracted.text` 而不是 `content_text` 渲染。如果 `extracted.status != "ok"`（fetch_failed / extract_failed / empty），再告诉用户原文抓不到、给原 URL 让他自己点。

## 7. 简报风格要求（仅 fetch 路径）

- **中文输出**，标题可保留原文（特别是技术名词、产品名）
- **信息密度高**：每句话都要有信息量，避免"近期 X 公司发布了关于 Y 的内容"这种空话
- **可扫读**：bullet、加粗、清晰小节，30 秒能抓住重点
- **不编造**：只依据 `content_text`。content_text 太短就照实说"原文需点开看"
- **链接保留**：每条都带 `url` 链接
- **去噪**：HN 这种源经常有杂项，可在"按源全量"列，但**别**进"今日要点"

## 8. 错误处理

- CLI 自身失败（非 0 退出）：先告诉用户错误，**不要**编造内容
- `command not found: my-news` → 回到 §0 重新走前置检查
- `command not found: newsboat`（CLI 跑得动但 `fetch` 时报错）→ 提示用户装 newsboat
- `show` 返回 `not_found`：告诉用户没找到，建议先 `list` 看 id
- stderr 有内容但 stdout 有有效 JSON：继续做简报/列表，末尾加"⚠️ 部分源刷新有问题，详见 `my-news paths` 返回的 `error_log`"
- JSON parse 失败：输出 stdout 头 20 行帮助排查；如果 payload 巨大（单条 content 上万字）可重试 `--summary-only`

## 9. 环境变量覆盖（可选）

`my-news` 默认 config 在 `~/.config/my-news/`，data 在 `~/.local/share/my-news/`。如果用户想改：

- `MY_NEWS_CONFIG=/some/path` 改 config 根（feeds/urls + newsboat.conf 都在里头）
- `MY_NEWS_DATA=/some/path` 改 data 根（cache.db + digests/ 都在里头）
- `MY_NEWS_SUMMARY_MAX_CHARS=N` 改 `--summary-only` 的截断阈值（默认 2000）

三个变量都是**可选**的；不设就用默认。设置时请用户自己写进 shell rc，skill 不应该替用户改 rc。

## 10. 源健康检查（用户问"哪个源没数据"时）

用户类似抱怨——"为什么 X 一直没东西"、"机器之心好像挂了"、"加了新源但 fetch 不到"——走 `doctor`：

```bash
my-news doctor              # 人类可读表格
my-news doctor --json       # 机器可读 JSON
my-news doctor --timeout 20 # 慢源放宽超时
```

输出每条源的：HTTP 状态、Content-Type、能不能 parse 成 RSS/Atom、item 数。状态分四种：

| 状态 | 含义 | 给用户什么建议 |
|---|---|---|
| `ok` | 拉得到 + parse 成功 + 有 item | 没事 |
| `feed_unreachable` | HTTP 4xx/5xx 或网络错误 | 检查 URL 是不是改了；连续失败考虑删行 |
| `not_a_feed` | HTTP 200 但响应不是 RSS/Atom（多半是 HTML 落地页） | URL 错了，去站点重找 RSS 入口 |
| `duplicate` | 与前面某行 URL 完全一致（仅规范化大小写 / 末尾斜杠） | 删一行 |

Skill 拿到 `--json` 输出后，把 `reports` 里 `status != "ok"` 的整理给用户，建议改 `feeds_file` 路径（来自 `my-news paths`）。

**注意**：`doctor` 检测不到"同站不同 URL 但内容雷同"的伪重复（典型陷阱：`hnrss.org/frontpage` 和 `news.ycombinator.com/rss` 都会过 `doctor`，但后者只 metadata）。这种已知组合在 `references/install.md` §III "已知陷阱" 里列了。
