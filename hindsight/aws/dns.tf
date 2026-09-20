# ゾーンは別リポジトリ (akmaru/akmaru.dev) が管理する。ここは名前引きしてレコードを 1 本足すだけ
data "aws_route53_zone" "zone" {
  name = "${var.zone_name}."
}

resource "aws_route53_record" "hindsight" {
  zone_id = data.aws_route53_zone.zone.zone_id
  name    = local.fqdn
  type    = "A"
  ttl     = 300
  records = [aws_eip.hindsight.public_ip]
}
