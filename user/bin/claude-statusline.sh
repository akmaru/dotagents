#!/usr/bin/env bash
# Claude Code statusLine: model, context usage, tokens, session cost, session-average throughput.
#
# user/settings.json の statusLine から参照され、user/install.sh が ~/.local/bin へ symlink する。
#
# Note: TTFT / TPOT are NOT in the statusline JSON and cannot be derived from the
# transcript (block timestamps are not token-arrival times). For accurate per-request
# ttft_ms / first_content_ms, enable OTEL tracing:
#   CLAUDE_CODE_ENABLE_TELEMETRY=1 CLAUDE_CODE_ENHANCED_TELEMETRY_BETA=1 \
#   OTEL_TRACES_EXPORTER=otlp OTEL_EXPORTER_OTLP_ENDPOINT=http://localhost:4317 claude
# The rate below is a session average, not a per-request measurement.

INPUT=$(cat)

MODEL=$(echo "$INPUT" | jq -r '.model.display_name // "unknown"')
PCT=$(echo "$INPUT" | jq -r '.context_window.used_percentage // empty')
USED=$(echo "$INPUT" | jq -r '(.context_window.current_usage.input_tokens // 0) + (.context_window.current_usage.cache_creation_input_tokens // 0) + (.context_window.current_usage.cache_read_input_tokens // 0)')
SIZE=$(echo "$INPUT" | jq -r '.context_window.context_window_size // 200000')
COST=$(echo "$INPUT" | jq -r '.cost.total_cost_usd // 0')
API_MS=$(echo "$INPUT" | jq -r '.cost.total_api_duration_ms // 0')
TP=$(echo "$INPUT" | jq -r '.transcript_path // empty')

# current_usage is null before the first API call; fall back to session totals
[ "$USED" = "0" ] && USED=$(echo "$INPUT" | jq -r '.context_window.total_input_tokens // 0')

# Color the percentage by how full the context is
if [ -n "$PCT" ]; then
  PCT_INT=${PCT%.*}
  if [ "$PCT_INT" -ge 80 ]; then C='\033[31m'; elif [ "$PCT_INT" -ge 50 ]; then C='\033[33m'; else C='\033[32m'; fi
  PCT_STR=$(printf "${C}%s%%\033[0m" "$PCT_INT")
else
  PCT_INT=0
  PCT_STR='--%'
fi

fmt() { awk -v n="$1" 'BEGIN { if (n >= 1000000) printf "%.1fM", n/1000000; else if (n >= 1000) printf "%.0fk", n/1000; else printf "%d", n }'; }

# Session-average output throughput: sum unique assistant output tokens / total API time
TPS=''
if [ -n "$TP" ] && [ -f "$TP" ]; then
  OUT_TOK=$(jq -rs '[ .[] | select(.type=="assistant" and .message.id != null)
      | {mid: .message.id, out: (.message.usage.output_tokens // 0)} ]
    | group_by(.mid) | map(.[0].out) | add // 0' "$TP" 2>/dev/null)
  if [ -n "$OUT_TOK" ] && [ "$OUT_TOK" -gt 0 ] && [ "$API_MS" -gt 0 ]; then
    TPS=$(awk -v o="$OUT_TOK" -v m="$API_MS" 'BEGIN { printf "%.0f", o/(m/1000) }')
  fi
fi

printf '\033[36m%s\033[0m  %s %s/%s  \033[2m$%.2f\033[0m' \
  "$MODEL" "$PCT_STR" "$(fmt "$USED")" "$(fmt "$SIZE")" "$COST"

[ -n "$TPS" ] && printf '  \033[2m~%stok/s\033[0m' "$TPS"
