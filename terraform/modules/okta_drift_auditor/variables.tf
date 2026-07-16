variable "function_name" {
  description = "Name of the drift auditor Lambda function."
  type        = string
  default     = "okta-drift-auditor"
}

variable "lambda_zip_path" {
  description = "Path to the built deployment package produced by lambda-drift-auditor/build.sh."
  type        = string
  default     = "../lambda-drift-auditor/okta-drift-auditor.zip"
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
  description = "Function timeout, in seconds. Needs enough headroom for a paginated Okta System Log call plus a possible GitHub issue creation call."
  type        = number
  default     = 60
}

variable "schedule_expression" {
  description = "EventBridge schedule expression."
  type        = string
  default     = "rate(15 minutes)"
}

variable "lookback_minutes" {
  description = "How far back the function looks in the Okta System Log on each run. Should match the schedule interval so no events are missed between runs."
  type        = number
  default     = 15
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
  description = "Name of the SSM SecureString parameter holding the Okta API token. Terraform only references this name, never the value - the function reads the actual secret from SSM itself at invocation time. The parameter must already exist (created out-of-band, e.g. `aws ssm put-parameter --type SecureString`)."
  type        = string
  default     = "/iam-automation-demo/okta/api_token"
}

variable "github_token_ssm_param_name" {
  description = "Name of the SSM SecureString parameter holding a GitHub PAT with issues:write, used to open drift-review issues. Same out-of-band-creation rule as the Okta token above."
  type        = string
  default     = "/iam-automation-demo/github/token"
}

variable "github_repo" {
  description = "owner/repo that the auditor opens \"Manual Okta change detected\" issues against."
  type        = string
}

variable "known_automation_actor_ids" {
  description = "Comma-separated Okta actor IDs (API token IDs) treated as known automation - the provisioning Lambda's token and the Terraform/CI token - so their changes are approved without escalation. These IDs are only knowable once the tokens exist and have been observed acting in the Okta System Log, so this typically starts empty and gets filled in after first deploy."
  type        = string
  default     = ""
}

variable "managed_resource_ids_json" {
  description = "JSON blob of the Okta resource IDs Terraform currently manages (group/app/policy IDs), used to filter which System Log events the auditor cares about. Passed in as plain Lambda config (not a secret) - the root module supplies this from lambda-drift-auditor/managed_resources.json, or ideally from terraform output -json after each apply."
  type        = string
}

variable "log_retention_days" {
  description = "CloudWatch log group retention, in days."
  type        = number
  default     = 14
}
