provider "okta" {
  org_name  = var.okta_org_name
  base_url  = var.okta_base_url
  api_token = var.okta_api_token
}

# TODO: configure once modules/lambda_provisioning and modules/api_gateway are wired up.
provider "aws" {
  region = var.aws_region
}
