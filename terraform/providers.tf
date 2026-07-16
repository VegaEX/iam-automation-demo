provider "okta" {
  org_name  = var.okta_org_name
  base_url  = var.okta_base_url
  api_token = var.okta_api_token
}

# Provider blocks can't be conditional or count-gated the way resources/modules
# can - `terraform init`/`plan` initializes the aws provider and validates its
# credentials regardless of whether var.enable_aws_resources actually creates
# anything. These locals let individual provider arguments react to the flag
# instead: with AWS resources disabled, skip all credential
# validation/account-id/instance-metadata calls and use placeholder keys, so
# init/plan never need real AWS credentials or network access. With AWS
# resources enabled, leave credentials unset (null) so the provider falls
# back to its default credential chain (env vars, shared config, or an IAM
# role) and validates normally.
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
