#!/usr/bin/env bash
#
# Hindsight Control Plane (Web UI) をローカルで起動し、AWS 上の API に繋ぐ。
# API キーは install-client.sh と同じ Keychain エントリ (hindsight-mcp-api-key) か
# 環境変数 HINDSIGHT_MCP_API_KEY から取る。
#
# --hostname は localhost 固定。127.0.0.1 にすると全ページが 307 で自己リダイレクトする
# (next-intl の rewrite 先が常に "localhost" 綴りで組み立てられるため。issue #1926)。
# 既定ポート 9999 はありふれていて衝突しやすいので 19999 にずらしている。
#
set -euo pipefail

API_URL="${HINDSIGHT_API_URL:-https://hindsight.akmaru.dev}"
PORT="${HINDSIGHT_CP_PORT:-19999}"
KEYCHAIN_SERVICE="hindsight-mcp-api-key"

API_KEY="${HINDSIGHT_MCP_API_KEY:-}"
if [[ -z "${API_KEY}" && "$(uname)" == "Darwin" ]]; then
  API_KEY="$(security find-generic-password -a "${USER}" -s "${KEYCHAIN_SERVICE}" -w 2>/dev/null || true)"
fi
if [[ -z "${API_KEY}" ]]; then
  echo "API キーが見つかりません。install-client.sh と同じ Keychain エントリに登録してください:" >&2
  echo "  security add-generic-password -a \"\${USER}\" -s ${KEYCHAIN_SERVICE} -w" >&2
  exit 1
fi

echo "Control Plane: http://localhost:${PORT}  (API: ${API_URL})"
HINDSIGHT_CP_DATAPLANE_API_URL="${API_URL}" HINDSIGHT_CP_DATAPLANE_API_KEY="${API_KEY}" \
  exec npx -y @vectorize-io/hindsight-control-plane --hostname localhost --port "${PORT}"
