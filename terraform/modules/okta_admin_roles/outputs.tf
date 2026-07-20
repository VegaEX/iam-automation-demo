# The exact computed `id` format on okta_user_admin_roles may vary across
# provider versions - verify against the docs for the version pinned in
# versions.tf. Used here as the per-user identifier for this assignment,
# fed into managed_resources.json so the drift auditor tracks admin role
# grants the same way it tracks groups/apps/policies.
output "admin_role_assignment_ids" {
  description = "Map of user email to the okta_user_admin_roles resource ID assigned to them."
  value       = { for email, res in okta_user_admin_roles.this : email => res.id }
}
