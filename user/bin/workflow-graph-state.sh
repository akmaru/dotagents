#!/usr/bin/env bash
#
# Claude Code UserPromptSubmit hook: ワークフローグラフの規約と現在地を main に見せる。
#
# 1. 規約の注入: プロンプトに /deliberate /build /review /web-research のどれかが含まれていたら、
#    workflow-graph skill の本文（frontmatter を除いた SKILL.md）を additionalContext で注入する。
#    ユーザーが skill を先に叩かなくても、skill を install していなくても、コマンドを打った時点で
#    規約（起動前にモデルを聞く、台帳の書き方、人間ノードの手順）が載る。
#    毎ターン積むとコンテキストを食うので、session_id ごとに 1 回だけ。
# 2. 現在地の注入: タスクの台帳（<cwd>/.claude/workflow-graph/<task>/{decisions,verify,review}.json）が
#    あれば、どの SCC にいるか（review > verify > decisions の順で推定）と「未確定 / 未pass / 未対応」の
#    件数を 1 行で注入する。台帳が無ければ出さない（グラフを使っていない作業を邪魔しない）。
#
# 設計は docs/adr/0020-workflow-graph-control-flow.md、規約は docs/design/workflow-graph.md。
# user/install.sh が hooks.UserPromptSubmit に登録し、~/.local/bin へ symlink する。
# ターンを妨げないことを最優先し、何が失敗しても exit 0 する。
#
set -euo pipefail

input="$(cat)"
cwd="$(printf '%s' "${input}" | jq -r '.cwd // empty' 2>/dev/null || true)"
[ -n "${cwd}" ] || cwd="${CLAUDE_PROJECT_DIR:-${PWD}}"
prompt="$(printf '%s' "${input}" | jq -r '.prompt // empty' 2>/dev/null || true)"
session="$(printf '%s' "${input}" | jq -r '.session_id // empty' 2>/dev/null || true)"

# symlink 越しに実行されるので、実体の場所からリポジトリルートを求める（skill 本文を読むため）
src="${BASH_SOURCE[0]}"
while [ -L "${src}" ]; do
  dir="$(cd -P "$(dirname "${src}")" && pwd)"
  src="$(readlink "${src}")"
  [[ "${src}" != /* ]] && src="${dir}/${src}"
done
repo_root="$(cd -P "$(dirname "${src}")/../.." && pwd)"
skill_md="${WORKFLOW_GRAPH_SKILL:-${repo_root}/packages/workflow-graph/.apm/skills/workflow-graph/SKILL.md}"

parts=()

# ---- 1. 規約の注入（コマンドを打ったターン、セッションにつき 1 回） ----
if printf '%s' "${prompt}" | grep -qE '(^|[^[:alnum:]/])/(deliberate|build|review|web-research)([^[:alnum:]-]|$)'; then
  marker_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/workflow-graph/injected"
  marker="${marker_dir}/${session:-no-session}"
  if [ ! -e "${marker}" ] && [ -f "${skill_md}" ]; then
    # frontmatter（先頭の --- ... ---）を落として本文だけ
    body="$(awk 'BEGIN{n=0} /^---$/ && n<2 {n++; next} n>=2 {print}' "${skill_md}")"
    parts+=("[workflow-graph] 以下はワークフローグラフの規約（workflow-graph skill の本文）。/deliberate /build /review /web-research を呼ぶ前にこれに従う。特に「起動前にモデルを聞く」は必須で、聞かずに起動すると hook が拒否する。

${body}")
    if [ -n "${session}" ]; then
      mkdir -p "${marker_dir}" 2>/dev/null && : > "${marker}" 2>/dev/null || true
    fi
  fi
fi

# ---- 2. 現在地の注入（台帳があるときだけ） ----
root="${cwd}/.claude/workflow-graph"
if [ -d "${root}" ]; then
  # 複数タスクがあれば最近更新されたものを現在のタスクとみなす
  task_dir="$(ls -td "${root}"/*/ 2>/dev/null | head -1 || true)"
  if [ -n "${task_dir}" ]; then
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
    scc=""
    if [ -f "${review}" ]; then scc="③ review"
    elif [ -f "${verify}" ]; then scc="② build"
    elif [ -f "${decisions}" ]; then scc="① deliberate"
    fi
    if [ -n "${scc}" ]; then
      open="$(count "${decisions}" '.open // [] | length')"
      fail="$(count "${verify}" '[(.items // [])[] | select(.result != "pass")] | length')"
      review_open="$(count "${review}" '[(.items // [])[] | select(.status == "open")] | length')"
      parts+=("[workflow-graph] task=${task} scc=${scc} 未確定 ${open} / 未pass ${fail} / 未対応 ${review_open}。台帳: ${task_dir}（抜ける条件: 未確定 0 → record、全 pass → PR、未対応 0 → merge）")
    fi
  fi
fi

[ "${#parts[@]}" -gt 0 ] || exit 0
ctx="$(printf '%s\n\n' "${parts[@]}")"
jq -n --arg ctx "${ctx}" '{hookSpecificOutput: {hookEventName: "UserPromptSubmit", additionalContext: $ctx}}'
exit 0
