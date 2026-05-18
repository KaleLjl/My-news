---
name: my-news
description: 拉取用户订阅的一手 RSS 源里的未读条目，整理成中文深度简报。用于"看看今天/最近有什么新东西"。触发：用户提到"简报"、"news digest"、"看看 RSS"、"my-news"、"今日新闻"、"有什么新的"、"刷一下源"等，或直接 /my-news。
---

# my-news — 一手 RSS 简报

用户在 `~/Workspace/my-news/` 维护了一份 RSS 源列表，希望由 agent 定期拉取并整理成深度简报。本 skill 负责：调 CLI 拉数据 → 判断是否有更新 → 整理成结构化中文简报 → 可选写到 digests/ 供推送使用。

## 工作流

### 1. 拉取数据

```bash
cd ~/Workspace/my-news && uv run my-news fetch
```

- 默认会先调 newsboat reload（网络刷新），再读 SQLite 缓存里所有 unread 条目，输出到 stdout 的 JSON，并把这些条目标记为已读。
- 如果用户只是想预览不想"消费"，加 `--no-mark`。
- 如果用户想看最近 N 时间内的，加 `--since 24h` / `--since 7d` 等。
- 如果用户想立刻看（不等 reload），加 `--no-reload`。

CLI 输出 JSON 结构：

```json
{
  "fetched_at": "ISO 时间戳",
  "count": <数字>,
  "feed_count": <数字>,
  "by_feed": {
    "<源标题>": [
      {"title": "...", "url": "...", "author": "...", "pub_date": "...",
       "content_text": "去 HTML 的正文，~4000 字符",
       "feed_url": "...", "tags": ["..."]}
    ]
  }
}
```

### 2. 空检查 — 这是关键

如果 `count == 0`：

```
📭 没有新内容（最近一次刷新：<fetched_at>）
```

**直接结束，不要调任何 LLM 能力做"假装总结"或编造内容**。这是为了：(a) 不浪费 token，(b) 让 Hermes 这种调度器能靠 stdout 是否包含"没有新内容"判断要不要推送。

### 3. 整理成简报

当 `count > 0` 时，按下面的结构输出中文 Markdown 简报：

```markdown
# 📰 my-news 简报 · <YYYY-MM-DD HH:MM>

共 **<count>** 条新条目，覆盖 **<feed_count>** 个源。

## 🎯 今日要点

跨源提炼 3-5 条最重要的更新，每条 1 句话讲清楚是什么 + 为什么值得注意。附原文链接。

- **<要点标题>**：<一句话本质>。([来源](URL))

## 📚 分主题

如果多条围绕同一话题（例如多个 AI 实验室同时发模型、多家公司在讨论同一技术），把它们合并讲，对比异同。每个主题 1-2 段。

如果没有明显的跨源主题，跳过本节。

## 📰 按源全量

每个源下，按 pub_date 倒序列出所有新条目，给 1-2 句中文摘要 + 原文链接。摘要要点出"做了什么/发现了什么/结论是什么"，不要复读标题。

### <源标题> (<n> 条)

- **<原标题翻译或保留>** · <pub_date 简化>  
  <中文摘要 1-2 句>  
  [原文](URL)

## 🔖 推荐精读

挑 2-3 条最值得点开看完的，每条说明"为什么推荐"。这帮用户决定时间投在哪。
```

### 4. 写入文件（推荐做）

简报写到聊天同时，也写一份到：

```
~/Workspace/my-news/digests/<YYYY-MM-DD-HHMM>.md
```

这个路径稳定可预测，方便用户的调度器（Hermes 之类）`cat` 后推送到手机。

## 写简报的风格要求

- **中文输出**，标题可保留原文（特别是技术名词、产品名）。
- **信息密度高**：每句话都要有信息量，不要"近期 X 公司发布了关于 Y 的内容"这种空话。
- **可扫读**：用 bullet、加粗、清晰的小节标题，让用户 30 秒能抓住重点。
- **不编造**：只依据 `content_text` 提供的内容总结。如果某条 content_text 太短（比如 HN 那种只有 metadata），就照实说"原文需点开看"，不要瞎编。
- **链接保留**：每条都带 `url` 字段的链接，让用户能跳过去看原文。
- **去噪**：HN frontpage 这种源经常有杂项（mapping/blog spam），可以在"按源全量"里照常列，但**别**把它们放进"今日要点"。要点必须是有真实信息量的。

## 错误处理

- 如果 `uv run my-news fetch` 自身失败（非 0 退出，stderr 有内容），先把错误告诉用户，**不要**继续编造简报。
- 如果 stderr 有内容但 stdout 也有有效 JSON（newsboat 部分源失败的情况），继续做简报，但在末尾加一行"⚠️ 部分源刷新有问题，详见 `data/last-error.log`"。
- 如果 JSON parse 失败，原样输出 stdout 头 20 行帮助用户排查。

## 用户可能的请求变体

- "看看今天的新闻" → 直接 `fetch`
- "看看最近 24 小时" → `fetch --since 24h`
- "预览一下，先别标已读" → `fetch --no-mark`
- "现在就看，别等网络" → `fetch --no-reload`
- "我都订了什么源" → `uv run my-news feeds`
- "新加一个源 https://..." → 提醒用户编辑 `feeds/urls`，附上 newsboat 格式说明（URL + 可选 "tag1" "tag2"）
