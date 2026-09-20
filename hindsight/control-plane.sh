#!/usr/bin/env bash
#
# Hindsight Control Plane (Web UI) をローカルで起動し、AWS 上の API に繋ぐ。
# API キーは install-client.sh と同じ探索順（api-key.sh）で取る。
#
# --hostname は localhost 固定。127.0.0.1 にすると全ページが 307 で自己リダイレクトする
# (next-intl の rewrite 先が常に "localhost" 綴りで組み立てられるため。issue #1926)。
# 既定ポート 9999 はありふれていて衝突しやすいので 19999 にずらしている。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/api-key.sh"

API_URL="${HINDSIGHT_API_URL:-https://hindsight.akmaru.dev}"
PORT="${HINDSIGHT_CP_PORT:-19999}"

if ! API_KEY="$(hindsight_mcp_api_key)"; then
  hindsight_print_api_key_help
  exit 1
fi

echo "Control Plane: http://localhost:${PORT}  (API: ${API_URL})"
HINDSIGHT_CP_DATAPLANE_API_URL="${API_URL}" HINDSIGHT_CP_DATAPLANE_API_KEY="${API_KEY}" \
  exec npx -y @vectorize-io/hindsight-control-plane --hostname localhost --port "${PORT}"
