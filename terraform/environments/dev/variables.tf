# Same variable set as the root terraform/variables.tf - this environment
# is a fully separate root module (own state, own backend), not something
# that inherits from root at runtime.
#
# Caveat, flagged rather than papered over: this demo only has one real
# Okta developer org, so okta_org_name/okta_base_url default here to the
# same values as prod's. A real dev/prod split normally points each
# environment at its own Okta org (or at least a clearly namespaced set of
# groups/apps) so applying both doesn't fight over identically-named
# resources. Until a second org exists, don't apply dev and prod against
# the same Okta org at the same time.

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
  description = "Deployment environment name, used to tag/prefix resources."
  type        = string
  default     = "dev"
}

variable "github_repo" {
  description = "owner/repo that the okta-drift-auditor and provisioning Lambdas open issues against."
  type        = string
}

variable "github_token_param_name" {
  description = "Name of the SSM SecureString parameter holding a GitHub PAT with issues:write."
  type        = string
  default     = "/iam-demo/github-token"
}

variable "enable_aws_resources" {
  description = "Whether to create the AWS-side resources (both Lambdas, API Gateway, EventBridge, the CloudWatch dashboard). Defaults to false so the Okta-only configuration can be applied without AWS credentials or the SSM secrets those modules depend on."
  type        = bool
  default     = false
}

variable "known_automation_actor_ids" {
  description = "Comma-separated Okta actor IDs (API token IDs) the drift auditor treats as known automation. Starts empty - these IDs are only knowable once the provisioning Lambda's and CI's Okta tokens have actually been used and observed in the Okta System Log for this environment."
  type        = string
  default     = ""
}

variable "access_review_function_name" {
  description = "Name of the access-review Lambda function, used to label its CloudWatch dashboard widgets. No Terraform module deploys this Lambda yet."
  type        = string
  default     = "okta-access-review-dev"
}
