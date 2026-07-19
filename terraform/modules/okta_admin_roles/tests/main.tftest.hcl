mock_provider "okta" {}

run "groups_assignments_by_user" {
  command = plan

  variables {
    admin_assignments = [
      { user_email = "admin@acme-corp.example", role_type = "SUPER_ADMIN" },
      { user_email = "admin@acme-corp.example", role_type = "ORG_ADMIN" },
      { user_email = "helpdesk@acme-corp.example", role_type = "HELP_DESK_ADMIN" },
    ]
  }

  assert {
    condition     = length(okta_user_admin_roles.this) == 2
    error_message = "expected one okta_user_admin_roles resource per unique user_email"
  }

  assert {
    condition     = contains(okta_user_admin_roles.this["admin@acme-corp.example"].admin_roles, "SUPER_ADMIN")
    error_message = "expected admin@acme-corp.example's role list to include SUPER_ADMIN"
  }

  assert {
    condition     = contains(okta_user_admin_roles.this["admin@acme-corp.example"].admin_roles, "ORG_ADMIN")
    error_message = "expected admin@acme-corp.example's role list to include ORG_ADMIN"
  }
}

run "empty_assignments_creates_nothing" {
  command = plan

  variables {
    admin_assignments = []
  }

  assert {
    condition     = length(okta_user_admin_roles.this) == 0
    error_message = "expected no okta_user_admin_roles resources when admin_assignments is empty"
  }
}
