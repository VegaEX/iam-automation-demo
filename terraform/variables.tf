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
  description = "owner/repo (e.g. \"jangus/iam-automation-demo\") that the okta-drift-auditor Lambda opens \"Manual Okta change detected\" issues against."
  type        = string
}

variable "known_automation_actor_ids" {
  description = "Comma-separated Okta actor IDs (API token IDs) the drift auditor treats as known automation. Starts empty - these IDs are only knowable once the provisioning Lambda's and CI's Okta tokens have actually been used and observed in the Okta System Log, so fill this in after first deploy."
  type        = string
  default     = ""
}
