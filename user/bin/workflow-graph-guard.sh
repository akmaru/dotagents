#!/usr/bin/env bash
#
# Claude Code PreToolUse hook (matcher: Bash): ワークフローグラフの「抜ける条件」を機械的に守る。
#
#   gh pr create … verify.json が全 pass でなければ拒否（② build を抜ける条件）
#   gh pr merge  … review.json に未対応（status: open）が残っていれば拒否（③ review を抜ける条件）
#
# 台帳（<cwd>/.claude/workflow-graph/<task>/）が無ければ何もしない。グラフを使っていない
# 作業には一切干渉しないことが、この hook を常設できる条件。
# 設計は docs/adr/0019-workflow-graph-control-flow.md、規約は docs/design/workflow-graph.md。
#
# user/install.sh が hooks.PreToolUse に登録し、~/.local/bin へ symlink する。
# 判定不能なときは通す（exit 0・出力なし）。止めるのは台帳が明確に「まだ」と言うときだけ。
#
set -euo pipefail

input="$(cat)"
tool="$(printf '%s' "${input}" | jq -r '.tool_name // empty' 2>/dev/null || true)"
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

deny() {
  jq -n --arg r "$1" '{hookSpecificOutput: {hookEventName: "PreToolUse", permissionDecision: "deny", permissionDecisionReason: $r}}'
  exit 0
}

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
