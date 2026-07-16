# --- Drift detection story: a group created out-of-band in the Okta console ---
#
# Scenario: someone creates a group directly in the Okta admin console (or via
# the API) with no corresponding entry in var.groups.
#
# What `terraform plan` shows: nothing. Plan diffs config against state (after
# refreshing state against the real API) - it only knows about resources it
# already manages. It never inventories the whole Okta org looking for objects
# it's never seen, so an unmanaged group is invisible to it. The one indirect
# way it can surface: if the manual group's name collides with a group this
# config is about to create, plan will still show a clean "create" (it doesn't
# check name uniqueness against the live API), and the collision only fails at
# `terraform apply`, when Okta's API rejects the duplicate name.
#
# How we'd actually detect it: out-of-band auditing, not `terraform plan`.
# Periodically list all groups via the Okta Groups API and diff those
# names/IDs against `terraform state list` (or the names in var.groups). Any
# group that exists in Okta but is absent from state is drift in the
# "unmanaged shadow resource" sense - see docs/drift-detection.md for how this
# project's reconciliation check works.
#
# Once found, two ways to resolve it:
#   1. Import it - add a matching entry to var.groups, then run
#      terraform import 'module.okta_groups.okta_group.this["<name>"]' <group-id>
#      This brings the existing group under Terraform's management without
#      recreating it, so its membership and any app assignments/policy
#      references tied to its ID are preserved. If the live group's attributes
#      (e.g. description) don't match what's now in config, the next plan
#      shows a diff and apply reconciles Okta to match Terraform.
#   2. Destroy and recreate via Terraform - delete the manually-created group
#      in the Okta console/API (Terraform can't destroy what isn't in its
#      state), then add the entry to var.groups so Terraform creates a fresh,
#      Terraform-managed replacement. Simpler, but the new group gets a new
#      Okta ID - any memberships, app assignments, or policy references tied
#      to the old group are lost and must be redone against the new one.
resource "okta_group" "this" {
  for_each = { for g in var.groups : g.name => g }

  name        = each.value.name
  description = each.value.description
}

# okta_group_rule attribute names have shifted across major provider versions -
# double check against the docs for the version pinned in versions.tf before
# applying against a real org.
resource "okta_group_rule" "this" {
  for_each = { for r in var.group_rules : r.name => r }

  name              = each.value.name
  status            = "ACTIVE"
  group_assignments = [okta_group.this[each.value.group_name].id]
  expression_type   = "urn:okta:expression:1.1"
  expression_value  = each.value.expression_value
}
