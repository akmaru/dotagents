#!/usr/bin/env bash
#
# Hindsight を MCP サーバーとして各エージェントへ配布する。
# べき等: 何度実行しても同じ結果になる。install.sh から呼ばれる。
#
# mcp/sync-mcp.sh が持つ master-mcp.d/ インクルード機構に相乗りする。
# 接続先 URL と API キーはマシンごとに異なりうるため、リポジトリ内のファイルへの symlink ではなく
# 生成する。別のインスタンスに繋ぐ場合は HINDSIGHT_MCP_URL で上書きする。
#
# サーバーは ApiKeyTenantExtension で認証するので API キーを Authorization ヘッダに載せる。
# キーの探索順と登録方法は api-key.sh を参照。
# キーが無いときは、既定 URL（認証必須の AWS サーバー）向けにはフラグメントを書かない。
# キー無しの設定を配ると全クライアントが 401 になるだけなので、登録方法を案内して正常終了する
# （install.sh 全体を止めない）。HINDSIGHT_MCP_URL を明示した場合は認証なしの開発用インスタンスと
# みなし、ヘッダなしで書く。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/api-key.sh"

DEFAULT_URL="https://hindsight.akmaru.dev/mcp"
MCP_URL="${HINDSIGHT_MCP_URL:-${DEFAULT_URL}}"
MCP_CONF_DIR="${XDG_CONFIG_HOME:-${HOME}/.config}/mcp/master-mcp.d"
FRAGMENT="${MCP_CONF_DIR}/hindsight.json"

API_KEY="$(hindsight_mcp_api_key || true)"

if [[ -z "${API_KEY}" && -z "${HINDSIGHT_MCP_URL:-}" ]]; then
  hindsight_print_api_key_help
  echo "登録後にもう一度 hindsight/install-client.sh を実行してください。Hindsight の配布はスキップします。" >&2
  exit 0
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
