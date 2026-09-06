#!/usr/bin/env bash
#
# フォーカス中の Claude Code セッションを分岐し、隣の pane で起動する。
# herdr の [[keys.command]] (type = "shell") から呼ばれる想定。
#
# セッション ID は herdr の Claude Code integration が SessionStart で報告した値を使う。
# 未インストールなら: herdr integration install claude
#
set -euo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"

# keybinding からの起動は herdr サーバの環境を継承するため、jq が PATH にないことがある
command -v jq >/dev/null 2>&1 || PATH="${HOME}/.local/share/mise/shims:/opt/homebrew/bin:/usr/local/bin:${PATH}"

notify() {
  "$HERDR" notification show "$1" --body "${2:-}" --sound "${3:-none}" >/dev/null 2>&1 || true
}

die() {
  notify "fork: 失敗" "$1" request
  exit 1
}

command -v jq >/dev/null 2>&1 || die "jq が見つからない"

pane="${HERDR_ACTIVE_PANE_ID:-}"
[[ -n "$pane" ]] || die "フォーカス中の pane を特定できない"

info=$("$HERDR" pane get "$pane") || die "pane get に失敗した ($pane)"

agent=$(jq -r '.result.pane.agent // ""' <<<"$info")
[[ "$agent" == "claude" ]] || die "この pane で動いているのは Claude Code ではない (agent=${agent:-none})"

sid=$(jq -r '.result.pane.agent_session | if .kind == "id" then .value else "" end' <<<"$info")
[[ -n "$sid" ]] || die "セッション ID が未報告。integration 導入後に開始したセッションのみ分岐できる"

# 会話が 1 往復もないセッションは transcript が無く --resume が失敗するため先に弾く
claude_root="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
[[ -n $(find "$claude_root/projects" -maxdepth 2 -name "$sid.jsonl" -print -quit 2>/dev/null) ]] ||
  die "まだ会話が記録されていないセッションは分岐できない ($sid)"

cwd=$(jq -r '.result.pane.foreground_cwd // .result.pane.cwd // ""' <<<"$info")
[[ -n "$cwd" ]] || cwd="${HERDR_ACTIVE_PANE_CWD:-$HOME}"

# 横長なら右、縦長なら下に割る。端末セルは幅が高さの約半分なので width/2 で比較する
read -r w h < <("$HERDR" pane layout --pane "$pane" |
  jq -r --arg p "$pane" '.result.layout.panes[] | select(.pane_id == $p) | "\(.rect.width) \(.rect.height)"') || true
if [[ -n "${w:-}" && -n "${h:-}" && $((w / 2)) -lt $h ]]; then dir=down; else dir=right; fi

# エージェント名はライブなもの同士でユニークである必要がある
used=$("$HERDR" agent list | jq -r '.result.agents[].name // empty')
for i in $(seq 1 99); do
  name="fork$i"
  grep -qx "$name" <<<"$used" || break
done

new=$("$HERDR" pane split --pane "$pane" --direction "$dir" --cwd "$cwd" --no-focus |
  jq -r '.result.pane.pane_id')
[[ -n "$new" && "$new" != "null" ]] || die "pane の分割に失敗した"

# 起動に失敗したら作った pane を残さない
die_pane() {
  "$HERDR" pane close "$new" >/dev/null 2>&1 || true
  die "$1"
}

# 分割直後の pane はシェルがまだプロンプトに達しておらず agent_pane_busy になる
for _ in $(seq 1 40); do
  if out=$("$HERDR" agent start "$name" --kind claude --pane "$new" --timeout 60000 \
    -- --resume "$sid" --fork-session 2>&1); then
    break
  fi
  grep -q "agent_pane_busy" <<<"$out" || die_pane "分岐セッションの起動に失敗した: $out"
  sleep 0.25
done
grep -q '"type":"agent_started"' <<<"${out:-}" || die_pane "分岐セッションが起動しなかった (pane=$new)"

# 分岐先にそのまま指示を出せるようフォーカスを移す（元 pane に残りたいならこの行を消す）
"$HERDR" agent focus "$name" >/dev/null 2>&1 || true

notify "fork: $name" "$new に分岐した (from ${sid:0:8})" done
