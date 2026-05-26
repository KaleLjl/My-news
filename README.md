# my-news

只看一手资料的个人 RSS 工作流，**给 agent 用，不是给人用**。

- **CLI**（`my-news`）：用 newsboat 拉源，输出 JSON。不调 LLM、不渲染。纯数据层。
- **Skill**（`skills/my-news/`）：Claude Code / Hermes / 任意能跑 shell 的 agent 都能挂载，把 CLI 输出整理成中文简报。

## 安装

```bash
npx skills add https://github.com/KaleLjl/my-news.git
```

就这一条。第一次在 agent 里触发 skill 时，它会自检 `my-news` CLI 是否就绪，缺啥（`uv` / `newsboat` / CLI 本身）会提示你装。

## 用法

装好后直接对 agent 说人话：

| 你想干啥 | 说法 |
|---|---|
| 看今天有什么新的 | "看看今天的新闻" / "刷一下" / `/my-news` |
| 订阅一个源 | "帮我订阅 https://simonwillison.net/atom/everything/" |
| 取消订阅 | "把 hnrss 这个源删掉" |
| 罗列某个源 | "列一下 simonw 最近 20 条" |
| 取单条原文 | "把 id 1042 的原文给我" / "https://... 这篇讲了啥" |
| 哪个源挂了 | "机器之心好像没数据" → skill 自动跑 `doctor` |

简报会写一份到 `~/.local/share/my-news/digests/<时间戳>.md`，方便回看或被脚本推送。

## 直接用 CLI

不走 agent 也行：

```bash
my-news add https://simonwillison.net/atom/everything/ --tag blog
my-news fetch                  # 输出未读 JSON 并标已读
my-news list --feed simon      # 翻缓存，不动 unread
my-news show 1042 --full       # 取单条全文（trafilatura 抓网页正文）
my-news doctor                 # 源健康检查
my-news --help                 # 看所有命令
```

所有命令输出 JSON，stdout 是数据、stderr 是状态，符合 agent-native CLI 惯例。

## 文件位置

| 路径 | 作用 |
|---|---|
| `~/.config/my-news/feeds/urls` | 订阅列表（newsboat 格式） |
| `~/.local/share/my-news/cache.db` | newsboat + trafilatura 缓存 |
| `~/.local/share/my-news/digests/` | Skill 写的简报 markdown |

环境变量 `MY_NEWS_CONFIG` / `MY_NEWS_DATA` 可覆盖默认位置。

## 设计原则

- **CLI 不调 LLM**：花 token 的事在 Skill 这一层
- **JSON-first 输出**：方便 agent 消费，人也能看
- **状态走 XDG 用户目录**：和仓库解耦，agent-agnostic

## 开发

```bash
git clone https://github.com/KaleLjl/my-news.git
cd my-news && uv sync
uv run my-news --help
```

详细安装/排错（Ubuntu 24.04 snap workaround、Hermes 部署等）见 [install.md](skills/my-news/references/install.md)。

## License

MIT
