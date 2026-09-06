#!/usr/bin/env bash
#
# Hindsight API サーバーをデーモンとして起動する。
#
# --daemon は親プロセスが即座に exit(0) するため、バインドに失敗してもシェルには
# 何も出ない。しかも古いプロセスが応答するので /health も通ってしまう。
# そのため起動前のポート衝突チェックと起動後の疎通確認を必ず行う。
#
set -euo pipefail

# ~/.local/bin に symlink された状態でも実体側の config.sh を読む
source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../config.sh"

KEYCHAIN_SERVICE="hindsight-anthropic-api-key"

# API キー: 環境変数が優先。Linux・CI・コンテナでは外部の秘密管理から渡す想定。
if [[ -z "${HINDSIGHT_API_LLM_API_KEY:-}" ]]; then
  if [[ "$(uname)" == "Darwin" ]]; then
    HINDSIGHT_API_LLM_API_KEY="$(security find-generic-password -a "${USER}" -s "${KEYCHAIN_SERVICE}" -w 2>/dev/null || true)"
  fi
fi

if [[ -z "${HINDSIGHT_API_LLM_API_KEY:-}" ]]; then
  echo "API キーが見つかりません。" >&2
  if [[ "$(uname)" == "Darwin" ]]; then
    echo "  security add-generic-password -a \"\${USER}\" -s ${KEYCHAIN_SERVICE} -w" >&2
  else
    echo "  export HINDSIGHT_API_LLM_API_KEY=<Anthropic のキー>" >&2
  fi
  exit 1
fi
export HINDSIGHT_API_LLM_API_KEY

if lsof -nP -iTCP:"${HINDSIGHT_API_PORT}" -sTCP:LISTEN -t >/dev/null 2>&1; then
  echo "ポート ${HINDSIGHT_API_PORT} は既に使用中です。先に hindsight-stop.sh を実行してください。" >&2
  exit 1
fi

hindsight-api --daemon

# デーモンの初期化（pg0 の起動を含む）を待ってから疎通を確認する
for _ in $(seq 1 60); do
  if curl -sf --max-time 3 "http://${HINDSIGHT_API_HOST}:${HINDSIGHT_API_PORT}/health" >/dev/null 2>&1; then
    echo "Hindsight API started on ${HINDSIGHT_API_HOST}:${HINDSIGHT_API_PORT} (log: ~/.hindsight/daemon.log)"
    exit 0
  fi
  sleep 2
done

echo "起動を確認できませんでした。~/.hindsight/daemon.log を確認してください。" >&2
exit 1
