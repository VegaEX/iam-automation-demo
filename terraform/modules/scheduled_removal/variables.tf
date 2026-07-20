variable "function_name" {
  description = "Name of the scheduled-removal Lambda function."
  type        = string
  default     = "scheduled-removal"
}

variable "lambda_zip_path" {
  description = "Path to the built deployment package produced by lambda/build.sh. scheduled_removal.py ships in the same package as the provisioning Lambda, not a separate one."
  type        = string
  default     = "../lambda/provisioning.zip"
}

variable "handler" {
  description = "Lambda handler entrypoint."
  type        = string
  default     = "scheduled_removal.handler"
}

variable "runtime" {
  description = "Lambda runtime identifier."
  type        = string
  default     = "python3.12"
}

variable "timeout" {
  description = "Function timeout, in seconds. Needs enough headroom to sweep the pending-removals list and issue an Okta delete call per elapsed record."
  type        = number
  default     = 60
}

variable "schedule_expression" {
  description = "EventBridge schedule expression. Runs once a day - removal dates are day-granularity, so anything more frequent is unnecessary."
  type        = string
  default     = "rate(1 day)"
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
  description = "Name of the SSM SecureString parameter holding the Okta API token. Terraform only references this name, never the value - the function reads the actual secret from SSM itself at invocation time. Same default path as modules/lambda_provisioning's variable of the same name - both point at the same real parameter once deployed."
  type        = string
  default     = "/iam-automation-demo/okta/api_token"
}

variable "github_token_param_name" {
  description = "Name of the SSM SecureString parameter holding a GitHub PAT with issues:write, used to comment on the offboarding issue once a user is permanently deleted. Same default path as modules/lambda_provisioning's variable of the same name."
  type        = string
  default     = "/iam-demo/github-token"
}

variable "github_repo" {
  description = "owner/repo that scheduled_removal.py comments on and links back to when a scheduled deletion completes."
  type        = string
}

variable "slack_webhook_param_name" {
  description = "Name of the SSM SecureString parameter holding the Slack incoming webhook URL used for #iam-alerts. Terraform only references the name, never the value. Same default path as modules/lambda_provisioning and modules/okta_drift_auditor's variables of the same name - all three point at the same real parameter once deployed."
  type        = string
  default     = "/iam-demo/slack-webhook"
}

variable "slack_alerts_channel" {
  description = "Slack channel this function posts completion notices to."
  type        = string
  default     = "#iam-alerts"
}

variable "pending_removals_param_name" {
  description = "Name of the SSM parameter (plain String, not a secret) storing the JSON list of pending offboarding removals. Written by offboarding_manager.py (in the provisioning Lambda), read and rewritten here on each daily sweep. Must match modules/lambda_provisioning's variable of the same name - both point at the same real parameter."
  type        = string
  default     = "/iam-demo/pending-removals"
}

variable "log_retention_days" {
  description = "CloudWatch log group retention, in days."
  type        = number
  default     = 14
}
