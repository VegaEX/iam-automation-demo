provider "okta" {
  org_name  = var.okta_org_name
  base_url  = var.okta_base_url
  api_token = var.okta_api_token
}

# See terraform/providers.tf for why these locals exist - same reasoning
# applies here: provider blocks can't be count-gated, so individual
# arguments react to enable_aws_resources instead.
locals {
  aws_skip_validation = !var.enable_aws_resources
  aws_access_key      = var.enable_aws_resources ? null : "placeholder"
  aws_secret_key      = var.enable_aws_resources ? null : "placeholder"
}

provider "aws" {
  region = var.aws_region

  access_key = local.aws_access_key
  secret_key = local.aws_secret_key

  skip_credentials_validation = local.aws_skip_validation
  skip_requesting_account_id  = local.aws_skip_validation
  skip_metadata_api_check     = local.aws_skip_validation
}
