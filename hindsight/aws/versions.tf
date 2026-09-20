terraform {
  required_version = ">= 1.10"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }
  # バケット名などアカウント固有の値は backend.hcl（gitignore）で渡す:
  #   terraform init -backend-config=backend.hcl
  backend "s3" {}
}

provider "aws" {
  region  = var.region
  profile = var.profile
  default_tags {
    tags = { ManagedBy = "terraform", Repo = "akmaru/dotagents", Stack = "hindsight" }
  }
}
