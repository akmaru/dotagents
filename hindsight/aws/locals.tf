locals {
  fqdn = "${var.hostname}.${var.zone_name}"
  # 秘密ではないが接続先として SSM に置くもの。deploy.sh が他の秘密と一緒に読む
  ssm_plain = {
    domain  = local.fqdn
    version = var.hindsight_version
  }
  # Terraform 外で put-parameter しておくべき SecureString
  ssm_secret_names = ["anthropic_api_key", "tenant_api_key", "postgres_password"]
}
