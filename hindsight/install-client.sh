#!/usr/bin/env bash
#
# Hindsight を MCP サーバーとして各エージェントへ配布する。
# べき等: 何度実行しても同じ結果になる。
#
# dotfiles の mcp/sync-mcp.sh が持つ master-mcp.d/ インクルード機構に相乗りする。
# 接続先 URL はマシンごとに異なりうるため、リポジトリ内のファイルへの symlink ではなく
# 生成する。リモートのサーバーに繋ぐ場合は HINDSIGHT_MCP_URL で上書きする。
#
set -euo pipefail

MCP_URL="${HINDSIGHT_MCP_URL:-http://localhost:8888/mcp}"
MCP_CONF_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/mcp/master-mcp.d"
FRAGMENT="${MCP_CONF_DIR}/hindsight.json"

mkdir -p "${MCP_CONF_DIR}"
cat > "${FRAGMENT}" <<JSON
{
  "servers": {
    "hindsight": {
      "type": "http",
      "url": "${MCP_URL}"
    }
  }
}
JSON

echo "Wrote ${FRAGMENT} (url: ${MCP_URL})"

if command -v sync-mcp.sh >/dev/null 2>&1; then
  sync-mcp.sh
else
  echo "sync-mcp.sh が見つかりません。dotfiles の install/mcp.sh を実行してから sync-mcp.sh を叩いてください。"
fi
