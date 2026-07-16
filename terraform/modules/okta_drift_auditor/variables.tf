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

<<<<<<< HEAD
variable "slack_webhook_param_name" {
  description = "Name of the SSM SecureString parameter holding the Slack incoming webhook URL used for #iam-alerts. Terraform only references the name, never the value - same out-of-band-creation rule as the other secrets. Used by both the main handler (escalation alerts) and the escalation-check function (unacknowledged reminders). Same default path as modules/lambda_provisioning's variable of the same name - both point at the same real parameter once deployed."
  type        = string
  default     = "/iam-demo/slack-webhook"
}

variable "slack_alerts_channel" {
  description = "Slack channel both entry points post alerts to."
  type        = string
  default     = "#iam-alerts"
}

variable "open_escalations_param_name" {
  description = "Name of the SSM parameter (plain String, not a secret) storing the JSON list of escalation issues opened but not yet confirmed closed. Written by the main handler when it escalates, read and rewritten by the escalation-check function on each run."
  type        = string
  default     = "/iam-demo/drift-auditor/open-escalations"
}

variable "escalation_check_schedule_expression" {
  description = "EventBridge schedule expression for the escalation-check function."
  type        = string
  default     = "rate(6 hours)"
}

=======
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)
variable "known_automation_actor_ids" {
  description = "Comma-separated Okta actor IDs (API token IDs) treated as known automation - the provisioning Lambda's token and the Terraform/CI token - so their changes are approved without escalation. These IDs are only knowable once the tokens exist and have been observed acting in the Okta System Log, so this typically starts empty and gets filled in after first deploy."
  type        = string
  default     = ""
}

<<<<<<< HEAD
variable "known_admin_emails" {
  description = "Comma-separated emails of users expected to hold an Okta admin role (e.g. those declared via terraform/modules/okta_admin_roles). The periodic admin-role-holder audit escalates anyone holding an admin role whose email isn't in this list - starts empty, so populate it once real admins are known, to avoid flagging your own legitimate admins."
  type        = string
  default     = ""
}

variable "reported_admin_alerts_param_name" {
  description = "Name of the SSM parameter (plain String, not a secret) storing the list of admin-holder emails already escalated by the periodic audit, so the same unresolved grant doesn't open a duplicate issue on every 15-minute run. Ongoing reminders for an already-open issue come from the escalation-check function instead (open_escalations_param_name)."
  type        = string
  default     = "/iam-demo/drift-auditor/reported-admins"
}

variable "managed_resource_ids_json" {
  description = "JSON blob of the Okta resource IDs Terraform currently manages (group/app/policy IDs), used to filter which System Log events the auditor cares about. Not sourced via file() from this module - Terraform Cloud's remote runners don't have lambda-drift-auditor/ available relative to this module's path. Defaults to an empty object; the real value is injected into the Lambda's MANAGED_RESOURCE_IDS_JSON environment variable out-of-band, populated from `terraform output -json` after each apply."
  type        = string
  default     = "{}"
=======
variable "managed_resource_ids_json" {
  description = "JSON blob of the Okta resource IDs Terraform currently manages (group/app/policy IDs), used to filter which System Log events the auditor cares about. Passed in as plain Lambda config (not a secret) - the root module supplies this from lambda-drift-auditor/managed_resources.json, or ideally from terraform output -json after each apply."
  type        = string
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)
}

variable "log_retention_days" {
  description = "CloudWatch log group retention, in days."
  type        = number
  default     = 14
}
