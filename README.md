# my-news

只看一手资料的 RSS 简报工作流。CLI 拉取 newsboat 的未读条目并以 JSON 输出，Claude Code skill 负责整理成中文深度简报，调度器（cron / Hermes 等）负责推送。

## 架构

```
feeds/urls  ──┐
              ├──> newsboat reload ──> data/cache.db ──> CLI 查询 + 标记已读 ──> JSON
config/      ─┘                                            │
                                                           ▼
                                              ~/.claude/skills/my-news (Claude)
                                                           │
                                                           ▼
                                              简报 (chat + digests/*.md)
```

设计原则：CLI 是纯数据层（不调 LLM），skill 才做 LLM 整理。

## 安装

```bash
brew install newsboat uv
uv sync
```

## 用法

```bash
# 编辑你的源
$EDITOR feeds/urls

# 拉取并输出未读条目（标记已读）
uv run my-news fetch

# 不刷新网络，只读缓存
uv run my-news fetch --no-reload

# 预览模式（不消耗未读状态）
uv run my-news fetch --no-mark

# 限定最近 24 小时
uv run my-news fetch --since 24h

# 列出已配置的源
uv run my-news feeds
```

或在 Claude Code 里用 skill：直接说"看看今天的新闻"或"/my-news"。

## 文件

- `feeds/urls` — RSS 源列表（newsboat 格式：URL + 可选 "tag" "tag"）
- `config/newsboat.conf` — newsboat 行为配置
- `src/my_news/` — CLI 实现（stdlib only）
- `data/cache.db` — newsboat SQLite 缓存（自动生成）
- `data/last-error.log` — newsboat 刷新日志（per-feed 错误在这里）
- `digests/` — skill 写出的简报 markdown
