# 非秘密の接続情報。秘密 (SecureString) は Terraform の state に載せたくないので
# ここでは作らず、存在確認だけする（README の手順で put-parameter する）。

resource "aws_ssm_parameter" "plain" {
  for_each = local.ssm_plain
  name     = "${var.ssm_prefix}/${each.key}"
  type     = "String"
  value    = each.value
}

data "aws_ssm_parameter" "secret" {
  for_each        = toset(local.ssm_secret_names)
  name            = "${var.ssm_prefix}/${each.key}"
  with_decryption = false
}
