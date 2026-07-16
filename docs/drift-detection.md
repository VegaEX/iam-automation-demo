# Drift Detection

## What is "drift"?

Terraform's whole job is to make the real world (in this project, our Okta
org) match what's written in the `.tf` config files. **Drift** is any point
where that stops being true — where the real world and Terraform's
understanding of it have fallen out of sync. It almost always happens because
someone changed something outside of Terraform: a click in the Okta admin
console, a direct API call, a script run by hand.

This project has two meaningfully different kinds of drift, and they behave
very differently when you run `terraform plan`.

## Type 1: Managed resource drift

This is drift on something Terraform already knows about — it's declared in
our config (e.g. in `terraform/modules/okta_groups/main.tf`) and recorded in
Terraform's state file. Someone just changed one of its properties outside of
Terraform.

**Example:** someone opens the Okta console and edits the description on the
`eng-base` group.

### How `terraform plan` catches this — automatically

Before it builds a plan, Terraform *refreshes*: it asks Okta for the current,
live value of every resource already in state, and compares that against what
state recorded. Any mismatch shows up as a proposed change:

```
  # module.okta_groups.okta_group.this["eng-base"] will be updated in-place
  ~ resource "okta_group" "this" {
      ~ description = "Some manual edit made in the console" -> "Baseline access group for Engineering staff"
        name        = "eng-base"
    }
```

Running `terraform apply` reconciles Okta back to whatever the `.tf` files
say. This direction of drift is the easy case — Terraform is designed
specifically to notice and fix it.

## Type 2: Unmanaged shadow resources

This is a different, trickier situation: someone creates something **brand
new** in Okta that our Terraform config has never heard of.

**Example:** someone creates a group called `finance-team` directly in the
Okta console. It's never been added to the `groups` list in
`terraform/main.tf`, and Terraform has no record of it anywhere.

### Why `terraform plan` can't catch this

This is the important gap, and it's easy to assume Terraform protects against
it when it doesn't: **`terraform plan` will show nothing at all for
`finance-team`.**

Plan only compares *resources it already tracks* — the ones in state —
against their live values and against config. It never goes and asks Okta
"list every group you have, so I can check if there's anything I've never
seen before." A hand-created group just sits there in the Okta org, silently,
indefinitely, unless someone finds it some other way.

The one indirect way it can leak through: a **naming collision**. If
`finance-team` happened to match a group name our config was about to create,
`terraform plan` would still show a clean, ordinary "create" action — it
doesn't check the live API for name conflicts ahead of time. The collision
only surfaces at `terraform apply`, when Okta's API rejects the request
because a group with that name already exists.

## The out-of-band audit

Since `terraform plan` structurally can't find shadow resources, finding them
means comparing two lists from two different sources of truth:

1. **What actually exists in Okta** — call the Okta Groups API
   (`GET /api/v1/groups`) to list every group in the org, no matter who or
   what created it.
2. **What Terraform believes it manages** — `terraform state list` shows
   every resource in state, e.g.
   `module.okta_groups.okta_group.this["eng-base"]`. Because our module keys
   groups by name (see the `for_each` in `okta_groups/main.tf`), the group
   name is sitting right there in the resource address.

Any group name that shows up in list #1 but not in list #2 is a shadow
resource: it exists in Okta, Terraform doesn't know about it, and
`terraform plan` will never mention it on its own.

### Audit script pattern

```bash
#!/usr/bin/env bash
# audit-group-drift.sh
# Lists every group that actually exists in Okta and compares it against the
# groups Terraform believes it manages. Anything printed at the end exists in
# Okta but is invisible to `terraform plan`.
set -euo pipefail

OKTA_ORG_URL="https://${OKTA_ORG_NAME}.${OKTA_BASE_URL}"

# 1. Every group Okta actually has, by name.
#    (Demo-scale only - a real script would follow the API's Link-header
#    pagination past the first page of results.)
curl -s -H "Authorization: SSWS ${OKTA_API_TOKEN}" \
  "${OKTA_ORG_URL}/api/v1/groups?limit=200" \
  | jq -r '.[].profile.name' \
  | sort > /tmp/okta_groups_actual.txt

# 2. Every group name Terraform's state says it manages.
terraform -chdir=terraform state list \
  | grep 'okta_group\.this\[' \
  | sed -E 's/.*this\["(.*)"\]/\1/' \
  | sort > /tmp/okta_groups_managed.txt

# 3. In Okta but not in Terraform state = unmanaged shadow group.
echo "Shadow groups (in Okta, not managed by Terraform):"
comm -23 /tmp/okta_groups_actual.txt /tmp/okta_groups_managed.txt
```

## Resolving a shadow group once you find one

Once an audit turns up a shadow group, there are two ways to bring things
back in sync (see the full comment in `okta_groups/main.tf` for details):

1. **Import it** — add a matching entry to `var.groups` and run
   `terraform import` against the existing group's ID. This brings it under
   Terraform's management without recreating it, so its membership and any
   app assignments already pointing at it are preserved.
2. **Destroy and recreate via Terraform** — delete the group by hand in Okta
   (Terraform can't destroy what isn't in its state), then add it to
   `var.groups` so Terraform creates a fresh, Terraform-managed replacement.
   Simpler, but the new group gets a new Okta ID, so any existing
   memberships, app assignments, or policy references tied to the old group
   are lost and have to be redone.
