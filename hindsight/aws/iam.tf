# インスタンスは SSM Session Manager 経由で操作し、秘密は Parameter Store から読む

data "aws_iam_policy_document" "assume_ec2" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "hindsight" {
  name               = "hindsight-instance"
  assume_role_policy = data.aws_iam_policy_document.assume_ec2.json
}

resource "aws_iam_role_policy_attachment" "ssm_core" {
  role       = aws_iam_role.hindsight.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

data "aws_caller_identity" "current" {}

data "aws_iam_policy_document" "read_params" {
  statement {
    actions   = ["ssm:GetParameter", "ssm:GetParameters", "ssm:GetParametersByPath"]
    resources = ["arn:aws:ssm:${var.region}:${data.aws_caller_identity.current.account_id}:parameter${var.ssm_prefix}/*"]
  }
}

resource "aws_iam_role_policy" "read_params" {
  name   = "read-hindsight-parameters"
  role   = aws_iam_role.hindsight.id
  policy = data.aws_iam_policy_document.read_params.json
}

resource "aws_iam_instance_profile" "hindsight" {
  name = "hindsight-instance"
  role = aws_iam_role.hindsight.name
}
