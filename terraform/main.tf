module "okta_groups" {
  source = "./modules/okta_groups"

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
  source = "./modules/okta_app_assignments"

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
  source = "./modules/okta_policies"

  admin_group_id = module.okta_groups.group_ids["ops-base"]
}

module "okta_admin_roles" {
  source = "./modules/okta_admin_roles"

  # Empty by default - granting SUPER_ADMIN/ORG_ADMIN is high-impact, so this
  # starts with no real assignments rather than guessing at real admins'
  # emails. Populate with real entries when you're ready for Terraform to
  # manage actual admin role grants, e.g.:
  # admin_assignments = [
  #   { user_email = "jane@acme-corp.example", role_type = "SUPER_ADMIN" },
  # ]
  admin_assignments = []
}

module "lambda_provisioning" {
  source = "./modules/lambda_provisioning"
  count  = var.enable_aws_resources ? 1 : 0

  okta_org_name           = var.okta_org_name
  okta_base_url           = var.okta_base_url
  github_token_param_name = var.github_token_param_name
  github_repo             = var.github_repo
}

module "api_gateway" {
  source = "./modules/api_gateway"
  count  = var.enable_aws_resources ? 1 : 0

  lambda_function_name = module.lambda_provisioning[0].function_name
  lambda_invoke_arn    = module.lambda_provisioning[0].invoke_arn
}

module "okta_drift_auditor" {
  source = "./modules/okta_drift_auditor"
  count  = var.enable_aws_resources ? 1 : 0

  okta_org_name              = var.okta_org_name
  okta_base_url              = var.okta_base_url
  github_repo                = var.github_repo
  known_automation_actor_ids = var.known_automation_actor_ids
  # managed_resource_ids_json intentionally omitted - defaults to "{}".
  # The real value is injected into the Lambda's environment variable
  # out-of-band from `terraform output -json` after each apply, not sourced
  # via file() here (Terraform Cloud's remote runners don't have
  # lambda-drift-auditor/ available relative to this module).
}

module "scheduled_removal" {
  source = "./modules/scheduled_removal"
  count  = var.enable_aws_resources ? 1 : 0

  okta_org_name = var.okta_org_name
  okta_base_url = var.okta_base_url
  github_repo   = var.github_repo
}

module "cloudwatch_dashboard" {
  source = "./modules/cloudwatch_dashboard"
  count  = var.enable_aws_resources ? 1 : 0

  aws_region                         = var.aws_region
  provisioning_lambda_function_name  = module.lambda_provisioning[0].function_name
  drift_auditor_lambda_function_name = module.okta_drift_auditor[0].function_name
  access_review_lambda_function_name = var.access_review_function_name
}
