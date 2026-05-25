# my-news skill — 安装手册

这个 skill 是个壳，真正干活的是 [`my-news` CLI](https://github.com/KaleLjl/my-news)（基于 newsboat + trafilatura，状态走 XDG 用户目录，可直接 `uv tool install`）。**安装 skill 的本质**是装好 CLI；skill 本体只需要待在 `~/.claude/skills/my-news/` 即可。

---

## 一、装系统依赖（newsboat + uv）

```bash
# macOS
brew install newsboat
brew install uv

# Linux (Debian/Ubuntu)
sudo apt install newsboat
curl -LsSf https://astral.sh/uv/install.sh | sh

# Linux (Arch)
sudo pacman -S newsboat
sudo pacman -S uv   # 或者用 astral 的官方安装脚本
```

验证：

```bash
newsboat --version
uv --version
```

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

`paths` 会打印解析出的配置 / 数据目录（默认 `~/.config/my-news/` 和 `~/.local/share/my-news/`）。

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

---

## 四、（可选）从旧版本迁移数据

如果你之前用过老版本（CLI 把状态存在仓库目录里：`<repo>/data/cache.db`、`<repo>/feeds/urls`、`<repo>/config/newsboat.conf`、`<repo>/digests/`），跑一次：

```bash
my-news migrate --from /path/to/old/my-news-repo
```

会把旧 cache、订阅、conf、digests 搬到新位置（`~/.config/my-news/` 和 `~/.local/share/my-news/`）。**幂等**：目标已存在则跳过，不会覆盖。

---

## 五、让 Claude Code 看到 skill

如果 skill 是通过 marketplace / `npx ... add` 装的，它已经在 `~/.claude/skills/my-news/` 下了，跳过这一步。

如果你是从本仓库手动装：

```bash
mkdir -p ~/.claude/skills
cp -r /path/to/my-news-repo/skills/my-news ~/.claude/skills/my-news
```

在 Claude Code 里输入 `/my-news` 验证 skill 触发。

---

## 六、（可选）自定义路径

如果你不想用默认 XDG 路径，两个环境变量可以改：

```bash
export MY_NEWS_CONFIG="$HOME/Dropbox/my-news"     # 改 config 根（urls + newsboat.conf）
export MY_NEWS_DATA="/Volumes/external/my-news"   # 改 data 根（cache.db + digests/）
```

不设就用默认。

---

## 七、（可选）定时简报

CLI 是纯 JSON 输出，接任何调度器都行。两种常用：

```cron
# 每天 8 点把原始 JSON 落地（不调 LLM）
0 8 * * *  my-news fetch > /tmp/news-$(date +\%F).json

# 每天 8 点触发 Claude Code 生成简报到 digests/
0 8 * * *  claude code --skill my-news "今天的简报"
```

`fetch` 在没有新内容时 skill 会输出固定字符串 `📭 没有新内容（...）`，调度器可以靠这个判断要不要推送。

---

## 仅 CLI 贡献者：开发模式

如果你要改 `my-news` CLI 本身，不要用 `uv tool install`（每次改完都要重装），用 `uv sync` + `uv run`：

```bash
git clone https://github.com/KaleLjl/my-news.git
cd my-news
uv sync
uv run my-news --help

# 改完 skill 后用 cp 验证（不要 symlink — symlink 在某些 marketplace 工具下表现不一致）
cp -r skills/my-news ~/.claude/skills/my-news
```

`uv run my-news` 默认也走 XDG 用户目录，跟全局 tool 一样。如果想隔离开发环境，传 `--root <临时目录>` 强制走 in-repo 布局（隐藏 flag，仅供测试）。

---

## 排错速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `command not found: uv` | uv 没装 | 回到 §一 |
| `command not found: newsboat` | newsboat 没装 | 回到 §一 |
| `command not found: my-news` | 没装或 `~/.local/bin` 不在 PATH | `uv tool install git+...`；`uv tool update-shell` |
| `/my-news` 在 Claude Code 里不出现 | skill 没放到 `~/.claude/skills/my-news/` | 看 §五 |
| `fetch` 报 newsboat lock 冲突 | 另一个 newsboat 进程还活着 | `pkill newsboat` 后再试 |
| `fetch` 出错且 `~/.local/share/my-news/last-error.log` 提示 SSL/HTTP | 单个源临时挂了 | 一般等等就好；持续挂的源考虑从 `feeds/urls` 摘掉 |

需要更详细的命令说明：见仓库根的 `README.md`。
