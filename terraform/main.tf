module "okta_groups" {
  source = "./modules/okta_groups"

  groups = [
    { name = "eng-base", description = "Baseline access group for Engineering staff" },
    { name = "ops-base", description = "Baseline access group for Operations/IT staff" },
    { name = "all-staff", description = "Automatic membership for every active employee" },
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

# TODO: wire up modules/lambda_provisioning and modules/api_gateway once the
# Lambda source under lambda/ is implemented.
