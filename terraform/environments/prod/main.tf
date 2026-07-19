# Calls the same modules as the root terraform/main.tf, from one directory
# further down - module source paths are relative to this file, hence
# "../../modules/..." instead of "./modules/...".

module "okta_groups" {
  source = "../../modules/okta_groups"

  groups = [
    { name = "eng-base", description = "Baseline access group for Engineering staff" },
    { name = "ops-base", description = "Baseline access group for Operations/IT staff" },
    { name = "it-base", description = "IT department base access group" },
    { name = "all-staff", description = "Automatic membership for every active employee" },
    { name = "pending_removal", description = "Holding group for terminated users awaiting permanent deletion" },
  ]

  group_rules = [
    {
      name             = "Assign Engineering to eng-base"
      group_name       = "eng-base"
      expression_value = "user.department==\"Engineering\""
    },
    {
      name             = "Assign Operations to ops-base"
      group_name       = "ops-base"
      expression_value = "user.department==\"Operations\""
    },
    {
      name             = "Assign everyone to all-staff"
      group_name       = "all-staff"
      expression_value = "user.login!=null"
    },
  ]
}

module "okta_app_assignments" {
  source = "../../modules/okta_app_assignments"

  apps = [
    { label = "Acme Slack Workspace", url = "https://acme-corp.slack.com" },
    { label = "Acme GitHub Organization", url = "https://github.com/acme-corp" },
    { label = "Acme AWS SSO", url = "https://acme-corp.awsapps.com/start" },
    { label = "Acme Salesforce", url = "https://acme-corp.my.salesforce.com" },
  ]

  assignments = [
    { app_label = "Acme Slack Workspace", group_name = "all-staff" },
    { app_label = "Acme GitHub Organization", group_name = "eng-base" },
    { app_label = "Acme AWS SSO", group_name = "eng-base" },
    { app_label = "Acme AWS SSO", group_name = "ops-base" },
    { app_label = "Acme Salesforce", group_name = "ops-base" },
  ]

  group_ids = module.okta_groups.group_ids
}

module "okta_policies" {
  source = "../../modules/okta_policies"

  admin_group_id = module.okta_groups.group_ids["ops-base"]
}

module "okta_admin_roles" {
  source = "../../modules/okta_admin_roles"

  # Empty by default - see terraform/main.tf's module block for the same
  # rationale. Populate per-environment once you're ready to manage real
  # admin role grants here.
  admin_assignments = []
}

module "lambda_provisioning" {
  source = "../../modules/lambda_provisioning"
  count  = var.enable_aws_resources ? 1 : 0

  function_name           = "iam-provisioning-${var.environment}"
  okta_org_name           = var.okta_org_name
  okta_base_url           = var.okta_base_url
  github_token_param_name = var.github_token_param_name
  github_repo             = var.github_repo
}

module "api_gateway" {
  source = "../../modules/api_gateway"
  count  = var.enable_aws_resources ? 1 : 0

  api_name             = "iam-provisioning-api-${var.environment}"
  lambda_function_name = module.lambda_provisioning[0].function_name
  lambda_invoke_arn    = module.lambda_provisioning[0].invoke_arn
}

module "okta_drift_auditor" {
  source = "../../modules/okta_drift_auditor"
  count  = var.enable_aws_resources ? 1 : 0

  function_name              = "okta-drift-auditor-${var.environment}"
  okta_org_name              = var.okta_org_name
  okta_base_url              = var.okta_base_url
  github_repo                = var.github_repo
  known_automation_actor_ids = var.known_automation_actor_ids
  # managed_resource_ids_json intentionally omitted - defaults to "{}",
  # same reasoning as root/main.tf.
}

module "cloudwatch_dashboard" {
  source = "../../modules/cloudwatch_dashboard"
  count  = var.enable_aws_resources ? 1 : 0

  dashboard_name                     = "iam-automation-demo-${var.environment}"
  aws_region                         = var.aws_region
  provisioning_lambda_function_name  = module.lambda_provisioning[0].function_name
  drift_auditor_lambda_function_name = module.okta_drift_auditor[0].function_name
  access_review_lambda_function_name = var.access_review_function_name
}
