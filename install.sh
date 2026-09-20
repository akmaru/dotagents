#!/usr/bin/env bash
#
# エージェント環境をこのマシンに導入する。
# べき等: 何度実行しても同じ結果になる。
#
# CLI の導入（ネットワークアクセス）をここに集約し、user/install.sh と mcp/install.sh は
# ローカルの配置だけに保つ。前者は一時 HOME でのテストが成立する前提になっている。
#
# hindsight/install-client.sh は API キーが無ければ登録方法を案内してスキップする
# （フラグメントを書かずに正常終了）ので、ここから呼んでも他の導入は止まらない。
#
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Claude Code CLI ---
curl -fsSL https://claude.ai/install.sh | bash

# --- ユーザーレベル設定 ---
"${ROOT_DIR}/user/install.sh"

# --- MCP ---
"${ROOT_DIR}/mcp/install.sh"

# --- Hindsight (MCP 経由の長期記憶) ---
"${ROOT_DIR}/hindsight/install-client.sh"

echo "Agent environment installed from ${ROOT_DIR}"
