#!/usr/bin/env bash
#
# メインの隣に解説役 (explainer) の常駐セッションを起動する、または既にあれば呼び出す。
# herdr の [[keys.command]] (type = "shell") から呼ばれる想定。
#
# メイン pane の特定・explainer pane の再利用規則は docs/design/explainer-pane.md。
# 起動の骨格は fork-claude-session.sh を型にしているが、同スクリプトは改造しない方針
# （docs/adr/0016）のため、共通部（通知・pane 分割・busy リトライ）は複製している。
#
set -euo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"

# keybinding からの起動は herdr サーバの環境を継承するため、jq が PATH にないことがある
command -v jq >/dev/null 2>&1 || PATH="${HOME}/.local/share/mise/shims:/opt/homebrew/bin:/usr/local/bin:${PATH}"

notify() {
  "$HERDR" notification show "$1" --body "${2:-}" --sound "${3:-none}" >/dev/null 2>&1 || true
}

die() {
  notify "explainer: 失敗" "$1" request
  exit 1
}

command -v jq >/dev/null 2>&1 || die "jq が見つからない"

pane="${HERDR_ACTIVE_PANE_ID:-}"
[[ -n "$pane" ]] || die "フォーカス中の pane を特定できない"

info=$("$HERDR" pane get "$pane") || die "pane get に失敗した ($pane)"

agent=$(jq -r '.result.pane.agent // ""' <<<"$info")
[[ "$agent" == "claude" ]] || die "この pane で動いているのは Claude Code ではない (agent=${agent:-none})"

sid=$(jq -r '.result.pane.agent_session | if .kind == "id" then .value else "" end' <<<"$info")
[[ -n "$sid" ]] || die "セッション ID が未報告。integration 導入後に開始したセッションのみ使える"

label=$(jq -r '.result.pane.label // ""' <<<"$info")
if [[ "$label" == "explainer" ]]; then
  notify "explainer" "explainer の pane で押した。メインの pane で押す" request
  exit 0
fi

cwd=$(jq -r '.result.pane.foreground_cwd // .result.pane.cwd // ""' <<<"$info")
[[ -n "$cwd" ]] || cwd="${HERDR_ACTIVE_PANE_CWD:-$HOME}"

tab_id=$(jq -r '.result.pane.tab_id // ""' <<<"$info")
[[ -n "$tab_id" ]] || die "タブ ID を特定できない ($pane)"

# herdr のエージェント名はライブなもの同士で一意である必要がある
# (fork-claude-session.sh 参照)。固定名 "explainer" だと別タブで explainer が
# 生きている間はこのタブで agent start が失敗するので、タブ ID を name に含める。
# 名前に使えるのは小文字・数字・'-'・'_' の 1〜32 文字（herdr の invalid_agent_name）。
# タブ ID は "w5:t6" のように ':' を含むので、使えない文字は '-' に落とす。
name="explainer-$(printf '%s' "$tab_id" | tr 'A-Z' 'a-z' | tr -c 'a-z0-9_-' '-')"
name="${name:0:32}"

# フォーカス pane に main ラベルを付け、同タブの他 pane から main を外す（常に 1 つにする）
"$HERDR" pane rename "$pane" main >/dev/null 2>&1 || die "main ラベルの付与に失敗した"

tab_panes=$("$HERDR" pane list | jq -c --arg t "$tab_id" '.result.panes[] | select(.tab_id == $t)')

while IFS= read -r p; do
  [[ -n "$p" ]] || continue
  pid=$(jq -r '.pane_id' <<<"$p")
  [[ "$pid" != "$pane" ]] || continue
  [[ "$(jq -r '.label // ""' <<<"$p")" == "main" ]] || continue
  "$HERDR" pane rename "$pid" --clear >/dev/null 2>&1 || true
done <<<"$tab_panes"

# 同タブの explainer ラベル pane を探す（herdr のエージェント名は agent start 時にしか
# 付かないため、再利用の判定はラベルで行う）
explainer_pane=""
explainer_agent=""
while IFS= read -r p; do
  [[ -n "$p" ]] || continue
  if [[ "$(jq -r '.label // ""' <<<"$p")" == "explainer" ]]; then
    explainer_pane=$(jq -r '.pane_id' <<<"$p")
    explainer_agent=$(jq -r '.agent // ""' <<<"$p")
    break
  fi
done <<<"$tab_panes"

start_explainer() {
  # $1: 起動先 pane_id
  local target="$1" out
  for _ in $(seq 1 40); do
    if out=$("$HERDR" agent start "$name" --kind claude --pane "$target" --timeout 60000 \
      -- --agent explainer -n explainer 2>&1); then
      break
    fi
    grep -q "agent_pane_busy" <<<"$out" || die "explainer の起動に失敗した: $out"
    sleep 0.25
  done
  grep -q '"type":"agent_started"' <<<"${out:-}" || die "explainer が起動しなかった (pane=$target)"
}

if [[ -n "$explainer_pane" ]]; then
  if [[ "$explainer_agent" != "claude" ]]; then
    # ラベルは付いているが Claude が居ない（/exit 後など）。再起動する
    start_explainer "$explainer_pane"
  fi
  new="$explainer_pane"
else
  # 横長なら右、縦長なら下に割る。端末セルは幅が高さの約半分なので width/2 で比較する
  read -r w h < <("$HERDR" pane layout --pane "$pane" |
    jq -r --arg p "$pane" '.result.layout.panes[] | select(.pane_id == $p) | "\(.rect.width) \(.rect.height)"') || true
  if [[ -n "${w:-}" && -n "${h:-}" && $((w / 2)) -lt $h ]]; then dir=down; else dir=right; fi

  new=$("$HERDR" pane split --pane "$pane" --direction "$dir" --cwd "$cwd" --env "HERDR_MAIN_PANE_ID=$pane" --no-focus |
    jq -r '.result.pane.pane_id')
  [[ -n "$new" && "$new" != "null" ]] || die "explainer pane の分割に失敗した"

  # 起動に失敗したら作った pane を残さない
  die_pane() {
    "$HERDR" pane close "$new" >/dev/null 2>&1 || true
    die "$1"
  }

  for _ in $(seq 1 40); do
    if out=$("$HERDR" agent start "$name" --kind claude --pane "$new" --timeout 60000 \
      -- --agent explainer -n explainer 2>&1); then
      break
    fi
    grep -q "agent_pane_busy" <<<"$out" || die_pane "explainer の起動に失敗した: $out"
    sleep 0.25
  done
  grep -q '"type":"agent_started"' <<<"${out:-}" || die_pane "explainer が起動しなかった (pane=$new)"

  "$HERDR" pane rename "$new" explainer >/dev/null 2>&1 || true
fi

# explainer にそのまま質問できるようフォーカスを移す。名前 (name) はタブ毎に変わるので
# pane id ($new) で指定する（agent focus が pane id を受けるかは実機未確認）。
"$HERDR" agent focus "$new" >/dev/null 2>&1 || true

notify "explainer" "$new に常駐 (main は ${sid:0:8})" done
