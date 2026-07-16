output "function_name" {
  description = "Name of the scheduled-removal Lambda function."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "ARN of the scheduled-removal Lambda function."
  value       = aws_lambda_function.this.arn
}

output "schedule_rule_arn" {
  description = "ARN of the EventBridge rule triggering the daily sweep."
  value       = aws_cloudwatch_event_rule.schedule.arn
}
