variable "admin_assignments" {
  description = "Flat list of (user_email, role_type) pairs to grant as standard Okta admin roles - e.g. SUPER_ADMIN, ORG_ADMIN, APP_ADMIN, USER_ADMIN, HELP_DESK_ADMIN, READ_ONLY_ADMIN, REPORT_ADMIN, GROUP_MEMBERSHIP_ADMIN, API_ACCESS_MANAGEMENT_ADMIN, MOBILE_ADMIN (see the okta_user_admin_roles provider docs for the exact set valid on the pinned provider version). Multiple entries for the same user_email are combined into that one user's single okta_user_admin_roles resource - the Okta API assigns a user's admin roles as one list, not one resource per role. Starts empty: granting SUPER_ADMIN/ORG_ADMIN is high-impact, so nothing is assigned until this is explicitly populated."
  type = list(object({
    user_email = string
    role_type  = string
  }))
  default = []
}
