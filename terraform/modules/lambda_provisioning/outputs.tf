output "function_name" {
  description = "Name of the provisioning Lambda function."
  value       = aws_lambda_function.this.function_name
}

output "function_arn" {
  description = "ARN of the provisioning Lambda function."
  value       = aws_lambda_function.this.arn
}

output "invoke_arn" {
  description = "Invoke ARN, for wiring into the API Gateway integration."
  value       = aws_lambda_function.this.invoke_arn
}
