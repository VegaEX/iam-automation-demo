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

---

## The full governance loop

Everything above is about *resources* — does a group/policy/app-assignment
that exists in Okta match, or even appear in, Terraform's config. That's only
half the picture. This project also runs a second, complementary loop that
asks a different question: not "does this match config," but **"who made
this change, and should they have?"** That's the job of the
`okta-drift-auditor` Lambda (`lambda-drift-auditor/`), running on an
EventBridge schedule every 15 minutes. It moves through four stages every
time it runs:

### 1. Detect

Pull every Okta System Log event published in the last 15 minutes
(`GET /api/v1/logs?since=...`), then narrow to the event types that touch
things Terraform manages: group lifecycle/membership, policy lifecycle/rule,
and app group/user assignment events. Anything else (logins, password resets,
etc.) is out of scope and discarded immediately.

### 2. Log

Of the events that pass the type filter, keep only the ones whose target
resource ID is in `managed_resources.json` (the current set of
Terraform-managed group/app/policy IDs — regenerated from
`terraform output -json` after every apply). For every one of those, a
structured JSON entry is written to CloudWatch Logs **unconditionally** —
event type, timestamp, actor, target, and the classification below. This
happens whether or not anything gets escalated, so CloudWatch ends up with a
complete audit trail of every change to Terraform-managed Okta resources,
not just the suspicious ones.

### 3. Evaluate

Each event's actor gets classified into exactly one bucket:

| Classification           | Actor looks like                                  | Meaning                                              |
|---------------------------|----------------------------------------------------|-------------------------------------------------------|
| `approved_automation`     | An Okta API token listed in `KNOWN_AUTOMATION_ACTOR_IDS` | The provisioning Lambda or the Terraform/CI pipeline made this change. Expected. |
| `approved_hr_pattern`     | Okta's own `System` actor                          | A dynamic group rule reacted automatically to an upstream profile attribute change (see the worked example below). Expected. |
| `manual_review_required`  | Anything else — a live `User` actor                | A person changed a Terraform-managed resource directly, outside every automated path. Not expected. |

### 4. Resolve or escalate

- `approved_automation` / `approved_hr_pattern` → nothing further happens.
  The CloudWatch log entry from step 2 *is* the record; there's nothing to
  act on.
- `manual_review_required` → the Lambda calls the GitHub Issues API and opens
  an issue titled **"Manual Okta change detected — review required"**,
  containing the event type, timestamp, actor, target(s), outcome, and the
  raw System Log event for debugging - and separately posts a Slack alert
  (`#iam-alerts`, warning severity, via `slack_client.py`) with the same
  who/what/when, so escalations get noticed without anyone having to be
  watching GitHub. A human now decides whether to revert the change (bring
  Okta back to match Terraform) or import it (bring Terraform's config up
  to match what actually happened).

### Step 5, six hours later: did anyone actually look?

Opening the issue isn't the end of the story - an issue nobody looks at is
exactly as useful as no issue at all. Every escalation also gets recorded
(`{issue_number, title, opened_at}`) to an SSM-stored list. A second, entirely
separate entry point - `check_unacknowledged_escalations()`, its own
EventBridge schedule every 6 hours, same Lambda deployment package and IAM
role as `handler()` - reads that list back and re-checks each issue's actual
state via the GitHub API:

- Issue already closed → acknowledged, drop it from the list. Nothing more
  to do.
- Issue still open, less than 24 hours old → leave it alone. Give a human a
  reasonable window to see it first.
- Issue still open, more than 24 hours old → post a Slack reminder (critical
  severity this time, not warning - the title, a link straight to the issue,
  and how many hours it's been sitting there), and leave it in the list.
  Since this check runs every 6 hours, an escalation that's still open next
  time gets reminded *again* - it doesn't stop nagging until someone closes
  the issue.

This is the same detect → log → evaluate → resolve/escalate shape as the
rest of this doc, just running on the *escalation* itself as the thing being
watched, rather than on the original Okta change.

### Worked example: the manager reassignment scenario

This is the case `approved_hr_pattern` exists for — it's easy to mistake for
drift if you don't know the group rules are supposed to do this.

1. Priya's manager reassigns her from Engineering to Operations in Workday.
2. That flows through to Okta as a `department` profile attribute change:
   `"Engineering"` → `"Operations"`.
3. Okta's own dynamic group rules — `Assign Engineering to eng-base` and
   `Assign Operations to ops-base` (defined in
   `terraform/modules/okta_groups/main.tf`) — re-evaluate the instant the
   attribute changes. **Okta itself** removes Priya from `eng-base` and adds
   her to `ops-base`. No person and no Lambda did this directly; Okta's rule
   engine did.
4. That produces two System Log events — `group.user_membership.remove` on
   `eng-base` and `group.user_membership.add` on `ops-base` — both with
   `actor.type == "System"`.
5. Within 15 minutes, `okta-drift-auditor` picks both events up. They target
   Terraform-managed group IDs, so they pass the filter in step 2.
   `classify_event()` sees the `System` actor type and returns
   `approved_hr_pattern`.
6. Result: two CloudWatch log entries recording exactly what happened, and
   **no GitHub issue** — this was the system working as designed.

### A second "expected" path, easy to conflate with the first

The provisioning Lambda's `OktaClient.assign_to_groups()`
(`lambda/src/clients/okta_client.py`) *also* puts new hires straight into
`eng-base`/`ops-base` via a direct Groups API call, as a belt-and-suspenders
measure so the group shows up immediately rather than waiting on the rule
engine above to notice the just-created user's `department` attribute. It's
easy to assume this lands in the same `approved_hr_pattern` bucket as the
manager-reassignment example, since the end result — the user ends up in the
right group — looks identical. It doesn't:

- The rule engine's group changes are logged with `actor.type == "System"` →
  `approved_hr_pattern`.
- The provisioning Lambda's direct API call is authenticated with its own
  Okta API token, so it's logged as an `SSWS` actor → `approved_automation`
  (matched via `KNOWN_AUTOMATION_ACTOR_IDS`, not the actor-type check).

Both are expected, and both are silent (no GitHub issue), but for different
reasons — one because Okta itself made the change, the other because a
known piece of *our* automation did. A brand-new hire in `eng-base` can
legitimately produce *two* separate `group.user_membership.add` events in
the System Log this way (one from each path), both approved, neither
flagged.

**Contrast this with an actual incident:** an IT admin, working from a
support ticket, manually drags Priya into `ops-base` in the Okta console
directly — but nobody has actually updated her `department` attribute in
Workday yet. The System Log event looks almost identical
(`group.user_membership.add` on `ops-base`), but this time `actor.type` is
`User` and the actor ID isn't in `KNOWN_AUTOMATION_ACTOR_IDS`.
`classify_event()` returns `manual_review_required`, and the Lambda opens
**"Manual Okta change detected — review required"**, naming the admin, the
timestamp, and the group — so someone can confirm whether the HR record
needs to catch up, or whether the manual change should be undone and left to
the group rule to handle once it does.

### How this loop relates to the other two

`okta-drift-auditor` never looks at Terraform config or state at all — it
only knows the *list* of resource IDs Terraform owns, not their intended
attribute values. It can tell you *who* changed `eng-base` and whether that
was expected, but not whether the change actually left `eng-base` looking
like `terraform/main.tf` says it should. That's still `terraform plan`'s job
(Type 1, above) and the out-of-band group audit's job (Type 2, above) — this
Lambda is a faster, identity-aware complement to both, not a replacement for
either.

There's a fourth check in this project that's easy to lump in with the above
but isn't actually more drift detection: `lambda/src/access_review.py`
audits every active user's *current* group membership and login recency on
a schedule, with no "before" state and no triggering event at all — it's
built to catch what accumulates quietly over time (a stale transfer, an
account nobody's touched in months) rather than anything that just changed.
See `docs/architecture.md`'s "Why access review is a different kind of
check, not a third drift path" for the full reasoning.
