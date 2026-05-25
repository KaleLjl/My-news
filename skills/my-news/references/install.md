# my-news skill — 安装手册

这个 skill 是个壳，真正干活的是 [`my-news` CLI](https://github.com/KaleLjl/my-news)（基于 newsboat + trafilatura，状态走 XDG 用户目录，可直接 `uv tool install`）。**安装 skill 的本质**是装好 CLI；skill 本体只是一个目录，拷到 agent 能识别的位置即可。

skill **agent-agnostic**——Claude Code / Hermes / 其它能跑 shell 的 agent 都能用，只是各自识别 skill 的目录不同（见 §V）。

---

## 一、装系统依赖（newsboat + uv）

```bash
# macOS
brew install newsboat uv

# Linux (Debian / Ubuntu ≤22.04)
sudo apt install newsboat
curl -LsSf https://astral.sh/uv/install.sh | sh

# Linux (Arch)
sudo pacman -S newsboat
sudo pacman -S uv   # 或者用 astral 的官方安装脚本

# Ubuntu 24.04+ → 见 §I.5
```

验证：

```bash
newsboat --version
uv --version
```

### §I.5 Ubuntu 24.04+：apt 里没有 newsboat 怎么办

Ubuntu 24.04（Noble）开始官方 apt 仓库**不再带 newsboat**。三种选择，按推荐顺序：

#### 1.（推荐）装 Linuxbrew，然后 `brew install newsboat`

最一致——和 macOS 走同一套命令，PATH / 路径行为相同。

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
# 按提示把 brew shellenv 加进 ~/.profile / ~/.bashrc

brew install newsboat
```

newsboat 装在 `/home/linuxbrew/.linuxbrew/bin/newsboat`，对 `~/.config/my-news/` 等隐藏目录没有任何访问限制。

#### 2.（次选）snap：注意沙箱权限

```bash
sudo snap install newsboat
```

snap 默认走 **strict confinement**，通过 `home` interface 访问用户主目录——但 `home` interface **看不到 dotfile 目录**（`~/.config/`、`~/.local/share/` 这种以 `.` 开头的）。直接跑 `my-news fetch` 时 newsboat 会报权限错误，读不到 `~/.config/my-news/feeds/urls`、写不了 `~/.local/share/my-news/cache.db`。

**workaround**：通过环境变量把数据搬到非 dotfile 目录：

```bash
# 写进 ~/.bashrc 或 ~/.zshrc
export MY_NEWS_CONFIG="$HOME/my-news/config"
export MY_NEWS_DATA="$HOME/my-news/data"
```

确认生效：

```bash
my-news paths     # 应当显示 ~/my-news/config 和 ~/my-news/data
```

如果之前已经在默认 XDG 路径下跑过（snap 拒绝写时也可能落了空目录），跑 `my-news migrate --from <旧 my-news 仓库>` 或者手动 `cp -r ~/.config/my-news/* ~/my-news/config/`。

#### 3.（次选）源码编译

newsboat 是 Rust + C++ 项目，依赖较多。最小 build deps：

```bash
sudo apt install build-essential cmake pkg-config gettext \
                 libsqlite3-dev libcurl4-openssl-dev libxml2-dev \
                 libstfl-dev libjson-c-dev libncursesw5-dev \
                 cargo asciidoctor
```

然后照 [newsboat 上游 BUILD.md](https://github.com/newsboat/newsboat/blob/master/BUILD.md) 走 `make && sudo make install`。

---

## 二、装 my-news CLI（一行搞定）

```bash
uv tool install git+https://github.com/KaleLjl/my-news.git
```

跟随仓库 `main` 分支。安装完 `my-news` 在 `~/.local/bin/` 下（uv tool 的默认位置）。如果 PATH 里还没有它，跑一次：

```bash
uv tool update-shell        # 一次性把 ~/.local/bin 加进 shell rc
```

验证：

```bash
my-news --help
my-news paths
```

`paths` 会打印解析出的配置 / 数据目录（默认 `~/.config/my-news/` 和 `~/.local/share/my-news/`，或环境变量覆盖后的路径）。

---

## 三、配置 RSS 源

第一次跑 `my-news feeds` / `fetch` / `list` 时，CLI 会自动在 `~/.config/my-news/feeds/urls` 生成一个空模板，并在 stderr 提示路径。编辑该文件，每行一个 newsboat 格式的源：

```
https://simonwillison.net/atom/everything/    "ai" "blog"
https://hnrss.org/newest                       "hn"
https://blog.cloudflare.com/rss/               "infra"
```

至少要有一个源，否则 `fetch` 拿不到任何东西。

第一次拉数据：

```bash
my-news fetch
```

会自动建 `~/.local/share/my-news/cache.db`。

### 已知陷阱

- **HN 双源去重**：别同时加 `https://hnrss.org/frontpage` 和 `https://news.ycombinator.com/rss`。后者 newsboat 抓到的 `content` 只有 `"Comments"` 一个字（HN 官方 RSS 设计如此），全是噪音。**只保留 hnrss.org 那个**。
- **死源易错配**：几个常被错配的 URL（截止 2026 年）：
  - Anthropic blog：`https://www.anthropic.com/news/rss.xml`
  - OpenAI blog：`https://openai.com/blog/rss.xml`（如果 404，去 openai.com/news/ 看页脚有没有更新地址）
  - 机器之心：`https://www.jiqizhixin.com/rss`
  - 改完任何源，跑一次 `my-news doctor` 自检（见下）。
- **`my-news doctor` 自检**：编辑完 `urls` 后，跑：

  ```bash
  my-news doctor              # 表格输出
  my-news doctor --json       # 给 skill / 脚本用
  ```

  会对每条 URL 实拉一次 HTTP、检查响应是不是 RSS/Atom、标记完全重复的 URL，给出 `ok / feed_unreachable / not_a_feed / duplicate` 四种状态。

---

## 四、（可选）从旧版本迁移数据

如果你之前用过老版本（CLI 把状态存在仓库目录里：`<repo>/data/cache.db`、`<repo>/feeds/urls`、`<repo>/config/newsboat.conf`、`<repo>/digests/`），跑一次：

```bash
my-news migrate --from /path/to/old/my-news-repo
```

会把旧 cache、订阅、conf、digests 搬到新位置（`~/.config/my-news/` 和 `~/.local/share/my-news/`，或环境变量覆盖后的位置）。**幂等**：目标已存在则跳过，不会覆盖。

---

## 五、让 agent 看到 skill

skill 就是 `skills/my-news/` 这个目录，里头有 `SKILL.md` + `references/install.md`。把它放到 agent 期望的 skill 目录就行。

如果 skill 是通过 marketplace / `npx ... add` 装的，那一步已经替你做了，跳过本节。

### §V.A Claude Code

```bash
mkdir -p ~/.claude/skills
cp -r /path/to/my-news-repo/skills/my-news ~/.claude/skills/my-news
```

在 Claude Code 里输入 `/my-news` 验证 skill 触发。

### §V.B Hermes

```bash
mkdir -p ~/.hermes/skills
cp -r /path/to/my-news-repo/skills/my-news ~/.hermes/skills/my-news
```

> 上述路径以 Hermes 当前的 skill 目录约定为准（写本文档时是 `~/.hermes/skills/`）。如果你的 Hermes 版本约定别的位置，以 Hermes 官方文档为准——skill 本身是纯文件，怎么放都可以，agent 找得到就行。

在 Hermes 里 `@my-news` 或自然语言触发（描述里的关键词都能触发）。

### §V.C 其他 agent

skill 只是一个目录，含 `SKILL.md`（frontmatter 标准）和 `references/install.md`。任何能读 SKILL frontmatter 的 agent 都能识别。把目录拷到 agent 文档说的 skill 路径下即可。

---

## 六、环境变量（snap 用户必看；其他人可选）

```bash
export MY_NEWS_CONFIG="$HOME/Dropbox/my-news"     # 改 config 根（urls + newsboat.conf）
export MY_NEWS_DATA="/Volumes/external/my-news"   # 改 data 根（cache.db + digests/）
export MY_NEWS_SUMMARY_MAX_CHARS=2000             # 改 --summary-only 的截断阈值（默认 2000）
```

- **snap newsboat 用户**：必须设 `MY_NEWS_CONFIG` / `MY_NEWS_DATA` 到非 dotfile 目录（详见 §I.5）。
- **其他用户**：不设就用默认 XDG 路径，没问题。

---

## 七、（可选）定时简报

CLI 是纯 JSON 输出，接任何调度器都行。三种用法并列：

```cron
# 1. 通用：纯 JSON 落盘，谁需要就 cat
0 8 * * *  my-news fetch > /tmp/news-$(date +\%F).json

# 2. Claude Code：触发 skill 生成简报
0 8 * * *  claude code --skill my-news "今天的简报"

# 3. Hermes：以 Hermes CLI 实际语法为准
# 0 8 * * *  hermes run my-news "今天的简报"
```

`fetch` 没新内容时 skill 会输出固定字符串 `📭 没有新内容（最近一次刷新：...）`，调度器可以靠这个判断要不要推送。

**大 backlog 场景**：定时简报每天跑一次，量不会大；但首次部署或长时间没跑后第一次触发，可能有几百条积压。skill 自己会先 `fetch --no-mark --summary-only --limit 5` 侦察 `count`，按量降级（详见 [SKILL.md §3](../SKILL.md) "首次大 backlog 处理"）。

---

## 仅 CLI 贡献者：开发模式

如果你要改 `my-news` CLI 本身，不要用 `uv tool install`（每次改完都要重装），用 `uv sync` + `uv run`：

```bash
git clone https://github.com/KaleLjl/my-news.git
cd my-news
uv sync
uv run my-news --help

# 改完 skill 后用 cp 验证（不要 symlink — symlink 在某些 marketplace 工具下表现不一致）
cp -r skills/my-news ~/.claude/skills/my-news     # Claude Code
cp -r skills/my-news ~/.hermes/skills/my-news     # Hermes
```

`uv run my-news` 默认也走 XDG 用户目录，跟全局 tool 一样。如果想隔离开发环境，传 `--root <临时目录>` 强制走 in-repo 布局（隐藏 flag，仅供测试）。

---

## 排错速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `command not found: uv` | uv 没装 | 回到 §一 |
| `command not found: newsboat` | newsboat 没装；Ubuntu 24.04+ 找不到 apt 包 | 回到 §一 / §I.5 |
| `command not found: my-news` | 没装或 `~/.local/bin` 不在 PATH | `uv tool install git+...`；`uv tool update-shell` |
| `/my-news` 在 Claude Code 里不出现 | skill 没放到 `~/.claude/skills/my-news/` | 看 §V.A |
| `@my-news` 在 Hermes 里不触发 | skill 没放到 Hermes skill 目录 | 看 §V.B |
| snap newsboat 报 `permission denied` 读 `urls` | snap home interface 摸不到 dotfile 目录 | 设 `MY_NEWS_CONFIG` / `MY_NEWS_DATA` 到非隐藏目录，详见 §I.5 #2 |
| `fetch` 报 newsboat lock 冲突 | 另一个 newsboat 进程还活着 | `pkill newsboat` 后再试 |
| `fetch` 出错且 `last-error.log` 提示 SSL/HTTP | 单个源临时挂了 | 一般等等就好；持续挂的源跑 `my-news doctor` 定位后从 `urls` 摘掉 |
| `doctor` 报 `not_a_feed` | URL 对了但响应不是 RSS（多半是 HTML 落地页） | 去站点重找 RSS 入口 URL |
| `doctor` 报 `feed_unreachable` 且持续 | 源真挂了或迁了 | 删行或换新 URL |
| `doctor` 报 `duplicate` | 同一 URL 写了两次 | 删一行 |
| JSON 解析失败 / 上下文爆掉 | 单条 content 上万字（如 Cloudflare 长博客）或 backlog 数百条 | 用 `--summary-only` 截断、`--limit` 分批；详见 [SKILL.md §3](../SKILL.md) |

需要更详细的命令说明：见仓库根的 `README.md`。
