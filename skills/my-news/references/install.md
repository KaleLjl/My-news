# my-news skill — 新机器安装手册

这个 skill 本身只是一组 markdown 提示词，**真正干活的是 [my-news CLI](https://github.com/KaleLjl/my-news)**——一个基于 newsboat + trafilatura 的 RSS 抓取工具。所以"安装 skill"实际上是两件事：

1. 把 CLI 跑起来
2. 把 skill 让 Claude Code 看到

下面是从零开始的全套步骤。中途任意一步可以让 Claude 帮你做。

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

## 二、克隆 CLI 仓库

随便选个目录，**仓库名保持 `my-news`**，skill 的路径探测会更顺：

```bash
mkdir -p ~/Workspace
cd ~/Workspace
git clone https://github.com/KaleLjl/my-news.git
cd my-news
```

如果你想放别的位置（比如 `~/code/my-news`），后面记得 `export MY_NEWS_HOME=...`。

---

## 三、装 Python 依赖

在仓库根目录跑：

```bash
uv sync
```

这会在 `.venv/` 里把 `trafilatura` 等依赖装好。完成后验证 CLI 能跑：

```bash
uv run my-news --help
```

看到子命令列表（fetch / list / show / feeds）就算装好。

---

## 四、配置 RSS 源

编辑 `feeds/urls`，每行一个 newsboat 格式的源：

```
https://simonwillison.net/atom/everything/    "ai" "blog"
https://hnrss.org/newest                       "hn"
https://blog.cloudflare.com/rss/               "infra"
```

注意：**至少要有一个源**，否则 `fetch` 拿不到任何东西。

第一次拉数据：

```bash
uv run my-news fetch
```

会自动建 `data/cache.db`。

---

## 五、让 Claude Code 看到 skill

Claude Code 在 `~/.claude/skills/` 下扫所有子目录。把仓库里的 `skills/my-news` 链过去（推荐用 symlink，仓库更新就自动同步）：

```bash
mkdir -p ~/.claude/skills
ln -s "$(pwd)/skills/my-news" ~/.claude/skills/my-news
```

如果已经存在同名目录/链接，先看下是不是你自己之前装的：

```bash
ls -la ~/.claude/skills/my-news
```

是旧的就 `rm ~/.claude/skills/my-news` 后再 `ln -s`（注意：只 rm 链接本身、不会删仓库里的源文件）。

验证：在 Claude Code 里输入 `/my-news`，应该能看到这个 skill 触发。

---

## 六、设置 `MY_NEWS_HOME`（必需）

skill 通过 `$MY_NEWS_HOME` 找项目本体——这是**唯一**的解析途径，没有这个变量就跑不起来。`setup.sh` 已经会自动追加这一行到 `~/.zshrc` / `~/.bashrc`。如果你是手动安装：

```bash
# zsh
echo 'export MY_NEWS_HOME="'"$(pwd)"'"' >> ~/.zshrc
source ~/.zshrc

# bash
echo 'export MY_NEWS_HOME="'"$(pwd)"'"' >> ~/.bashrc
source ~/.bashrc
```

验证：

```bash
[ -n "$MY_NEWS_HOME" ] && [ -f "$MY_NEWS_HOME/pyproject.toml" ] && echo OK
```

输出 `OK` 才说明 skill 能用了。

---

## 七、（可选）定时简报

CLI 是纯 JSON 输出，接任何调度器都行。两种常用：

```cron
# 每天 8 点把原始 JSON 落地（不调 LLM）
0 8 * * *  cd ~/Workspace/my-news && uv run my-news fetch > /tmp/news-$(date +\%F).json

# 每天 8 点触发 Claude Code 生成简报到 digests/
0 8 * * *  claude code --skill my-news "今天的简报"
```

`fetch` 在没有新内容时 skill 会输出固定字符串 `📭 没有新内容（...）`，调度器可以靠这个判断要不要推送。

---

## 排错速查

| 现象 | 原因 | 处理 |
|---|---|---|
| `command not found: uv` | uv 没装 | 回到 §一 |
| `command not found: newsboat` | newsboat 没装 | 回到 §一 |
| `uv run my-news` 报 `ModuleNotFoundError` | 没 `uv sync` 过 | 在仓库里跑 `uv sync` |
| `/my-news` 在 Claude Code 里不出现 | symlink 没建对 / 路径错 | `ls -la ~/.claude/skills/my-news` 看链接目标 |
| `fetch` 报 newsboat lock 冲突 | 另一个 newsboat 进程还活着 | `pkill newsboat` 后再试 |
| `fetch` 出错且 `data/last-error.log` 提示 SSL/HTTP | 单个源临时挂了 | 一般等等就好；持续挂的源考虑从 `feeds/urls` 摘掉 |

需要更详细的命令说明：见仓库根的 `README.md`。
