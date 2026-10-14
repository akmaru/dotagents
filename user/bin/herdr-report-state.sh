#!/usr/bin/env bash
#
# Claude Code hook: セッションが「ユーザーの回答待ち」かどうかを herdr に報告する。
#
#   herdr-report-state.sh blocked   AskUserQuestion の実行前・権限確認などの通知で呼ぶ
#   herdr-report-state.sh working   ツールが完了したら呼ぶ（回答が済んだ印）
#
# herdr が Claude Code に入れる hook は SessionStart だけで、回答待ちは通知されない。
# `herdr pane report-agent --state blocked` で pane を blocked にすると、attention 順の並び
# （agent_panel_sort = "priority"）と next_agent で拾える。設計は docs/adr/0030。
#
# herdr が生成するスクリプトは再インストールで上書きされるので、別ファイルとして持つ。
# working は blocked を送った pane にだけ返す（ツールごとに呼ばれるので、印のファイルで足切りする）。
# セッションを妨げないことを最優先し、何が失敗しても exit 0 する。
#
set -uo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"
state="${1:-}"
pane="${HERDR_PANE_ID:-}"

cat >/dev/null 2>&1 || true  # hook の入力は使わない

case "${state}" in blocked | working) ;; *) exit 0 ;; esac
[ -n "${pane}" ] || exit 0  # herdr の外で動いているセッション

mark_dir="${XDG_STATE_HOME:-${HOME}/.local/state}/herdr-report-state"
mark="${mark_dir}/${pane//\//_}"

if [ "${state}" = working ]; then
  [ -e "${mark}" ] || exit 0
  rm -f "${mark}"
else
  mkdir -p "${mark_dir}" 2>/dev/null && : >"${mark}" 2>/dev/null
fi

# source は herdr 自身の hook（herdr-agent-state.sh）と同じ値にする
"${HERDR}" pane report-agent --source herdr:claude --agent claude --state "${state}" "${pane}" >/dev/null 2>&1 || true
exit 0
