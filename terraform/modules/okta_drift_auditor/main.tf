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
      # Trailing wildcard right after the function name (not just inside
      # the "*") so this one statement covers both this module's Lambda
      # functions - "${var.function_name}" and
      # "${var.function_name}-escalation-check" - without a second
      # near-duplicate policy statement.
      Resource = "arn:aws:logs:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.function_name}*:*"
    }]
  })
}

# Lets both of this module's Lambda functions read the Okta token, GitHub
# token, and Slack webhook URL from SSM at invocation time - none of these
# secrets' values ever appear in a Terraform-managed environment variable or
# in Terraform state, only their parameter names do (set below).
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
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.github_token_ssm_param_name}",
          "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.slack_webhook_param_name}",
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

# The open-escalations list is plain state, not a secret - both functions
# need to read *and write* it (append on escalation, rewrite on each
# follow-up check), unlike the read-only secrets above.
resource "aws_iam_role_policy" "open_escalations_state" {
  name = "${var.function_name}-open-escalations-state"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "ReadWriteOpenEscalationsParameter"
      Effect   = "Allow"
      Action   = ["ssm:GetParameter", "ssm:PutParameter"]
      Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.open_escalations_param_name}"
    }]
  })
}

# The reported-admin-alerts list is plain state, not a secret - the main
# handler's periodic admin-role-holder audit reads and rewrites it so the
# same unresolved admin grant doesn't reopen a GitHub issue on every
# 15-minute run. Only the main function (aws_lambda_function.this) needs
# this - escalation_check never calls that audit.
resource "aws_iam_role_policy" "reported_admin_alerts_state" {
  name = "${var.function_name}-reported-admin-alerts-state"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid      = "ReadWriteReportedAdminAlertsParameter"
      Effect   = "Allow"
      Action   = ["ssm:GetParameter", "ssm:PutParameter"]
      Resource = "arn:aws:ssm:${data.aws_region.current.name}:${data.aws_caller_identity.current.account_id}:parameter${var.reported_admin_alerts_param_name}"
    }]
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

  environment {
    variables = {
      OKTA_ORG_NAME                    = var.okta_org_name
      OKTA_BASE_URL                    = var.okta_base_url
      OKTA_API_TOKEN_PARAM_NAME        = var.okta_api_token_ssm_param_name
      GITHUB_TOKEN_PARAM_NAME          = var.github_token_ssm_param_name
      GITHUB_REPO                      = var.github_repo
      SLACK_WEBHOOK_PARAM_NAME         = var.slack_webhook_param_name
      SLACK_ALERTS_CHANNEL             = var.slack_alerts_channel
      OPEN_ESCALATIONS_PARAM_NAME      = var.open_escalations_param_name
      KNOWN_AUTOMATION_ACTOR_IDS       = var.known_automation_actor_ids
      KNOWN_ADMIN_EMAILS               = var.known_admin_emails
      REPORTED_ADMIN_ALERTS_PARAM_NAME = var.reported_admin_alerts_param_name
      LOOKBACK_MINUTES                 = tostring(var.lookback_minutes)
      MANAGED_RESOURCE_IDS_JSON        = var.managed_resource_ids_json
    }
  }

  depends_on = [aws_cloudwatch_log_group.this]
}

resource "aws_cloudwatch_event_rule" "schedule" {
  name                = "${var.function_name}-schedule"
  description         = "Triggers ${var.function_name} to audit recent Okta System Log events."
  schedule_expression = var.schedule_expression
}

resource "aws_cloudwatch_event_target" "lambda" {
  rule = aws_cloudwatch_event_rule.schedule.name
  arn  = aws_lambda_function.this.arn
}

resource "aws_lambda_permission" "eventbridge_invoke" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.this.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.schedule.arn
}

# Second function, same zip and role, different entry point - one Lambda
# resource can only run one handler, so check_unacknowledged_escalations
# needs its own aws_lambda_function to be invokable on its own schedule.
resource "aws_cloudwatch_log_group" "escalation_check" {
  name              = "/aws/lambda/${var.function_name}-escalation-check"
  retention_in_days = var.log_retention_days
}

resource "aws_lambda_function" "escalation_check" {
  function_name    = "${var.function_name}-escalation-check"
  role             = aws_iam_role.lambda_exec.arn
  handler          = "handler.check_unacknowledged_escalations"
  runtime          = var.runtime
  timeout          = var.timeout
  filename         = var.lambda_zip_path
  source_code_hash = filebase64sha256(var.lambda_zip_path)

  environment {
    variables = {
      GITHUB_TOKEN_PARAM_NAME     = var.github_token_ssm_param_name
      GITHUB_REPO                 = var.github_repo
      SLACK_WEBHOOK_PARAM_NAME    = var.slack_webhook_param_name
      SLACK_ALERTS_CHANNEL        = var.slack_alerts_channel
      OPEN_ESCALATIONS_PARAM_NAME = var.open_escalations_param_name
    }
  }

  depends_on = [aws_cloudwatch_log_group.escalation_check]
}

resource "aws_cloudwatch_event_rule" "escalation_check_schedule" {
  name                = "${var.function_name}-escalation-check-schedule"
  description         = "Triggers ${var.function_name}-escalation-check to follow up on unacknowledged escalation issues."
  schedule_expression = var.escalation_check_schedule_expression
}

resource "aws_cloudwatch_event_target" "escalation_check" {
  rule = aws_cloudwatch_event_rule.escalation_check_schedule.name
  arn  = aws_lambda_function.escalation_check.arn
}

resource "aws_lambda_permission" "escalation_check_eventbridge_invoke" {
  statement_id  = "AllowEventBridgeInvoke"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.escalation_check.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.escalation_check_schedule.arn
}
