variable "function_name" {
  description = "Name of the provisioning Lambda function."
  type        = string
  default     = "iam-provisioning"
}

variable "lambda_zip_path" {
  description = "Path to the built deployment package produced by lambda/build.sh."
  type        = string
  default     = "../lambda/provisioning.zip"
}

variable "handler" {
  description = "Lambda handler entrypoint."
  type        = string
  default     = "handler.handler"
}

variable "runtime" {
  description = "Lambda runtime identifier."
  type        = string
  default     = "python3.12"
}

variable "timeout" {
  description = "Function timeout, in seconds."
  type        = number
  default     = 30
}

variable "reserved_concurrent_executions" {
  description = "Blast radius cap: the maximum number of concurrent invocations this function is ever allowed, regardless of incoming traffic. Also implicitly reserves this much of the account's concurrency pool for this function alone."
  type        = number
  default     = 10
}

variable "okta_org_name" {
  description = "Okta organization name, passed through as an environment variable."
  type        = string
}

variable "okta_base_url" {
  description = "Okta base domain, passed through as an environment variable."
  type        = string
}

variable "okta_api_token_ssm_param_name" {
  description = "Name of the SSM SecureString parameter holding the Okta API token. Terraform only references this name, never the value - the function reads the actual secret from SSM itself at invocation time using its execution role's permissions. The parameter must already exist (created out-of-band, e.g. `aws ssm put-parameter --type SecureString`) before this function can call the Okta API."
  type        = string
  default     = "/iam-automation-demo/okta/api_token"
}

variable "github_token_param_name" {
  description = "Name of the SSM SecureString parameter holding a GitHub PAT with issues:write, used by schema_validator.py to open an issue when an ADP payload contains unmapped fields. Same out-of-band-creation rule as the Okta token above - Terraform only references the name, never the value."
  type        = string
  default     = "/iam-demo/github-token"
}

variable "github_repo" {
  description = "owner/repo that schema_validator.py opens \"ADP payload contains unmapped fields\" issues against, passed through as an environment variable."
  type        = string
}

variable "slack_webhook_param_name" {
  description = "Name of the SSM SecureString parameter holding the Slack incoming webhook URL used for #iam-alerts. Terraform only references the name, never the value - same out-of-band-creation rule as the other secrets. Used by access_review.py, offboarding_manager.py, schema_validator.py, and scheduled_removal.py."
  type        = string
  default     = "/iam-demo/slack-webhook"
}

variable "slack_alerts_channel" {
  description = "Slack channel this Lambda's alerts post to."
  type        = string
  default     = "#iam-alerts"
}

variable "pending_removals_param_name" {
  description = "Name of the SSM parameter (plain String, not a secret) storing the JSON list of pending offboarding removals. Read and written by offboarding_manager.py and scheduled_removal.py."
  type        = string
  default     = "/iam-demo/pending-removals"
}

variable "log_retention_days" {
  description = "CloudWatch log group retention, in days."
  type        = number
  default     = 14
}
