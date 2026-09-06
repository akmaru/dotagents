#!/usr/bin/env bash
#
# エージェント環境をこのマシンに導入する。
# べき等: 何度実行しても同じ結果になる。
#
# CLI の導入（ネットワークアクセス）をここに集約し、user/install.sh と mcp/install.sh は
# ローカルの配置だけに保つ。前者は一時 HOME でのテストが成立する前提になっている。
#
# hindsight/ は動かすマシンでのみ必要なので、ここからは呼ばない。
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Claude Code CLI ---
curl -fsSL https://claude.ai/install.sh | bash

# --- ユーザーレベル設定 ---
"${ROOT_DIR}/user/install.sh"

# --- MCP ---
"${ROOT_DIR}/mcp/install.sh"

echo "Agent environment installed from ${ROOT_DIR}"
