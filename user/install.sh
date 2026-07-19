#!/usr/bin/env bash
#
# ユーザーレベルのエージェント設定を ~/.claude と ~/.config/opencode に symlink する。
# べき等: 何度実行しても同じ結果になる。ランタイムデータ（cache, projects 等）には触れない。
#
set -euo pipefail

USER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Claude Code (~/.claude) ---
mkdir -p "${HOME}/.claude"

# 旧 dotfiles 由来の symlink / rules ディレクトリを除去してから張り直す
rm -f  "${HOME}/.claude/CLAUDE.md" "${HOME}/.claude/AGENTS.md" "${HOME}/.claude/settings.json"
rm -rf "${HOME}/.claude/rules"

# CLAUDE.md は @~/.claude/AGENTS.md を import するため、AGENTS.md も ~/.claude に置く
ln -sfn "${USER_DIR}/AGENTS.md"     "${HOME}/.claude/AGENTS.md"
ln -sfn "${USER_DIR}/CLAUDE.md"     "${HOME}/.claude/CLAUDE.md"
ln -sfn "${USER_DIR}/settings.json" "${HOME}/.claude/settings.json"
ln -sfn "${USER_DIR}/rules"         "${HOME}/.claude/rules"

# --- OpenCode (~/.config/opencode) ---
mkdir -p "${HOME}/.config/opencode"
ln -sfn "${USER_DIR}/AGENTS.md" "${HOME}/.config/opencode/AGENTS.md"

echo "Linked user-level agent config from ${USER_DIR}"
