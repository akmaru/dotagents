#!/usr/bin/env bash
#
# Claude Code PreToolUse hook (matcher: Bash|Workflow): ワークフローグラフの規則を機械的に守る。
#
#   Workflow … うちの 4 本（deliberate / build / review / web-research）を args.models 無しで起動しようと
#              したら拒否する。models は「起動前にモデルを聞いた」ことの機械的な証拠（既定なら {}）。
#              同梱の deep-research は model を固定できないので、web-research に誘導して拒否する。
#   gh pr create … verify.json が全 pass でなければ拒否（② build を抜ける条件）
#   gh pr merge  … review.json に未対応（status: open）が残っていれば拒否（③ review を抜ける条件）
#
# Bash 側は台帳（<cwd>/.claude/workflow-graph/<task>/）が無ければ何もしない。グラフを使っていない
# 作業には一切干渉しないことが、この hook を常設できる条件。
# 設計は docs/adr/0020-workflow-graph-control-flow.md、規約は docs/design/workflow-graph.md。
#
# user/install.sh が hooks.PreToolUse に登録し、~/.local/bin へ symlink する。
# 判定不能なときは通す（exit 0・出力なし）。止めるのは規則が明確に「まだ」と言うときだけ。
#
set -euo pipefail

input="$(cat)"
tool="$(printf '%s' "${input}" | jq -r '.tool_name // empty' 2>/dev/null || true)"

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
  exit 0
}

# ---- Workflow の起動 --------------------------------------------------------
if [ "${tool}" = "Workflow" ]; then
  name="$(printf '%s' "${input}" | jq -r '.tool_input.name // empty' 2>/dev/null || true)"
  if [ -z "${name}" ]; then
    # name 解決に失敗して scriptPath で起動する経路も同じ規則
    script="$(printf '%s' "${input}" | jq -r '.tool_input.scriptPath // empty' 2>/dev/null || true)"
    name="$(basename "${script}" .js)"
  fi
  case "${name}" in
    deep-research)
      deny "[workflow-graph] 同梱の /deep-research は model を固定できず、セッションのモデルで 100 体前後が回る。/web-research（段階ごとに model を固定した写し）を args {question, models} で使う"
      ;;
    deliberate|build|review|web-research)
      has_models="$(printf '%s' "${input}" | jq -r '.tool_input.args | if type == "object" and (.models | type) == "object" then "yes" else "no" end' 2>/dev/null || printf 'no')"
      if [ "${has_models}" != "yes" ]; then
        deny "[workflow-graph] /${name} は起動の直前に AskUserQuestion でノードごとのモデルを聞き、その答えを args.models（既定のままなら {}）に渡してから起動する。args は object にする（web-research も {question, models}）"
      fi
      ;;
  esac
  exit 0
fi

# ---- Bash: PR と merge ------------------------------------------------------
[ "${tool}" = "Bash" ] || exit 0

cmd="$(printf '%s' "${input}" | jq -r '.tool_input.command // empty' 2>/dev/null || true)"
case "${cmd}" in
  *"gh pr create"*) kind="create" ;;
  *"gh pr merge"*)  kind="merge" ;;
  *) exit 0 ;;
esac

cwd="$(printf '%s' "${input}" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -n "${cwd}" ] || cwd="${CLAUDE_PROJECT_DIR:-${PWD}}"
root="${cwd}/.claude/workflow-graph"
[ -d "${root}" ] || exit 0
task_dir="$(ls -td "${root}"/*/ 2>/dev/null | head -1 || true)"
[ -n "${task_dir}" ] || exit 0
task_dir="${task_dir%/}"

case "${kind}" in
  create)
    verify="${task_dir}/verify.json"
    [ -f "${verify}" ] || deny "[workflow-graph] ${verify} が無い。/build を実行して全 pass にしてから PR を作る（② build を抜ける条件）"
    failing="$(jq -r '[(.items // [])[] | select(.result != "pass") | .name] | join(", ")' "${verify}" 2>/dev/null || printf '?')"
    if [ -n "${failing}" ]; then
      deny "[workflow-graph] verify.json に fail / 未実行の項目が残っている: ${failing}。全 pass にしてから PR を作る（② build を抜ける条件）"
    fi
    ;;
  merge)
    review="${task_dir}/review.json"
    [ -f "${review}" ] || deny "[workflow-graph] ${review} が無い。/review を実行し、人間のレビューを経てから merge する（③ review を抜ける条件）"
    open_n="$(jq -r '[(.items // [])[] | select(.status == "open")] | length' "${review}" 2>/dev/null || printf '?')"
    if [ "${open_n}" != "0" ]; then
      deny "[workflow-graph] review.json に未対応の指摘が ${open_n} 件ある。対応（fixed）か棚上げ（deferred）か却下（rejected）にしてから merge する（③ review を抜ける条件）"
    fi
    ;;
esac
exit 0
