data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_iam_role" "lambda_exec" {
  name = "${var.function_name}-exec"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_cloudwatch_log_group" "this" {
  name              = "/aws/lambda/${var.function_name}"
  retention_in_days = var.log_retention_days
}

resource "aws_iam_role_policy" "cloudwatch_logs" {
  name = "${var.function_name}-logs"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
      ]
      Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.function_name}:*"
    }]
  })
}

# Lets the function read its Okta API token and GitHub token from SSM at
# invocation time - the tokens' values never appear in a Terraform-managed
# environment variable or in Terraform state, only their parameter names do
# (set below).
resource "aws_iam_role_policy" "secrets_ssm_read" {
  name = "${var.function_name}-secrets-read"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ReadSecretParameters"
        Effect = "Allow"
        Action = ["ssm:GetParameter"]
        Resource = [
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.okta_api_token_ssm_param_name}",
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.github_token_param_name}",
        ]
      },
      {
        # SSM SecureString parameters under the default AWS-managed key are
        # encrypted with alias/aws/ssm, but IAM resource-level permissions
        # don't reliably support granting kms:Decrypt by key *alias* ARN - so
        # this scopes decrypt access by which service is calling KMS instead
        # of by key resource. Using a customer-managed KMS key instead? Swap
        # this for that key's actual key ARN as the Resource.
        Sid      = "DecryptViaSSM"
        Effect   = "Allow"
        Action   = ["kms:Decrypt"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "kms:ViaService" = "ssm.${data.aws_region.current.name}.amazonaws.com"
          }
        }
      }
    ]
  })
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = aws_iam_role.lambda_exec.arn
  handler          = var.handler
  runtime          = var.runtime
  timeout          = var.timeout
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  # Blast radius protection: caps how many concurrent invocations this
  # function can ever have, regardless of how much traffic API Gateway
  # forwards to it - a runaway retry storm or bulk export gone wrong can't
  # scale this function past reserved_concurrent_executions no matter what.
  reserved_concurrent_executions = var.reserved_concurrent_executions

  environment {
    variables = {
      OKTA_ORG_NAME             = var.okta_org_name
      OKTA_BASE_URL             = var.okta_base_url
      OKTA_API_TOKEN_PARAM_NAME = var.okta_api_token_ssm_param_name
      GITHUB_TOKEN_PARAM_NAME   = var.github_token_param_name
      GITHUB_REPO               = var.github_repo
    }
  }

  depends_on = [aws_cloudwatch_log_group.this]
}
