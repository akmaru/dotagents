#!/usr/bin/env bash
#
# サーバー上で実行し、SSM Parameter Store から秘密を取り出して .env を生成し、
# コンテナを起動（更新）する。べき等: 何度実行しても同じ結果になる。
#
# 初回は Terraform の user-data から呼ばれる。以降の更新は
#   git -C /opt/dotagents pull && /opt/dotagents/hindsight/compose/deploy.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SSM_PREFIX="${HINDSIGHT_SSM_PREFIX:-/hindsight}"
ENV_FILE="${SCRIPT_DIR}/.env"

# IMDSv2 でリージョンを取る（インスタンスプロファイル経由で SSM を叩く）
TOKEN="$(curl -sf -X PUT "http://169.254.169.254/latest/api/token" -H "X-aws-ec2-metadata-token-ttl-seconds: 60")"
REGION="$(curl -sf -H "X-aws-ec2-metadata-token: ${TOKEN}" http://169.254.169.254/latest/meta-data/placement/region)"

get_param() {
  aws ssm get-parameter --region "${REGION}" --name "${SSM_PREFIX}/$1" --with-decryption --query Parameter.Value --output text
}

umask 077
cat > "${ENV_FILE}" <<ENV
HINDSIGHT_DOMAIN=$(get_param domain)
HINDSIGHT_VERSION=$(get_param version)
HINDSIGHT_DATA_DIR=${HINDSIGHT_DATA_DIR:-/data/hindsight}
HINDSIGHT_API_LLM_API_KEY=$(get_param anthropic_api_key)
HINDSIGHT_API_TENANT_API_KEY=$(get_param tenant_api_key)
POSTGRES_PASSWORD=$(get_param postgres_password)
ENV

mkdir -p "${HINDSIGHT_DATA_DIR:-/data/hindsight}/postgres"

cd "${SCRIPT_DIR}"
docker compose pull --quiet
docker compose up -d --remove-orphans

# hindsight-api の初期化（モデルロード + マイグレーション）を待って疎通確認
for _ in $(seq 1 60); do
  if docker compose exec -T hindsight-api python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8888/health')" >/dev/null 2>&1; then
    echo "Hindsight API is up (domain: $(get_param domain))"
    exit 0
  fi
  sleep 5
done
echo "起動を確認できませんでした。docker compose logs hindsight-api を確認してください。" >&2
exit 1
