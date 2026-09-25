#!/usr/bin/env bash
#
# メインセッションのトランスクリプト (JSONL) を直近のやり取りに整形して出力する。
# explainer (user/agents/explainer.md) が質問のたびに呼び、メインの現在の状態を読む。
# 機構と選別規則は docs/design/explainer-pane.md「整形スクリプト claude-main-digest.sh の仕様」。
#
# メイン pane の特定は --pane を指定しなければ herdr 経由で行う（同ドキュメントの解決順）。
# --file はテストと herdr の無い環境向けに、対象の JSONL を直接指定する。
#
set -euo pipefail

HERDR="${HERDR_BIN_PATH:-herdr}"

# keybinding 経由の起動やフック環境は login shell を経由せず jq が PATH に無いことがある
command -v jq >/dev/null 2>&1 || PATH="${HOME}/.local/share/mise/shims:/opt/homebrew/bin:/usr/local/bin:${PATH}"

usage() {
  cat >&2 <<'EOF'
usage: claude-main-digest.sh [--pane ID | --file JSONL] [--turns N] [--since UUID]
                              [--with-results] [--max-chars N] [--resolve-only]
EOF
}

pane_arg=""
file_arg=""
turns=6
since_uuid=""
with_results=0
max_chars=12000
resolve_only=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --pane) pane_arg="${2:?--pane requires a value}"; shift 2 ;;
    --file) file_arg="${2:?--file requires a value}"; shift 2 ;;
    --turns) turns="${2:?--turns requires a value}"; shift 2 ;;
    --since) since_uuid="${2:?--since requires a value}"; shift 2 ;;
    --with-results) with_results=1; shift ;;
    --max-chars) max_chars="${2:?--max-chars requires a value}"; shift 2 ;;
    --resolve-only) resolve_only=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown option: $1" >&2; usage; exit 1 ;;
  esac
done

command -v jq >/dev/null 2>&1 || { echo "jq が見つからない" >&2; exit 1; }

# --- メイン pane の特定（--file が無いとき） ------------------------------
#
# 解決順（docs/design/explainer-pane.md 準拠）:
#   1. --pane（手動指定）
#   2. --file（呼び出し元でチェック済みなのでここには来ない）
#   3. 現在のタブで label == "main" の pane
#   4. HERDR_MAIN_PANE_ID（pane が存在し agent == "claude" のとき）
#   5. 同タブで agent == "claude" かつ自分以外の pane がちょうど 1 つ
#   6. 失敗: exit 2。stderr に候補を出す
resolve_main_pane() {
  local self="${HERDR_PANE_ID:-}"
  local self_info tab_id panes candidate

  if [[ -n "${self}" ]]; then
    self_info=$("$HERDR" pane get "${self}" 2>/dev/null || true)
    tab_id=$(jq -r '.result.pane.tab_id // empty' <<<"${self_info}")
  fi

  if [[ -n "${tab_id:-}" ]]; then
    panes=$("$HERDR" pane list 2>/dev/null | jq -c --arg t "${tab_id}" '.result.panes[]? | select(.tab_id == $t)')
    candidate=$(jq -r 'select(.label == "main") | .pane_id' <<<"${panes}" | head -1)
    if [[ -n "${candidate}" ]]; then
      printf '%s\n' "${candidate}"
      return 0
    fi
  fi

  if [[ -n "${HERDR_MAIN_PANE_ID:-}" ]]; then
    local info agent
    info=$("$HERDR" pane get "${HERDR_MAIN_PANE_ID}" 2>/dev/null || true)
    agent=$(jq -r '.result.pane.agent // empty' <<<"${info}")
    if [[ "${agent}" == "claude" ]]; then
      printf '%s\n' "${HERDR_MAIN_PANE_ID}"
      return 0
    fi
  fi

  if [[ -n "${panes:-}" ]]; then
    local claude_panes count
    claude_panes=$(jq -r --arg self "${self}" 'select(.agent == "claude") | select(.pane_id != $self) | .pane_id' <<<"${panes}")
    count=$(printf '%s\n' "${claude_panes}" | grep -c . || true)
    if [[ "${count}" -eq 1 ]]; then
      printf '%s\n' "${claude_panes}"
      return 0
    fi
  fi

  {
    echo "メイン pane を特定できない。候補:"
    if [[ -n "${panes:-}" ]]; then
      jq -r '"  " + .pane_id + " label=" + (.label // "-") + " title=" + (.terminal_title_stripped // "-") + " status=" + (.agent_status // "-")' <<<"${panes}"
    fi
    echo "--pane <id> で明示するか、対象 pane に main ラベルを付けてください"
  } >&2
  return 1
}

if [[ -z "${file_arg}" ]]; then
  pane="${pane_arg}"
  if [[ -z "${pane}" ]]; then
    pane=$(resolve_main_pane) || exit 2
  fi

  info=$("$HERDR" pane get "${pane}") || { echo "pane get に失敗した (${pane})" >&2; exit 2; }
  agent=$(jq -r '.result.pane.agent // ""' <<<"${info}")
  status=$(jq -r '.result.pane.agent_status // ""' <<<"${info}")
  if [[ "${agent}" != "claude" || "${status}" == "unknown" ]]; then
    echo "メイン pane に Claude Code が居ない (agent=${agent:-none} status=${status:-none})" >&2
    exit 3
  fi

  session_id=$(jq -r '.result.pane.agent_session | if .kind == "id" then .value else "" end' <<<"${info}")
  cwd=$(jq -r '.result.pane.foreground_cwd // .result.pane.cwd // ""' <<<"${info}")
  claude_root="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
  transcript=$(find "${claude_root}/projects" -maxdepth 2 -name "${session_id}.jsonl" -print -quit 2>/dev/null || true)
  if [[ -z "${transcript}" ]]; then
    echo "トランスクリプトが見つからない (session ${session_id})" >&2
    exit 4
  fi
  pane_desc="${pane}"
  session_short="${session_id:0:8}"
  claude_version=$(claude --version 2>/dev/null | head -1 || true)
else
  transcript="${file_arg}"
  pane_desc="file:${file_arg}"
  session_short=""
  cwd=""
  claude_version=""
fi

[[ -r "${transcript}" ]] || { echo "トランスクリプトを読めない: ${transcript}" >&2; exit 4; }

# --- 行単位のパース ---------------------------------------------------------
#
# 書き込み中の末尾不完全行や壊れた行は捨て、捨てた件数をヘッダに出す。
raw_total=$(jq -R -c 'select(length > 0)' "${transcript}" | wc -l | tr -d ' ')

parsed_stream=$(jq -R -c 'select(length > 0) | (try fromjson catch {"__parse_error__": true})' "${transcript}")

valid_count=$(printf '%s\n' "${parsed_stream}" | jq -s '[.[] | select(.__parse_error__ != true)] | length')
dropped=$((raw_total - valid_count))

if [[ "${valid_count}" -eq 0 ]]; then
  if [[ "${raw_total}" -eq 0 ]]; then
    echo "# main: pane ${pane_desc}$( [[ -n "${session_short}" ]] && echo " · session ${session_short}")$( [[ -n "${cwd}" ]] && echo " · cwd ${cwd}") · entries 0/0"
    exit 0
  fi
  echo "トランスクリプトの形式が変わった疑いがある (有効行 0/${raw_total})" >&2
  exit 5
fi

# --- 選別・束ね（jq）--------------------------------------------------------
#
# isSidechain / isMeta / attachment・system 行を除外し、user のターンと
# assistant の応答（message.id で束ねる）だけを entries として組み立てる。
entries_json=$(jq -n -c --argjson with_results "${with_results}" '
  def strip_harness:
    reduce (
      "local-command-caveat", "local-command-stdout", "local-command-stderr",
      "bash-stdout", "bash-stderr", "command-name", "command-message", "command-args"
    ) as $tag (.; gsub("(?s)<" + $tag + ">.*?</" + $tag + ">"; ""));

  def text_of($content):
    if ($content | type) == "string" then $content
    else ([$content[]? | select(.type == "text") | .text] | join("\n"))
    end;

  [inputs] as $rows
  | ($rows | map(select(.__parse_error__ != true))) as $valid
  | ($valid | if length > 0 then .[-1].uuid // "" else "" end) as $last_uuid
  | (
      [ $valid[]
        | select((.isSidechain // false) | not)
        | select((.isMeta // false) | not)
        | select(.type == "user" or .type == "assistant")
        | (.message.content) as $content
        | if .type == "user" then
            if (($content | type) == "array") and ([$content[]? | select(.type == "tool_result")] | length) > 0 then
              (
                if $with_results == 1 then
                  {kind: "result", uuid: (.uuid // ""), ts: ((.timestamp // "")[11:16]),
                   text: ([$content[]? | select(.type == "tool_result") | (.content | if type == "string" then . else tojson end)] | join("\n") | .[0:300])}
                else empty end
              )
            elif (($content | type) == "string") and (($content | test("^<local-command")) or ($content | test("<command-name>"))) then
              empty
            else
              {kind: "user", uuid: (.uuid // ""), ts: ((.timestamp // "")[11:16]), text: (text_of($content) | strip_harness)}
            end
          else
            {kind: "assistant_block", uuid: (.uuid // ""), ts: ((.timestamp // "")[11:16]),
             mid: (.message.id // .uuid // ""), blocks: $content}
          end
      ]
    ) as $items
  | (reduce $items[] as $it (
      [];
      if $it.kind == "assistant_block" then
        if (length > 0) and (.[-1].kind == "assistant") and (.[-1].mid == $it.mid) then
          (.[0:-1] + [ (.[-1] + {blocks: (.[-1].blocks + $it.blocks), uuid: $it.uuid}) ])
        else
          . + [ {kind: "assistant", mid: $it.mid, uuid: $it.uuid, ts: $it.ts, blocks: $it.blocks} ]
        end
      else
        . + [$it]
      end
    )) as $merged
  | ($merged | map(
      if .kind == "assistant" then
        {
          kind, uuid, ts,
          text: (
            [ .blocks[]? | select(.type == "text") | .text ]
            | join("\n") | strip_harness | .[0:2000]
          ),
          tool_lines: (
            [ .blocks[]?
              | select(.type == "tool_use")
              | "- tool " + (.name // "?") + ": " + (
                  ((.input // {}) | to_entries | if length > 0 then (.[0].value | if type == "string" then . else tojson end) else "" end)
                  | strip_harness | .[0:160]
                )
            ]
          )
        }
      else . end
    )) as $final
  | {entries: $final, last_uuid: $last_uuid}
' <<<"${parsed_stream}")

total=$(jq '.entries | length' <<<"${entries_json}")
last_uuid=$(jq -r '.last_uuid' <<<"${entries_json}")

# --- 窓の選択（--since / --turns）------------------------------------------
start_index=0
since_warning=""
if [[ -n "${since_uuid}" ]]; then
  found_index=$(jq --arg u "${since_uuid}" '[.entries[] | .uuid] | index($u)' <<<"${entries_json}")
  if [[ "${found_index}" != "null" ]]; then
    start_index=$((found_index + 1))
  else
    since_warning="--since ${since_uuid} が見つからない。既定の窓に戻す"
  fi
fi

if [[ -z "${since_uuid}" || -n "${since_warning}" ]]; then
  # 直近 N 個のユーザーターンから末尾まで
  user_start=$(jq --argjson n "${turns}" '
    [.entries | to_entries[] | select(.value.kind == "user") | .key] as $u
    | if ($u | length) <= $n then 0
      else $u[-$n]
      end
  ' <<<"${entries_json}")
  start_index="${user_start}"
fi

if [[ -n "${since_warning}" ]]; then
  echo "${since_warning}" >&2
fi

# --- resolve-only: ヘッダ 1 行だけ ------------------------------------------
header() {
  local range="$1" note="$2"
  local out="# main: pane ${pane_desc}"
  [[ -n "${session_short}" ]] && out+=" · session ${session_short}"
  [[ -n "${cwd}" ]] && out+=" · cwd ${cwd}"
  out+=" · entries ${range}"
  [[ -n "${claude_version}" ]] && out+=" · claude ${claude_version}"
  [[ -n "${note}" ]] && out+=" · ${note}"
  printf '%s\n' "${out}"
}

if [[ "${resolve_only}" -eq 1 ]]; then
  header "${total}/${total}" ""
  exit 0
fi

# --- 窓を書式化し、max-chars を超えたら古い側から落とす --------------------
format_entry() {
  jq -r '
    if .kind == "user" then "## " + .ts + " user\n" + .text
    elif .kind == "result" then "## " + .ts + " result\n" + .text
    else
      "## " + .ts + " assistant"
      + (if .text != "" then "\n" + .text else "" end)
      + (if (.tool_lines | length) > 0 then "\n" + (.tool_lines | join("\n")) else "" end)
    end
  '
}

window_json=$(jq -c --argjson s "${start_index}" '.entries[$s:]' <<<"${entries_json}")

dropped_for_chars=0
while :; do
  body=$(jq -c '.[]' <<<"${window_json}" | while IFS= read -r e; do format_entry <<<"$e"; echo; done)
  body_len=${#body}
  if [[ "${body_len}" -le "${max_chars}" || $(jq 'length' <<<"${window_json}") -le 1 ]]; then
    break
  fi
  window_json=$(jq -c '.[1:]' <<<"${window_json}")
  dropped_for_chars=$((dropped_for_chars + 1))
done

final_count=$(jq 'length' <<<"${window_json}")
if [[ "${total}" -eq 0 ]]; then
  range="0/0"
else
  final_start=$((total - final_count))
  range="$((final_start + 1))–${total}/${total}"
fi

note=""
[[ "${dropped}" -gt 0 ]] && note="dropped ${dropped}"
if [[ "${dropped_for_chars}" -gt 0 ]]; then
  trunc_note="(truncated: ${dropped_for_chars} entries dropped)"
  note=$( [[ -n "${note}" ]] && printf '%s · %s' "${note}" "${trunc_note}" || printf '%s' "${trunc_note}" )
fi

header "${range}" "${note}"
printf '%s\n' "${body}"

if [[ "${final_count}" -gt 0 ]]; then
  cursor_uuid=$(jq -r '.[-1].uuid' <<<"${window_json}")
else
  cursor_uuid="${last_uuid}"
fi
printf 'cursor: %s\n' "${cursor_uuid}"
