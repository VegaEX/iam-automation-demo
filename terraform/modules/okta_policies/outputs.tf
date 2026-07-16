output "signon_policy_id" {
  description = "ID of the admin sign-on policy."
  value       = okta_policy_signon.admin_signon.id
}

output "mfa_policy_id" {
  description = "ID of the corporate MFA enrollment policy."
  value       = okta_policy_mfa.corporate_mfa.id
}
