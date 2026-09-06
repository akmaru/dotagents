#!/usr/bin/env bash
#
# Hindsight サーバー（hindsight-api）をこのマシンに導入する。
# べき等: 何度実行しても同じ結果になる。既存のバンクやデータベースには触れない。
#
# Hindsight を実際に動かすマシンでのみ実行する。ローカル埋め込みモデルを含むため
# 常駐時の RSS が 800MB を超えるので、全マシン共通のインストールには含めない。
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BIN_DIR="${HOME}/.local/bin"
KEYCHAIN_SERVICE="hindsight-anthropic-api-key"

pip install --upgrade hindsight-api

mkdir -p "${BIN_DIR}"
ln -sfn "${SCRIPT_DIR}/bin/hindsight-start.sh" "${BIN_DIR}/hindsight-start.sh"
ln -sfn "${SCRIPT_DIR}/bin/hindsight-stop.sh"  "${BIN_DIR}/hindsight-stop.sh"

# キーの登録は対話入力を伴うため、ここでは案内のみ（非対話実行を壊さない）
if [[ "$(uname)" == "Darwin" ]] \
  && ! security find-generic-password -a "${USER}" -s "${KEYCHAIN_SERVICE}" -w >/dev/null 2>&1; then
  echo
  echo "API キーが未登録です。次のコマンドで Keychain に登録してください:"
  echo "  security add-generic-password -a \"\${USER}\" -s ${KEYCHAIN_SERVICE} -w"
  echo
fi

echo "Installed hindsight-api and linked start/stop scripts into ${BIN_DIR}"
