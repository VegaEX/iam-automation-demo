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

variable "github_repo" {
  description = "owner/repo (e.g. \"jangus/iam-automation-demo\") that the okta-drift-auditor Lambda opens \"Manual Okta change detected\" issues against, and that the provisioning Lambda opens \"ADP payload contains unmapped fields\" issues against."
  type        = string
}

variable "github_token_param_name" {
  description = "Name of the SSM SecureString parameter holding a GitHub PAT with issues:write, used by the provisioning Lambda's schema_validator.py to open an issue when an ADP payload contains unmapped fields. Terraform only references the name, never the value - the parameter must already exist (created out-of-band)."
  type        = string
  default     = "/iam-demo/github-token"
}

variable "enable_aws_resources" {
  description = "Whether to create the AWS-side resources (both Lambdas, API Gateway, EventBridge). Defaults to false so the Okta-only configuration can be applied without AWS credentials or the SSM secrets those modules depend on."
  type        = bool
  default     = false
}

variable "known_automation_actor_ids" {
  description = "Comma-separated Okta actor IDs (API token IDs) the drift auditor treats as known automation. Starts empty - these IDs are only knowable once the provisioning Lambda's and CI's Okta tokens have actually been used and observed in the Okta System Log, so fill this in after first deploy."
  type        = string
  default     = ""
}
