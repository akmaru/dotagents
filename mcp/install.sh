#!/usr/bin/env bash
#
# MCP のマスター設定を配置し、各ツールへ同期する。
# べき等: 何度実行しても同じ結果になる。
#
# master-mcp.d/ は会社用など別リポジトリからの追加設定を置く場所なので、
# ディレクトリだけ作って中身には触れない。
#
set -euo pipefail

MCP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/mcp"
BIN_DIR="${XDG_BIN_HOME:-${HOME}/.local/bin}"

mkdir -p "${CONFIG_DIR}/master-mcp.d" "${BIN_DIR}"

ln -sfn "${MCP_DIR}/master-mcp.json" "${CONFIG_DIR}/master-mcp.json"
ln -sfn "${MCP_DIR}/sync-mcp.sh"     "${BIN_DIR}/sync-mcp.sh"

"${BIN_DIR}/sync-mcp.sh"

echo "Linked MCP master config from ${MCP_DIR} and synced to all tools"
