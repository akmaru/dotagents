variable "region" {
  type    = string
  default = "ap-northeast-1"
}

variable "profile" {
  description = "AWS CLI profile。CI 等で環境変数から認証する場合は null"
  type        = string
  default     = null
}

variable "zone_name" {
  description = "レコードを追加する既存の Route 53 Hosted Zone 名（ゾーン自体は別リポジトリが管理）"
  type        = string
}

variable "hostname" {
  description = "zone_name 配下のホスト名。FQDN は <hostname>.<zone_name>"
  type        = string
  default     = "hindsight"
}

variable "instance_type" {
  # hindsight-api full イメージは RAM 1.5GB 以上必要。Postgres と同居するので 4GB
  type    = string
  default = "t4g.medium"
}

variable "data_volume_size_gb" {
  description = "Postgres データ用 EBS (gp3)。ルートとは分け、スナップショットはこちらだけ取る"
  type        = number
  default     = 20
}

variable "snapshot_retain_days" {
  type    = number
  default = 7
}

variable "hindsight_version" {
  description = "ghcr.io/vectorize-io/hindsight-api のタグ"
  type        = string
  default     = "0.9.2"
}

variable "ssm_prefix" {
  description = "秘密を置く SSM Parameter Store のプレフィックス。値は Terraform 外で put-parameter する"
  type        = string
  default     = "/hindsight"
}

variable "dotagents_repo" {
  description = "サーバーが clone する compose 定義のリポジトリ"
  type        = string
  default     = "https://github.com/akmaru/dotagents.git"
}

variable "dotagents_ref" {
  description = "clone 後に checkout するブランチ/タグ。通常は main。未マージのブランチを試すときに変える"
  type        = string
  default     = "main"
}
