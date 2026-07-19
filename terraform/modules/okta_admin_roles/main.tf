# okta_user_admin_roles is one resource per user (a list of role types),
# not one resource per (user, role) pair - so the flat list of assignments
# this module takes in gets grouped by user_email here first.
locals {
  emails_with_assignments = distinct([for a in var.admin_assignments : a.user_email])

  roles_by_user_email = {
    for email in local.emails_with_assignments :
    email => [for a in var.admin_assignments : a.role_type if a.user_email == email]
  }
}

# admin_assignments is keyed by email, but okta_user_admin_roles needs the
# Okta user ID - this looks each one up. Every email in var.admin_assignments
# must already exist as a real Okta user; this module doesn't create users.
data "okta_user" "this" {
  for_each = local.roles_by_user_email

  search {
    name       = "profile.email"
    comparison = "eq"
    value      = each.key
  }
}

resource "okta_user_admin_roles" "this" {
  for_each = local.roles_by_user_email

  user_id     = data.okta_user.this[each.key].id
  admin_roles = each.value
}
