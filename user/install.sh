#!/usr/bin/env bash
#
# ユーザーレベルのエージェント設定を ~/.claude / ~/.config/opencode / ~/.config/herdr へ配布する。
# settings.json のみマージ、それ以外は symlink。
# べき等: 何度実行しても同じ結果になる。ランタイムデータ（cache, projects 等）には触れない。
#
set -euo pipefail

USER_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if ! command -v jq >/dev/null 2>&1; then
  echo "jq が必要です（settings.json のマージに使用）" >&2
  exit 1
fi

# --- Claude Code (~/.claude) ---
mkdir -p "${HOME}/.claude"

# 旧 dotfiles 由来の symlink / rules ディレクトリを除去してから張り直す
rm -f  "${HOME}/.claude/CLAUDE.md" "${HOME}/.claude/AGENTS.md"
rm -rf "${HOME}/.claude/rules"

# CLAUDE.md は @~/.claude/AGENTS.md を import するため、AGENTS.md も ~/.claude に置く
ln -sfn "${USER_DIR}/AGENTS.md" "${HOME}/.claude/AGENTS.md"
ln -sfn "${USER_DIR}/CLAUDE.md" "${HOME}/.claude/CLAUDE.md"
ln -sfn "${USER_DIR}/rules"     "${HOME}/.claude/rules"

# settings.json だけは symlink せずマージする（docs/adr/0009）。
# herdr の hook や /config がローカルに書くマシン固有のキーを残したまま、
# dotagents で定義したキーを上書きする。競合時はリポジトリ側が勝つ。
SETTINGS="${HOME}/.claude/settings.json"
if [ -L "${SETTINGS}" ]; then
  rm -f "${SETTINGS}"  # 旧 symlink 方式からの移行
fi
if [ ! -f "${SETTINGS}" ]; then
  echo '{}' > "${SETTINGS}"
fi
jq -s '.[0] * .[1]' "${SETTINGS}" "${USER_DIR}/settings.json" > "${SETTINGS}.tmp"
mv "${SETTINGS}.tmp" "${SETTINGS}"

# --- OpenCode (~/.config/opencode) ---
mkdir -p "${HOME}/.config/opencode"
ln -sfn "${USER_DIR}/AGENTS.md" "${HOME}/.config/opencode/AGENTS.md"

# --- herdr (~/.config/herdr) ---
# 設定とスクリプトだけを symlink する。socket / log / session.json などのランタイムには触らない
mkdir -p "${HOME}/.config/herdr"

# herdr 自身が書き込んだ既存 config は退避してから張り替える
if [ -e "${HOME}/.config/herdr/config.toml" ] && [ ! -L "${HOME}/.config/herdr/config.toml" ]; then
  mv "${HOME}/.config/herdr/config.toml" "${HOME}/.config/herdr/config.toml.pre-dotagents"
fi
ln -sfn "${USER_DIR}/herdr/config.toml" "${HOME}/.config/herdr/config.toml"

rm -rf "${HOME}/.config/herdr/scripts"
ln -sfn "${USER_DIR}/herdr/scripts" "${HOME}/.config/herdr/scripts"

# Claude Code integration: pane と Claude セッション ID を紐付ける SessionStart hook。
# hook スクリプト本体は herdr が生成・更新するので repo では管理しない。
if [ "${DOTAGENTS_SKIP_HERDR_INTEGRATION:-}" != "1" ] && command -v herdr >/dev/null 2>&1; then
  herdr integration install claude >/dev/null
  herdr server reload-config >/dev/null 2>&1 || true
fi

echo "Linked user-level agent config from ${USER_DIR}"
