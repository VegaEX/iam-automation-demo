# Factor block names/attributes on okta_policy_mfa have shifted across major
# versions of the okta/okta provider - double check these against the docs for
# the version pinned in versions.tf before applying against a real org.

resource "okta_policy_signon" "admin_signon" {
  name            = "Admin Sign-On Policy"
  status          = "ACTIVE"
  description     = "Requires MFA for members of the ops-base group."
  groups_included = [var.admin_group_id]
  priority        = 1
}

resource "okta_policy_rule_signon" "admin_signon_mfa" {
  policy_id          = okta_policy_signon.admin_signon.id
  name               = "Require MFA"
  status             = "ACTIVE"
  access             = "ALLOW"
  mfa_required       = true
  mfa_prompt         = "ALWAYS"
  network_connection = "ANYWHERE"
  priority           = 1
}

resource "okta_policy_mfa" "corporate_mfa" {
  name        = "Corporate MFA Policy"
  status      = "ACTIVE"
  description = "Requires Okta Verify enrollment for all users."

  okta_verify = {
    enroll = "REQUIRED"
  }

  okta_password = {
    enroll = "REQUIRED"
  }
}
