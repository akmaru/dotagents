#!/usr/bin/env bash
#
# Hindsight API サーバーを停止する。
# --daemon は PID ファイルも stop サブコマンドも持たないため、待ち受けポートから引く。
#
set -euo pipefail

source "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")/../config.sh"

PID="$(lsof -nP -iTCP:"${HINDSIGHT_API_PORT}" -sTCP:LISTEN -t 2>/dev/null || true)"

if [[ -z "${PID}" ]]; then
  echo "Hindsight API is not running on port ${HINDSIGHT_API_PORT}"
  exit 0
fi

kill ${PID}
echo "Stopped Hindsight API (pid ${PID})"
