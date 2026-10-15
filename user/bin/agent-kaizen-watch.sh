#!/usr/bin/env bash
#
# kaizen 専用セッションが、自分の Issue を見張る（docs/adr/0030）。Monitor ツールで起動する想定で、
# ユーザーの番になった（または終わった）ときだけ stdout に 1 行出す。
#
#   agent-kaizen-watch.sh <Issue 番号>
#
# ユーザーの番:
#   - 改善ループのエージェントが Issue に書いて止まった（質問、または PR を出せずに止まった）
#   - PR が出た（レビューと merge はユーザーの番）
# 終わり（出力して終了する）: PR が merge された / Issue が閉じられた
#
# 環境変数: AGENT_KAIZEN_REPO（既定 akmaru/dotagents）、AGENT_KAIZEN_INTERVAL（秒、既定 60）、
#          AGENT_KAIZEN_ONCE=1（1 回だけ確かめて終わる。テスト用）
#
set -uo pipefail

issue="${1:-}"
[[ "${issue}" =~ ^[0-9]+$ ]] || { echo "usage: agent-kaizen-watch.sh <issue number>" >&2; exit 2; }
repo="${AGENT_KAIZEN_REPO:-akmaru/dotagents}"
interval="${AGENT_KAIZEN_INTERVAL:-60}"
tag="[agent-kaizen #${issue}]"

command -v gh >/dev/null 2>&1 || { echo "${tag} gh が無い" >&2; exit 1; }
command -v jq >/dev/null 2>&1 || { echo "${tag} jq が無い" >&2; exit 1; }

# 状態を 1 行の JSON にする: {kind, key, text}
#   kind: waiting（エージェントの番）/ ask / pr / merged / closed
classify() {
  jq -cn --argjson i "$1" --argjson p "$2" --arg n "${issue}" '
    ($p | map(select(.headRefName | startswith("claude/issue-" + $n + "-")))) as $prs
    | ($prs | map(select(.state == "MERGED")) | first) as $merged
    | ($prs | map(select(.state == "OPEN")) | first) as $open
    | ($i.comments | last) as $last
    | if $merged != null then
        {kind: "merged", key: "merged", text: ("PR #\($merged.number) が merge された: \($merged.url)")}
      elif $open != null then
        {kind: "pr", key: "pr\($open.number)", text: ("PR #\($open.number) が出た。試して approve するか、直してほしい点を伝える番: \($open.url)")}
      elif $i.state == "CLOSED" then
        {kind: "closed", key: "closed", text: "Issue が閉じられた"}
      elif $last == null then {kind: "waiting", key: "", text: ""}
      elif ($last.author.login | test("^claude(\\[bot\\])?$")) | not then {kind: "waiting", key: "", text: ""}
      elif ($last.body | test("is working|5ac382c7-e004-429b-8e35-7feb3e8f9c6f")) then {kind: "waiting", key: "", text: ""}
      else
        {kind: "ask", key: "ask\($last.id)-\($last.body | length)",
         text: ("エージェントが Issue に書いて止まった。答える番: \($last.url)\n" + ($last.body | .[0:1500]))}
      end'
}

last_key=""
while true; do
  issue_json="$(gh issue view "${issue}" --repo "${repo}" --json state,comments 2>/dev/null)" || issue_json=""
  prs_json="$(gh pr list --repo "${repo}" --state all --limit 100 --json number,headRefName,state,url 2>/dev/null)" || prs_json=""
  if [ -n "${issue_json}" ] && [ -n "${prs_json}" ]; then
    verdict="$(classify "${issue_json}" "${prs_json}")"
    kind="$(jq -r .kind <<<"${verdict}")"
    key="$(jq -r .key <<<"${verdict}")"
    if [ "${kind}" != waiting ] && [ "${key}" != "${last_key}" ]; then
      printf '%s %s\n' "${tag}" "$(jq -r .text <<<"${verdict}")"
      last_key="${key}"
    fi
    case "${kind}" in merged | closed) exit 0 ;; esac
  fi
  [ "${AGENT_KAIZEN_ONCE:-}" = 1 ] && exit 0
  sleep "${interval}"
done
