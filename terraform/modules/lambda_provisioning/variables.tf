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

variable "log_retention_days" {
  description = "CloudWatch log group retention, in days."
  type        = number
  default     = 14
}
