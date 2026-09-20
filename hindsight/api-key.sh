#!/usr/bin/env bash
#
# Hindsight サーバー (ApiKeyTenantExtension) の API キーをクライアント側で取り出す。
# install-client.sh と control-plane.sh から source される（実行はしない）。
#
# 探索順:
#   1. 環境変数 HINDSIGHT_MCP_API_KEY（CI・コンテナ向け）
#   2. OS のキーストア: macOS は Keychain、Linux は secret-tool (libsecret)
#   3. ファイル ${XDG_CONFIG_HOME:-~/.config}/hindsight/mcp-api-key（ヘッドレス Linux 向け、600）
#
# キーの値は AWS の SSM Parameter Store /hindsight/tenant_api_key にある:
#   aws ssm get-parameter --profile maru --name /hindsight/tenant_api_key --with-decryption \
#     --query Parameter.Value --output text
#

HINDSIGHT_KEY_SERVICE="hindsight-mcp-api-key"
HINDSIGHT_KEY_FILE="${XDG_CONFIG_HOME:-${HOME}/.config}/hindsight/mcp-api-key"

# 見つかればキーを stdout に出して 0、なければ何も出さず 1 を返す
hindsight_mcp_api_key() {
  local key="${HINDSIGHT_MCP_API_KEY:-}"
  if [[ -z "${key}" ]]; then
    case "$(uname)" in
      Darwin)
        key="$(security find-generic-password -a "${USER}" -s "${HINDSIGHT_KEY_SERVICE}" -w 2>/dev/null || true)" ;;
      Linux)
        if command -v secret-tool >/dev/null 2>&1; then
          key="$(secret-tool lookup service "${HINDSIGHT_KEY_SERVICE}" 2>/dev/null || true)"
        fi ;;
    esac
  fi
  if [[ -z "${key}" && -r "${HINDSIGHT_KEY_FILE}" ]]; then
    key="$(head -n 1 "${HINDSIGHT_KEY_FILE}")"
  fi
  [[ -n "${key}" ]] || return 1
  printf '%s\n' "${key}"
}

# キーの登録方法を OS に合わせて stderr に案内する
hindsight_print_api_key_help() {
  cat >&2 <<HELP
Hindsight の API キーが見つかりません。値は SSM Parameter Store から取れます:
  aws ssm get-parameter --profile maru --name /hindsight/tenant_api_key --with-decryption --query Parameter.Value --output text

登録方法（いずれか 1 つ）:
HELP
  case "$(uname)" in
    Darwin)
      cat >&2 <<HELP
  macOS Keychain:
    security add-generic-password -a "\${USER}" -s ${HINDSIGHT_KEY_SERVICE} -w
HELP
      ;;
    Linux)
      cat >&2 <<HELP
  libsecret（デスクトップ環境。secret-tool は libsecret-tools パッケージ）:
    secret-tool store --label='Hindsight MCP API key' service ${HINDSIGHT_KEY_SERVICE}
HELP
      ;;
  esac
  cat >&2 <<HELP
  ファイル（ヘッドレス環境向け）:
    mkdir -p "$(dirname "${HINDSIGHT_KEY_FILE}")" && (umask 077 && printf '%s\\n' '<key>' > "${HINDSIGHT_KEY_FILE}")
  環境変数（CI・コンテナ向け）:
    export HINDSIGHT_MCP_API_KEY=<key>
HELP
}
