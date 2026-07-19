resource "aws_cloudwatch_dashboard" "this" {
  dashboard_name = var.dashboard_name

  dashboard_body = jsonencode({
    widgets = [
      # --- Provisioning Lambda ---
      {
        type   = "metric"
        x      = 0
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Provisioning Lambda - Invocations & Errors"
          view   = "timeSeries"
          region = var.aws_region
          period = 300
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.provisioning_lambda_function_name,
              { stat = "Sum", label = "Invocations" }
            ],
            ["AWS/Lambda", "Errors", "FunctionName", var.provisioning_lambda_function_name,
              { stat = "Sum", label = "Errors" }
            ],
          ]
        }
      },
      {
        type   = "metric"
        x      = 12
        y      = 0
        width  = 12
        height = 6
        properties = {
          title  = "Provisioning Lambda - Error Rate (%)"
          view   = "timeSeries"
          region = var.aws_region
          period = 300
          metrics = [
            ["AWS/Lambda", "Errors", "FunctionName", var.provisioning_lambda_function_name,
              { id = "provErrors", stat = "Sum", visible = false }
            ],
            ["AWS/Lambda", "Invocations", "FunctionName", var.provisioning_lambda_function_name,
              { id = "provInvocations", stat = "Sum", visible = false }
            ],
            [{ expression = "100 * provErrors / MAX([provInvocations, 1])", label = "Error Rate", id = "provErrorRate" }],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Provisioning Lambda - Duration (p50 / p95)"
          view   = "timeSeries"
          region = var.aws_region
          period = 300
          metrics = [
            ["AWS/Lambda", "Duration", "FunctionName", var.provisioning_lambda_function_name,
              { stat = "p50", label = "p50" }
            ],
            ["AWS/Lambda", "Duration", "FunctionName", var.provisioning_lambda_function_name,
              { stat = "p95", label = "p95" }
            ],
          ]
        }
      },

      # --- Drift auditor Lambda ---
      {
        type   = "metric"
        x      = 12
        y      = 6
        width  = 12
        height = 6
        properties = {
          title  = "Drift Auditor Lambda - Invocations & Errors"
          view   = "timeSeries"
          region = var.aws_region
          period = 300
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.drift_auditor_lambda_function_name,
              { stat = "Sum", label = "Invocations" }
            ],
            ["AWS/Lambda", "Errors", "FunctionName", var.drift_auditor_lambda_function_name,
              { stat = "Sum", label = "Errors" }
            ],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 12
        width  = 12
        height = 6
        properties = {
          # CloudWatch has no native "last invocation timestamp" metric - this
          # approximates "is it still running on schedule" as invocations
          # summed over a trailing window matching the auditor's 15-minute
          # EventBridge schedule. Non-zero means it ran recently; a literal
          # last-run timestamp would need CloudWatch Logs Insights or a
          # custom metric instead.
          title  = "Drift Auditor Lambda - Ran In Last 15 Minutes"
          view   = "singleValue"
          region = var.aws_region
          period = 900
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.drift_auditor_lambda_function_name],
          ]
        }
      },

      # --- Access review Lambda ---
      {
        type   = "metric"
        x      = 12
        y      = 12
        width  = 12
        height = 6
        properties = {
          title  = "Access Review Lambda - Invocations"
          view   = "timeSeries"
          region = var.aws_region
          period = 300
          stat   = "Sum"
          metrics = [
            ["AWS/Lambda", "Invocations", "FunctionName", var.access_review_lambda_function_name],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 18
        width  = 12
        height = 6
        properties = {
          # Custom metric - nothing currently publishes to it. access_review.py
          # would need a boto3 cloudwatch put_metric_data call (this namespace/
          # metric name) for this widget to show real data.
          title  = "Access Review - Findings Count (custom metric, not yet published)"
          view   = "timeSeries"
          region = var.aws_region
          period = 3600
          stat   = "Sum"
          metrics = [
            [var.custom_metric_namespace, "AccessReviewFindings"],
          ]
        }
      },

      # --- Cross-cutting custom metrics ---
      {
        type   = "metric"
        x      = 12
        y      = 18
        width  = 12
        height = 6
        properties = {
          # Custom metric - nothing currently publishes to it. schema_validator.py
          # would need a boto3 cloudwatch put_metric_data call on ValidationError
          # for this widget to show real data.
          title  = "Failed ADP Payload Validations (custom metric, not yet published)"
          view   = "timeSeries"
          region = var.aws_region
          period = 3600
          stat   = "Sum"
          metrics = [
            [var.custom_metric_namespace, "ADPValidationFailures"],
          ]
        }
      },
      {
        type   = "metric"
        x      = 0
        y      = 24
        width  = 24
        height = 6
        properties = {
          # Placeholder widget - no Lambda in this project currently computes
          # or publishes an "orphaned account age" metric at all. Kept here as
          # the intended home for that data once something (e.g. a future
          # access-review extension) starts publishing it.
          title  = "Orphaned Account Age (custom metric placeholder - not yet implemented)"
          view   = "timeSeries"
          region = var.aws_region
          period = 3600
          stat   = "Maximum"
          metrics = [
            [var.custom_metric_namespace, "OrphanedAccountAge"],
          ]
        }
      },
    ]
  })
}
