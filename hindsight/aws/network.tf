# 専用 VPC は作らず default VPC を使う（単一インスタンス・公開 443 のみ）

data "aws_vpc" "default" {
  default = true
}

data "aws_subnets" "default" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.default.id]
  }
}

resource "aws_security_group" "hindsight" {
  name        = "hindsight"
  description = "Hindsight: HTTPS from anywhere; admin via SSM Session Manager (no SSH)"
  vpc_id      = data.aws_vpc.default.id

  ingress {
    description = "ACME HTTP-01 / redirect to https"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    description = "HTTPS"
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_eip" "hindsight" {
  domain = "vpc"
  tags   = { Name = "hindsight" }
}

resource "aws_eip_association" "hindsight" {
  instance_id   = aws_instance.hindsight.id
  allocation_id = aws_eip.hindsight.id
}
