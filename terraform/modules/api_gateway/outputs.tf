output "api_endpoint" {
  description = "Base invoke URL for the HTTP API - POST {this}/provision to reach the provisioning Lambda."
  value       = aws_apigatewayv2_stage.default.invoke_url
}
