#!/usr/bin/env bash
#
# Claude Code UserPromptSubmit hook: ワークフローグラフの現在地を 1 行注入する。
#
# タスクの台帳は <cwd>/.claude/workflow-graph/<task>/{decisions,verify,review}.json。
# 台帳が無ければ何も出さない（グラフを使っていない作業を邪魔しない）。
# 台帳があれば、どの SCC にいるか（review > verify > decisions の順で推定）と
# 「未確定 / 未pass / 未対応」の件数を additionalContext で main に見せる。
# main が規約を忘れても、抜ける条件の判定材料が毎ターン目に入るようにするのが目的。
# 設計は docs/adr/0019-workflow-graph-control-flow.md、規約は docs/design/workflow-graph.md。
#
# user/install.sh が hooks.UserPromptSubmit に登録し、~/.local/bin へ symlink する。
# ターンを妨げないことを最優先し、何が失敗しても exit 0 する。
#
set -euo pipefail

input="$(cat)"
cwd="$(printf '%s' "${input}" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -n "${cwd}" ] || cwd="${CLAUDE_PROJECT_DIR:-${PWD}}"

root="${cwd}/.claude/workflow-graph"
[ -d "${root}" ] || exit 0

# 複数タスクがあれば最近更新されたものを現在のタスクとみなす
task_dir="$(ls -td "${root}"/*/ 2>/dev/null | head -1 || true)"
[ -n "${task_dir}" ] || exit 0
task_dir="${task_dir%/}"
task="$(basename "${task_dir}")"

count() {
  # $1: ファイル, $2: jq フィルタ（件数を返す）。無ければ "-"
  if [ -f "$1" ]; then
    jq -r "$2" "$1" 2>/dev/null || printf '?'
  else
    printf -- '-'
  fi
}

decisions="${task_dir}/decisions.json"
verify="${task_dir}/verify.json"
review="${task_dir}/review.json"

if [ -f "${review}" ]; then scc="③ review"
elif [ -f "${verify}" ]; then scc="② build"
elif [ -f "${decisions}" ]; then scc="① deliberate"
else exit 0
fi

open="$(count "${decisions}" '.open // [] | length')"
fail="$(count "${verify}" '[(.items // [])[] | select(.result != "pass")] | length')"
review_open="$(count "${review}" '[(.items // [])[] | select(.status == "open")] | length')"

ctx="[workflow-graph] task=${task} scc=${scc} 未確定 ${open} / 未pass ${fail} / 未対応 ${review_open}。台帳: ${task_dir}（抜ける条件: 未確定 0 → record、全 pass → PR、未対応 0 → merge）"

jq -n --arg ctx "${ctx}" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $ctx}}'
exit 0
