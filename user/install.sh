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

# herdr plugins: ~/.config/herdr/plugins.json は絶対パスとインストール時刻を持つため
# symlink で配れない。宣言的に install する（docs/adr/0010）。
# ref は検証済みのコミットに固定する。更新は ref を書き換えて再実行するだけでよい
# （herdr が既存インストールを replace する）。
HERDR_PLUGINS=(
  # タブ名を作業内容から自動生成する。ビルドに Go が要る
  "kryptamine/herdr-auto-title@a34f22d1fc8a6037d171789cfda17289088527e0"
  # エージェントの差分をレビューし、行コメントをエージェントの入力欄へ送る
  "persiyanov/herdr-reviewr@4c090225af706bf3aaa24b39fea890a72994f40f"
  # nvim をサイドバーで開き、エージェントの出力からファイルを拾う
  "ChmaraX/herdr-nvim@e652ebf7b3d6713992e68a30aec588822e69fae5"
)

if [ "${DOTAGENTS_SKIP_HERDR_PLUGINS:-}" != "1" ] && command -v herdr >/dev/null 2>&1; then
  # 一覧が引けない時点で install も全滅する（CLI とサーバのプロトコル不一致など）。
  # 個別の失敗として 3 回報告すると真因が埋もれるので、ここで止めて herdr の
  # エラーをそのまま見せる。
  if ! installed="$(herdr plugin list 2>&1)"; then
    echo "herdr plugin: 一覧の取得に失敗したためインストールをスキップします" >&2
    printf '%s\n' "${installed}" >&2
  else
    for entry in "${HERDR_PLUGINS[@]}"; do
      repo="${entry%@*}"
      ref="${entry##*@}"
      case "${installed}" in
        *"github:${repo}@${ref}"*) continue ;;
      esac
      echo "herdr plugin: installing ${repo}@${ref}"
      if ! output="$(herdr plugin install "${repo}" --ref "${ref}" --yes 2>&1)"; then
        echo "herdr plugin: ${repo}@${ref} のインストールに失敗" >&2
        printf '%s\n' "${output}" >&2
      fi
    done
  fi
  # プラグインは herdr サーバがセッションを復元するときに起動する。
  # 初回導入時は `herdr server stop` が要る（reload-config では起動しない）。
fi

# config.toml の popup バインドが呼ぶ外部コマンド。無くても install は続行する
command -v lazygit >/dev/null 2>&1 ||
  echo "lazygit が見つかりません（prefix+alt+g のバインドに必要）" >&2

echo "Linked user-level agent config from ${USER_DIR}"
