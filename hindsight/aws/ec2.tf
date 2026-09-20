data "aws_ssm_parameter" "al2023_arm64" {
  name = "/aws/service/ami-amazon-linux-latest/al2023-ami-kernel-default-arm64"
}

resource "aws_instance" "hindsight" {
  ami                    = data.aws_ssm_parameter.al2023_arm64.value
  instance_type          = var.instance_type
  subnet_id              = data.aws_subnets.default.ids[0]
  vpc_security_group_ids = [aws_security_group.hindsight.id]
  iam_instance_profile   = aws_iam_instance_profile.hindsight.name

  root_block_device {
    volume_type = "gp3"
    volume_size = 16
  }

  metadata_options {
    http_tokens = "required" # IMDSv2 のみ
  }

  user_data = templatefile("${path.module}/user-data.sh.tftpl", {
    dotagents_repo = var.dotagents_repo
    dotagents_ref  = var.dotagents_ref
    ssm_prefix     = var.ssm_prefix
  })
  # user-data は初回起動でしか走らない。変更時の再作成はしない（手動で deploy.sh を再実行する）
  user_data_replace_on_change = false

  tags = { Name = "hindsight" }

  lifecycle {
    ignore_changes = [ami] # AMI 更新でインスタンスを作り直さない
  }
}

# Postgres データはルートと分けた EBS に置く。インスタンスを作り直してもデータが残る
resource "aws_ebs_volume" "data" {
  availability_zone = aws_instance.hindsight.availability_zone
  size              = var.data_volume_size_gb
  type              = "gp3"
  encrypted         = true
  tags = {
    Name     = "hindsight-data"
    Snapshot = "hindsight" # DLM がこのタグでスナップショット対象を選ぶ
  }

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_volume_attachment" "data" {
  device_name = "/dev/sdf" # Nitro では /dev/nvme1n1 として見える。user-data は by-id で探す
  volume_id   = aws_ebs_volume.data.id
  instance_id = aws_instance.hindsight.id
}
