#!/usr/bin/env bash
#
# Claude Code SessionEnd hook: セッションの会話テキストを Hindsight に投入する。
#
# transcript のうち user / assistant の text ブロックだけを抜き出して投げる。
# tool_result・thinking・attachment は落とす（実測で transcript の 97% 以上を占め、
# 記憶としての価値がないうえ投入量に比例して抽出コストと識別子破損が増えるため)。
# 要約はサーバー側の retain 抽出に任せる。設計は docs/adr/0017-session-end-retain-hook.md。
#
# user/settings.json の hooks.SessionEnd から参照され、user/install.sh が ~/.local/bin へ symlink する。
#
# セッション終了を妨げないことを最優先し、何が失敗しても exit 0 する。
# 経緯は ${XDG_STATE_HOME:-~/.local/state}/hindsight-retain/log に残す。
#
# HINDSIGHT_RETAIN_DRY_RUN=1 を立てると POST せずにペイロードを stdout に出す。
#
set -euo pipefail

HINDSIGHT_BANK="${HINDSIGHT_BANK:-personal}"
HINDSIGHT_API_URL="${HINDSIGHT_API_URL:-https://hindsight.akmaru.dev}"

# これ未満の会話しかないセッションは投げない。挨拶や打ち間違いだけで
# サーバー側の抽出 LLM を焚かないための足切り。
HINDSIGHT_RETAIN_MIN_BYTES="${HINDSIGHT_RETAIN_MIN_BYTES:-500}"

STATE_DIR="${XDG_STATE_HOME:-${HOME}/.local/state}/hindsight-retain"
LOG="${STATE_DIR}/log"

log() {
  mkdir -p "${STATE_DIR}" 2>/dev/null || return 0
  printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >>"${LOG}" 2>/dev/null || true
}

# symlink 越しに実行されるので、実体の場所からリポジトリルートを求める（api-key.sh を source するため）
src="${BASH_SOURCE[0]}"
while [ -L "${src}" ]; do
  dir="$(cd -P "$(dirname "${src}")" && pwd)"
  src="$(readlink "${src}")"
  [[ "${src}" != /* ]] && src="${dir}/${src}"
done
ROOT_DIR="$(cd -P "$(dirname "${src}")/../.." && pwd)"

command -v jq >/dev/null 2>&1 || { log "skip: jq がない"; exit 0; }

input="$(cat)"
transcript="$(printf '%s' "${input}" | jq -r '.transcript_path // empty' 2>/dev/null || true)"
session_id="$(printf '%s' "${input}" | jq -r '.session_id // empty' 2>/dev/null || true)"
cwd="$(printf '%s' "${input}" | jq -r '.cwd // empty' 2>/dev/null || true)"

[[ -n "${transcript}" && -r "${transcript}" ]] || { log "skip: transcript が読めない (${transcript:-未指定})"; exit 0; }

# 会話の地の文だけを取り出す。user の content は文字列のこともある。
#
# 文字列の user メッセージには、ユーザーが `!` で実行したコマンドの出力が
# <bash-stdout> などのタグで混ざる。これは「ツール出力の生ログ」そのもので、
# `aws ssm get-parameter --with-decryption` のような出力が入りうるため落とす。
# 打ったコマンド自体 (<bash-input>) は短く文脈として役立つので残す。
conversation="$(
  jq -r '
    def strip_harness:
      reduce (
        "local-command-caveat", "local-command-stdout", "local-command-stderr",
        "bash-stdout", "bash-stderr", "command-name", "command-message", "command-args"
      ) as $tag (.; gsub("(?s)<" + $tag + ">.*?</" + $tag + ">"; ""));

    select(.type == "user" or .type == "assistant")
    | .message.content
    | if type == "string" then .
      else (.[]? | select(.type == "text") | .text)
      end
    | strip_harness
    | gsub("^\\s+|\\s+$"; "")
    | select(. != "")
  ' "${transcript}" 2>/dev/null || true
)"

size="$(printf '%s' "${conversation}" | wc -c | tr -d ' ')"
if [[ "${size}" -lt "${HINDSIGHT_RETAIN_MIN_BYTES}" ]]; then
  log "skip: 会話が ${size} B しかない (閾値 ${HINDSIGHT_RETAIN_MIN_BYTES} B)"
  exit 0
fi

project="$(basename "${cwd:-unknown}")"
# SessionEnd は clear / resume / logout などで 1 セッション中に複数回発火しうる。
# document_id を session_id に固定すると、update_mode の既定 replace が
# 同じ文書を入れ替えるので再発火が冪等になる。
document_id="${session_id:-unknown-$(date -u +%Y%m%dT%H%M%SZ)}"

payload="$(
  jq -n \
    --arg content "${conversation}" \
    --arg context "Claude Code セッション (${project})" \
    --arg document_id "${document_id}" \
    --arg timestamp "$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
    --arg project_tag "project:${project}" \
    '{
       items: [{
         content: $content,
         context: $context,
         document_id: $document_id,
         timestamp: $timestamp,
         tags: [$project_tag, "source:session-hook"]
       }],
       async: true
     }'
)"

if [[ -n "${HINDSIGHT_RETAIN_DRY_RUN:-}" ]]; then
  printf '%s\n' "${payload}"
  log "dry-run: ${project} ${size} B"
  exit 0
fi

# shellcheck source=../../hindsight/api-key.sh
if [[ -r "${ROOT_DIR}/hindsight/api-key.sh" ]]; then
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/hindsight/api-key.sh"
else
  log "skip: api-key.sh が ${ROOT_DIR}/hindsight に無い"
  exit 0
fi

key="$(hindsight_mcp_api_key || true)"
[[ -n "${key}" ]] || { log "skip: API キーが無い"; exit 0; }

response="$(
  curl -sS --max-time 5 \
    -X POST "${HINDSIGHT_API_URL}/v1/default/banks/${HINDSIGHT_BANK}/memories" \
    -H "Authorization: Bearer ${key}" \
    -H "Content-Type: application/json" \
    -d "${payload}" 2>&1
)" || { log "fail: ${project} ${size} B -> ${response}"; exit 0; }

log "ok: ${project} ${size} B doc=${document_id} -> ${response}"
exit 0
