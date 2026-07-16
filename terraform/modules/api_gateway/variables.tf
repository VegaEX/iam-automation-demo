variable "api_name" {
  description = "Name of the HTTP API."
  type        = string
  default     = "iam-provisioning-api"
}

variable "stage_name" {
  description = "API Gateway stage name. \"$default\" auto-deploys with no stage prefix in the URL."
  type        = string
  default     = "$default"
}

variable "lambda_function_name" {
  description = "Name of the provisioning Lambda function, for the invoke permission."
  type        = string
}

variable "lambda_invoke_arn" {
  description = "Invoke ARN of the provisioning Lambda (from module.lambda_provisioning)."
  type        = string
}
