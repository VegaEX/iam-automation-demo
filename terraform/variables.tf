variable "okta_org_name" {
  description = "Okta organization name - the 'acme-corp' in acme-corp.okta.com."
  type        = string
  default     = "acme-corp"
}

variable "okta_base_url" {
  description = "Okta base domain for the org (okta.com for production orgs, oktapreview.com for preview orgs)."
  type        = string
  default     = "okta.com"
}

variable "okta_api_token" {
  description = "Okta API token used by the provider. Set via a local terraform.tfvars (gitignored) or a sensitive Terraform Cloud workspace variable - never commit a real value."
  type        = string
  sensitive   = true
}

variable "aws_region" {
  description = "AWS region the Lambda/API Gateway infrastructure is deployed into."
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment name, used to tag/prefix resources (e.g. dev, prod)."
  type        = string
  default     = "dev"
}
