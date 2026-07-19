variable "dashboard_name" {
  description = "Name of the CloudWatch dashboard."
  type        = string
  default     = "iam-automation-demo"
}

variable "aws_region" {
  description = "AWS region the widgeted metrics are read from."
  type        = string
}

variable "provisioning_lambda_function_name" {
  description = "Name of the provisioning Lambda function (terraform/modules/lambda_provisioning)."
  type        = string
}

variable "drift_auditor_lambda_function_name" {
  description = "Name of the okta-drift-auditor Lambda function (terraform/modules/okta_drift_auditor)."
  type        = string
}

variable "access_review_lambda_function_name" {
  description = "Name of the access-review Lambda function (lambda/src/access_review.py). No Terraform module deploys this Lambda yet - this only names the function the dashboard's widgets will look for once one does."
  type        = string
}

variable "custom_metric_namespace" {
  description = "CloudWatch namespace for this project's custom (non-AWS-native) metrics: access review findings, ADP validation failures, orphaned account age. Nothing currently publishes to this namespace - see the comments on the widgets that reference it."
  type        = string
  default     = "IAMAutomationDemo"
}
