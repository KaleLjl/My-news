#!/usr/bin/env bash
# my-news skill — 一键安装脚本
#
# 干的事（每一步都 idempotent，重跑无害）：
#   1. 检测 / 提示装 newsboat
#   2. 检测 / 提示装 uv
#   3. 找到 my-news 项目（自动探测 / 询问用户）
#   4. 在项目里跑 uv sync
#   5. 把 skill symlink 到 ~/.claude/skills/my-news
#   6. 给出 MY_NEWS_HOME 的导出建议

set -e

# ---------- 工具函数 ----------
say()  { printf '\033[1;36m▸ %s\033[0m\n' "$*"; }
warn() { printf '\033[1;33m! %s\033[0m\n' "$*"; }
ok()   { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
err()  { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; }

have() { command -v "$1" >/dev/null 2>&1; }

# ---------- 路径推断 ----------
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
SKILL_DIR="$( cd "$SCRIPT_DIR/.." && pwd )"

# 如果 skill 在仓库里（即 SKILL_DIR/../../pyproject.toml 存在且 name=my-news），
# 那 SKILL_DIR/../.. 就是项目根。
GUESSED_REPO=""
if [ -f "$SKILL_DIR/../../pyproject.toml" ] && grep -q '^name = "my-news"' "$SKILL_DIR/../../pyproject.toml" 2>/dev/null; then
  GUESSED_REPO="$( cd "$SKILL_DIR/../.." && pwd )"
fi

# ---------- §1 newsboat ----------
say "检查 newsboat"
if have newsboat; then
  ok "newsboat 已装：$(newsboat --version | head -1)"
else
  warn "没装 newsboat。"
  if [[ "$OSTYPE" == "darwin"* ]] && have brew; then
    read -rp "  用 'brew install newsboat' 装上？[Y/n] " ans
    if [[ ! "$ans" =~ ^[Nn]$ ]]; then
      brew install newsboat
    fi
  elif have apt; then
    warn "  请手动跑：sudo apt install newsboat"
  elif have pacman; then
    warn "  请手动跑：sudo pacman -S newsboat"
  else
    err "  未识别包管理器，请参考 references/install.md §一 自行安装"
  fi
fi

# ---------- §2 uv ----------
say "检查 uv"
if have uv; then
  ok "uv 已装：$(uv --version)"
else
  warn "没装 uv。"
  if [[ "$OSTYPE" == "darwin"* ]] && have brew; then
    read -rp "  用 'brew install uv' 装上？[Y/n] " ans
    if [[ ! "$ans" =~ ^[Nn]$ ]]; then
      brew install uv
    fi
  else
    read -rp "  用 astral 官方脚本装 uv？[Y/n] " ans
    if [[ ! "$ans" =~ ^[Nn]$ ]]; then
      curl -LsSf https://astral.sh/uv/install.sh | sh
      warn "  装完可能需要重启 shell 或 source ~/.cargo/env / ~/.local/bin"
    fi
  fi
fi

# ---------- §3 找项目 ----------
say "定位 my-news 项目"

# 优先级：1) $MY_NEWS_HOME  2) 紧邻 skill 的仓库  3) 常见候选路径
PROJECT=""
if [ -n "${MY_NEWS_HOME:-}" ] && [ -d "$MY_NEWS_HOME" ]; then
  PROJECT="$MY_NEWS_HOME"
  ok "用环境变量 MY_NEWS_HOME=$PROJECT"
elif [ -n "$GUESSED_REPO" ]; then
  PROJECT="$GUESSED_REPO"
  ok "skill 装在仓库里，直接用：$PROJECT"
else
  for cand in "$HOME/Workspace/my-news" "$HOME/my-news" "$HOME/Projects/my-news" "$HOME/code/my-news"; do
    if [ -d "$cand" ] && [ -f "$cand/pyproject.toml" ]; then
      PROJECT="$cand"
      ok "在 $PROJECT 找到了"
      break
    fi
  done
fi

if [ -z "$PROJECT" ]; then
  warn "没找到 my-news 项目。"
  echo "  默认会克隆到 ~/Workspace/my-news。"
  read -rp "  现在克隆？[Y/n] " ans
  if [[ ! "$ans" =~ ^[Nn]$ ]]; then
    mkdir -p "$HOME/Workspace"
    git clone https://github.com/KaleLjl/my-news.git "$HOME/Workspace/my-news"
    PROJECT="$HOME/Workspace/my-news"
    ok "克隆完成：$PROJECT"
  else
    err "需要项目本体才能继续。手动克隆后重跑本脚本，或 export MY_NEWS_HOME=<路径>。"
    exit 1
  fi
fi

# ---------- §4 uv sync ----------
say "在项目里跑 uv sync"
if have uv; then
  ( cd "$PROJECT" && uv sync )
  ok "依赖装好了"

  say "做一次烟囱测试：uv run my-news --help"
  if ( cd "$PROJECT" && uv run my-news --help >/dev/null 2>&1 ); then
    ok "CLI 可以跑"
  else
    err "uv run my-news --help 失败。先解决这个再继续（看上一行的 stderr）。"
    exit 1
  fi
else
  warn "uv 没装，跳过 uv sync。装好 uv 后重跑本脚本。"
fi

# ---------- §5 symlink skill ----------
say "把 skill 链到 ~/.claude/skills/my-news"
mkdir -p "$HOME/.claude/skills"
TARGET="$HOME/.claude/skills/my-news"

if [ -L "$TARGET" ]; then
  CURRENT="$(readlink "$TARGET")"
  if [ "$CURRENT" = "$SKILL_DIR" ]; then
    ok "已经链到当前 skill：$CURRENT"
  else
    warn "$TARGET 当前指向 $CURRENT"
    read -rp "  覆盖成 $SKILL_DIR？[Y/n] " ans
    if [[ ! "$ans" =~ ^[Nn]$ ]]; then
      rm "$TARGET"
      ln -s "$SKILL_DIR" "$TARGET"
      ok "已重链：$TARGET → $SKILL_DIR"
    fi
  fi
elif [ -e "$TARGET" ]; then
  err "$TARGET 已经存在且不是 symlink（可能是手动复制的旧版本）。"
  err "请先手动确认是否能删除：ls -la $TARGET"
else
  ln -s "$SKILL_DIR" "$TARGET"
  ok "已链：$TARGET → $SKILL_DIR"
fi

# ---------- §6 持久化 MY_NEWS_HOME ----------
# skill 强制要 $MY_NEWS_HOME，所以不论项目放哪都得把它写进 shell rc，
# 不然新 shell 一开就丢了。
say "持久化 MY_NEWS_HOME（skill 强制依赖）"

# 选 rc 文件：优先看 $SHELL，再退回 zsh 和 bash 都存在的那个
RC_FILE=""
case "${SHELL:-}" in
  */zsh)  RC_FILE="$HOME/.zshrc" ;;
  */bash) RC_FILE="$HOME/.bashrc" ;;
esac
if [ -z "$RC_FILE" ]; then
  if [ -f "$HOME/.zshrc" ]; then RC_FILE="$HOME/.zshrc"
  elif [ -f "$HOME/.bashrc" ]; then RC_FILE="$HOME/.bashrc"
  else RC_FILE="$HOME/.zshrc"   # macOS 默认
  fi
fi

EXPORT_LINE="export MY_NEWS_HOME=\"$PROJECT\""

if [ -f "$RC_FILE" ] && grep -Fq "MY_NEWS_HOME" "$RC_FILE"; then
  # rc 里已经有一行，看是不是指向同一个路径
  EXISTING=$(grep -E '^[^#]*export[[:space:]]+MY_NEWS_HOME=' "$RC_FILE" | tail -1 || true)
  if [[ "$EXISTING" == *"\"$PROJECT\""* ]] || [[ "$EXISTING" == *"=$PROJECT"* ]]; then
    ok "$RC_FILE 里已经设过 MY_NEWS_HOME 且指向当前项目"
  else
    warn "$RC_FILE 里已有 MY_NEWS_HOME，但指向别的路径："
    echo "  $EXISTING"
    echo "  期望：$EXPORT_LINE"
    echo "  请你自己确认要不要改（这个脚本不会动你旧的导出）"
  fi
else
  echo "  准备把这行追加到 $RC_FILE："
  echo "    $EXPORT_LINE"
  read -rp "  追加？[Y/n] " ans
  if [[ ! "$ans" =~ ^[Nn]$ ]]; then
    {
      echo ""
      echo "# my-news skill"
      echo "$EXPORT_LINE"
    } >> "$RC_FILE"
    ok "已写入 $RC_FILE"
  else
    warn "跳过了。你之后需要自己加，否则 skill 不会工作："
    echo "  echo '$EXPORT_LINE' >> $RC_FILE"
  fi
fi

echo
ok "全部装好。"
echo "  · 当前 shell 立即生效（不用重开终端）："
echo "      $EXPORT_LINE"
echo "  · 进 Claude Code 试一下：/my-news"
