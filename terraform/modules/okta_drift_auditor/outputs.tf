output "function_name" {
  description = "Name of the drift auditor Lambda function."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "ARN of the drift auditor Lambda function."
  value       = aws_lambda_function.this.arn
}

output "schedule_rule_arn" {
  description = "ARN of the EventBridge rule triggering the auditor."
  value       = aws_cloudwatch_event_rule.schedule.arn
}

output "escalation_check_function_name" {
  description = "Name of the escalation-check Lambda function."
  value       = aws_lambda_function.escalation_check.function_name
}

output "escalation_check_schedule_rule_arn" {
  description = "ARN of the EventBridge rule triggering the escalation-check function."
  value       = aws_cloudwatch_event_rule.escalation_check_schedule.arn
}
