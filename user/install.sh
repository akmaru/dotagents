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

# --- Claude Code hooks / statusLine (~/.local/bin) ---
# settings.json が参照するスクリプト。settings.json 同様、絶対パスに依存しないよう
# ~/.local/bin に symlink し、PATH 経由で解決させる。
mkdir -p "${HOME}/.local/bin"
ln -sfn "${USER_DIR}/bin/claude-statusline.sh"    "${HOME}/.local/bin/claude-statusline.sh"
ln -sfn "${USER_DIR}/bin/claude-context.py"       "${HOME}/.local/bin/claude-context.py"
# SessionEnd hook。SessionStart と違い herdr が書かない配列なので、登録は
# user/settings.json 側の deep merge に任せられる（docs/adr/0017）。
ln -sfn "${USER_DIR}/bin/hindsight-retain-hook.sh" "${HOME}/.local/bin/hindsight-retain-hook.sh"

# コンテキスト使用量の記録・要点表示を SessionStart hook として登録する（docs/adr/0013）。
# hooks.SessionStart は herdr も書き込む配列で、上の deep merge では配列が丸ごと置換される。
# user/settings.json に持たせると herdr の hook を消してしまうので、ここで無ければ末尾に足す。
CONTEXT_HOOK_CMD="claude-context.py session-start"
jq --arg cmd "${CONTEXT_HOOK_CMD}" '
  .hooks.SessionStart = ((.hooks.SessionStart // []) as $h
    | if any($h[]?; (.hooks // []) | any(.command == $cmd)) then $h
      else $h + [{"matcher": "startup|resume", "hooks": [{"type": "command", "command": $cmd, "timeout": 10}]}]
      end)
' "${SETTINGS}" > "${SETTINGS}.tmp"
mv "${SETTINGS}.tmp" "${SETTINGS}"

# ワークフローグラフの hook（docs/adr/0020）。規約と現在地の注入（UserPromptSubmit）と、
# 抜ける条件・起動条件の強制（PreToolUse, Bash と Workflow）。どちらも他ツールが書き得る配列なので、
# SessionStart と同じく「無ければ末尾に足す」。
ln -sfn "${USER_DIR}/bin/workflow-graph-state.sh" "${HOME}/.local/bin/workflow-graph-state.sh"
ln -sfn "${USER_DIR}/bin/workflow-graph-guard.sh" "${HOME}/.local/bin/workflow-graph-guard.sh"
add_hook_once() {
  # $1: イベント名, $2: matcher, $3: command
  jq --arg ev "$1" --arg m "$2" --arg cmd "$3" '
    .hooks[$ev] = ((.hooks[$ev] // []) as $h
      | if any($h[]?; (.hooks // []) | any(.command == $cmd)) then $h
        else $h + [{"matcher": $m, "hooks": [{"type": "command", "command": $cmd, "timeout": 10}]}]
        end)
  ' "${SETTINGS}" > "${SETTINGS}.tmp"
  mv "${SETTINGS}.tmp" "${SETTINGS}"
}
add_hook_once "UserPromptSubmit" "*"    "workflow-graph-state.sh"
add_hook_once "PreToolUse"       "Bash|Workflow" "workflow-graph-guard.sh"

# --- workflows (~/.claude/workflows) ---
# 保存ワークフロー（SCC ごとに 1 本、docs/adr/0020）をファイル単位で symlink する。
# /workflows の保存ダイアログは「対象ファイル自身が symlink」のときだけ拒否するので、
# ディレクトリごと張ると保存が repo に書き込む。agents と同じ配り方にする。
WORKFLOWS_LINK_DIR="${HOME}/.claude/workflows"
mkdir -p "${WORKFLOWS_LINK_DIR}"
for link in "${WORKFLOWS_LINK_DIR}"/*.js; do
  [ -L "${link}" ] || continue
  case "$(readlink "${link}")" in
    "${USER_DIR}/workflows/"*) [ -e "${link}" ] || rm -f "${link}" ;;
  esac
done
for src in "${USER_DIR}"/workflows/*.js; do
  [ -e "${src}" ] || continue
  ln -sfn "${src}" "${WORKFLOWS_LINK_DIR}/$(basename "${src}")"
done

# --- agents (~/.claude/agents) ---
# 役割定義（サブエージェント）はファイル単位で symlink する（docs/adr/0014）。
# ディレクトリごと張ると /agents UI が書いた定義が repo に入り、OpenCode が読めない
# frontmatter（tools: "Read, Grep" 等）を配ってしまう。OpenCode 側への配布は、
# Claude 固有キーが provider に流れて拒否されないことを検証してから足す。
AGENTS_LINK_DIR="${HOME}/.claude/agents"
mkdir -p "${AGENTS_LINK_DIR}"
# repo 側で消した役割の壊れたリンクを掃除する（dotagents 由来のものだけ）
for link in "${AGENTS_LINK_DIR}"/*.md; do
  [ -L "${link}" ] || continue
  case "$(readlink "${link}")" in
    "${USER_DIR}/agents/"*) [ -e "${link}" ] || rm -f "${link}" ;;
  esac
done
for src in "${USER_DIR}"/agents/*.md; do
  dst="${AGENTS_LINK_DIR}/$(basename "${src}")"
  # /agents UI や手で書いた同名の実ファイルは消さず退避する
  if [ -e "${dst}" ] && [ ! -L "${dst}" ]; then
    mkdir -p "${AGENTS_LINK_DIR}.pre-dotagents"
    mv "${dst}" "${AGENTS_LINK_DIR}.pre-dotagents/"
  fi
  ln -sfn "${src}" "${dst}"
done

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
