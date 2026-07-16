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
