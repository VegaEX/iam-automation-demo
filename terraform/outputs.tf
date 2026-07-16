output "group_ids" {
  description = "Map of Okta group name to group ID."
  value       = module.okta_groups.group_ids
}

output "app_ids" {
  description = "Map of Okta app label to app ID."
  value       = module.okta_app_assignments.app_ids
}

output "admin_signon_policy_id" {
  description = "ID of the sign-on policy enforcing MFA for IT-Admins."
  value       = module.okta_policies.signon_policy_id
}

output "mfa_policy_id" {
  description = "ID of the corporate MFA enrollment policy."
  value       = module.okta_policies.mfa_policy_id
}
