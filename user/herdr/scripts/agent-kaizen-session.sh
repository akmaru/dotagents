#!/usr/bin/env bash
#
# agent-kaizen の Issue 1 件を担当する専用の Claude Code セッションを、隣の pane に立ち上げる（docs/adr/0030）。
# 専用セッションは Issue を見張り、ユーザーの番になると質問を表示し、答えの投稿を受け持つ。
# agent-kaizen スキルが起票した直後に呼ぶ。元のセッションはフォーカスを奪われず、今の作業に戻る。
#
#   agent-kaizen-session.sh <Issue 番号>
#
set -euo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"
issue="${1:-}"
[[ "${issue}" =~ ^[0-9]+$ ]] || { echo "usage: agent-kaizen-session.sh <issue number>" >&2; exit 2; }

pane="${HERDR_PANE_ID:-${HERDR_ACTIVE_PANE_ID:-}}"
[[ -n "${pane}" ]] || { echo "herdr の pane の中で実行してください (HERDR_PANE_ID が無い)" >&2; exit 1; }

name="kaizen-${issue}"
if "${HERDR}" agent list | jq -e --arg n "${name}" '.result.agents[] | select(.name == $n)' >/dev/null 2>&1; then
  echo "${name} は既に動いている" >&2
  exit 0
fi

new=$("${HERDR}" pane split --pane "${pane}" --direction right --cwd "${PWD}" --no-focus |
  jq -r '.result.pane.pane_id')
[[ -n "${new}" && "${new}" != "null" ]] || { echo "pane の分割に失敗した" >&2; exit 1; }

fail() {
  "${HERDR}" pane close "${new}" >/dev/null 2>&1 || true
  echo "$1" >&2
  exit 1
}

prompt="agent-kaizen スキルの「専用セッション」の節に従い、akmaru/dotagents の Issue #${issue} を担当してください。"

# 分割直後の pane はシェルがまだプロンプトに達しておらず agent_pane_busy になる
for _ in $(seq 1 40); do
  if out=$("${HERDR}" agent start "${name}" --kind claude --pane "${new}" --timeout 60000 -- "${prompt}" 2>&1); then
    break
  fi
  grep -q "agent_pane_busy" <<<"${out}" || fail "起動に失敗した: ${out}"
  sleep 0.25
done
grep -q '"type":"agent_started"' <<<"${out:-}" || fail "起動しなかった (pane=${new})"
echo "${name} を ${new} に立ち上げた"
