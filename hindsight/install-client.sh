#!/usr/bin/env bash
#
# Hindsight を MCP サーバーとして各エージェントへ配布する。
# べき等: 何度実行しても同じ結果になる。
#
# mcp/sync-mcp.sh が持つ master-mcp.d/ インクルード機構に相乗りする。
# 接続先 URL はマシンごとに異なりうるため、リポジトリ内のファイルへの symlink ではなく
# 生成する。リモートのサーバーに繋ぐ場合は HINDSIGHT_MCP_URL で上書きする。
#
# リモート（ApiKeyTenantExtension で認証）に繋ぐ場合は API キーを Authorization ヘッダに
# 載せる。キーは環境変数 HINDSIGHT_MCP_API_KEY が優先、なければ macOS Keychain から取得する:
#   security add-generic-password -a "${USER}" -s hindsight-mcp-api-key -w
# ローカル（認証なし）ではキー不要で、ヘッダは付けない。
#
set -euo pipefail

MCP_URL="${HINDSIGHT_MCP_URL:-http://localhost:8888/mcp}"
MCP_CONF_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/mcp/master-mcp.d"
FRAGMENT="${MCP_CONF_DIR}/hindsight.json"
KEYCHAIN_SERVICE="hindsight-mcp-api-key"

API_KEY="${HINDSIGHT_MCP_API_KEY:-}"
if [[ -z "${API_KEY}" && "$(uname)" == "Darwin" ]]; then
  API_KEY="$(security find-generic-password -a "${USER}" -s "${KEYCHAIN_SERVICE}" -w 2>/dev/null || true)"
fi

mkdir -p "${MCP_CONF_DIR}"
# フラグメントにキーが入るので所有者以外に読ませない。既存ファイルは umask では変わらないので chmod もする
umask 077
[[ -e "${FRAGMENT}" ]] && chmod 600 "${FRAGMENT}"
if [[ -n "${API_KEY}" ]]; then
  jq -n --arg url "${MCP_URL}" --arg key "${API_KEY}" \
    '{servers: {hindsight: {type: "http", url: $url, headers: {Authorization: ("Bearer " + $key)}}}}' \
    > "${FRAGMENT}"
  echo "Wrote ${FRAGMENT} (url: ${MCP_URL}, with API key)"
else
  jq -n --arg url "${MCP_URL}" \
    '{servers: {hindsight: {type: "http", url: $url}}}' \
    > "${FRAGMENT}"
  echo "Wrote ${FRAGMENT} (url: ${MCP_URL}, no API key)"
fi

if command -v sync-mcp.sh >/dev/null 2>&1; then
  sync-mcp.sh
else
  echo "sync-mcp.sh が見つかりません。先に mcp/install.sh を実行してください。"
fi
