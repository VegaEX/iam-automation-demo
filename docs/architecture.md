# Architecture

This project has four moving parts that all touch the same Okta org from
different angles:

1. A **real-time provisioning path** — Workday pushes new-hire/termination
   events, a Lambda acts on them immediately. Termination fans out into a
   multi-app offboarding sequence with its own scheduled follow-up Lambda
   (see the diagram and the "Offboarding" section of the README).
2. A **declarative baseline** — Terraform owns the org's groups, group rules,
   app assignments, and policies as code, applied through GitHub Actions.
3. A **drift governance loop** — a second Lambda and a scheduled GitHub Action
   both watch for the baseline and the real world falling out of sync, from
   two different angles (see the note at the end of this doc).
4. A **periodic access review** — a third Lambda that doesn't wait for a
   change at all; it directly audits every active user's current group
   membership and login recency on a schedule (see the note at the end of
   this doc for how this differs from the drift checks above).

```
1) NEW HIRE / TERMINATION FLOW  (event-driven, real-time)
──────────────────────────────────────────────────────────────────────

  Workday (HR system of record)
        │
        │  new-hire / termination JSON payload
        ▼
  API Gateway   POST /provision   (terraform/modules/api_gateway)
        │
        ▼
  Lambda: provisioning  (lambda/, deployed by terraform/modules/lambda_provisioning,
                         reserved_concurrent_executions=10 caps blast radius)
        │
        │  reads its Okta token from SSM at invocation time (execution role
        │  has ssm:GetParameter on /iam-automation-demo/okta/api_token only -
        │  the token's value never appears in Terraform config, state, or a
        │  plain Lambda environment variable)
        │
        │  handler.py rejects outright (structured log + raise, no partial
        │  processing) any single invocation whose event carries more than
        │  25 records - a runaway batch guard, separate from the concurrency
        │  cap above
        │
        │  every Okta API call below retries 429/5xx responses with
        │  exponential backoff + jitter (1s/2s/4s base delays, up to 3
        │  retries) before OktaApiError gives up - anything else (4xx like
        │  400/404) still fails on the first attempt, no retry
        │
        ├── new-hire payload (provisioning/new_hire.py):
        │     1. validate + normalize against adp_schema.json
        │        (schema_validator.py) - a bad payload logs a structured
        │        error and re-raises before any Okta call is made, so the
        │        Lambda returns 400 and the event lands in the DLQ instead
        │        of silently provisioning a user from garbage data
        │     2. create_user()   - Okta user created in STAGED status,
        │        profile mapped from adp_schema.json's okta_attribute map
        │     3. activate_user() - STAGED -> ACTIVE
        │     4. assign_to_groups(department) - all-staff, plus eng-base/
        │        ops-base if the department maps to one (Okta's own dynamic
        │        group rules react to the same department attribute
        │        independently - see the note below)
        │
        └── termination payload (provisioning/termination.py):
              1. okta.initiate_offboarding(email, manager_email) - security
                 first, all of this before anything else runs: deactivate,
                 clear_sessions() (kills active sessions + OAuth tokens),
                 rename_username() -> "<original>_deactivated",
                 move_to_holding_group() -> pending_removal (removed from
                 every other group in the same step). Not found is logged
                 as a warning and returns cleanly, not an error.
              2. offboarding_manager.run_offboarding() - reads
                 offboarding_config.json and, per app:
                   - slack: no-op, note that SCIM (Okta group removal,
                     already done in step 1) deprovisions it automatically
                   - google_workspace: GoogleWorkspaceClient sequence -
                     delegate_inbox -> rename_account -> transfer_drive ->
                     create_hidden_group -> schedule_deletion(30 days)
                     (mocked - no real Workspace credentials in this demo)
                   - github / salesforce / atlassian: collected as manual
                     checklist items, nothing automated
              3. opens "Offboarding checklist — [name]" on GitHub (done
                 actions, manual items with instructions, data-review
                 deadline, final removal date) and appends
                 {email, manager_email, removal_date, issue_number} to an
                 SSM-stored pending-removals list
        ▼
  Okta org   (Okta Users & Groups API)
      - any non-2xx response from Okta is logged (endpoint, status code,
        response body) and re-raised - same fail-loud contract as a
        validation failure: Lambda returns 500, event goes to the DLQ

Note: assign_to_groups() and Okta's own department-driven dynamic group
rules (terraform/modules/okta_groups) both react to the same new hire,
independently - one via a direct API call, one via Okta's rule engine. The
drift auditor doesn't see this as a conflict; see docs/drift-detection.md
for why both paths land in different "expected" buckets rather than one
looking like drift.


1b) SCHEDULED REMOVAL  (daily, follows up on the termination flow above)
──────────────────────────────────────────────────────────────────────

  (no trigger shown here - no Terraform module schedules this Lambda yet)
        │
        ▼
  Lambda: scheduled_removal  (lambda/src/scheduled_removal.py)
        │
        │  reads the pending-removals list offboarding_manager.py wrote
        ▼
  for each {email, manager_email, removal_date, issue_number}:
      - removal_date in the future -> log days remaining, leave it in the list
      - removal_date has passed -> okta.permanently_delete_user(email),
        comment on the original checklist issue, drop it from the list
        │
        ▼
  SSM pending-removals list rewritten with only the still-waiting records


2) DECLARATIVE BASELINE  (Terraform, CI/CD)
──────────────────────────────────────────────────────────────────────

  terraform/*.tf   (groups, group rules, app assignments, policies)
        │
        │  git push / pull request
        ▼
  GitHub Actions
    - terraform-plan.yml    on pull_request -> main  (fmt, validate, plan,
                                                       plan posted as a PR comment)
    - terraform-apply.yml   on push -> main           (apply -auto-approve)
        │
        │  plan/apply runs remotely
        ▼
  Terraform Cloud   (org: jangus-iam-demo, workspace: jangus-iam-demo)
        │
        │  Okta provider API calls
        ▼
  Okta org
      - eng-base / ops-base / it-base / all-staff groups + dynamic group
        rules (department attribute -> eng-base / ops-base; everyone -> all-staff)
      - Slack / GitHub / AWS SSO / Salesforce app assignments
      - MFA enrollment policy + admin sign-on policy (ops-base)


3) DRIFT GOVERNANCE LOOP  (continuous audit, two complementary paths)
──────────────────────────────────────────────────────────────────────

  Okta System Log   (every change, by anyone or anything, is recorded here)
        │
        ├─── fast path: every 15 minutes ───────────────────────────────┐
        │    EventBridge rule (terraform/modules/okta_drift_auditor)    │
        │          ▼                                                    │
        │    Lambda: okta-drift-auditor  (lambda-drift-auditor/)        │
        │      0. resolve OKTA_API_TOKEN and GITHUB_TOKEN from SSM at   │
        │         invocation time - execution role has ssm:GetParameter │
        │         scoped to those two parameters only, nothing else     │
        │      1. pull System Log events from the last 15 minutes       │
        │      2. filter to group / policy / app-assignment event types │
        │      3. keep only events targeting a Terraform-managed        │
        │         resource ID (managed_resources.json)                  │
        │      4. classify the actor:                                   │
        │           - known automation token (provisioning Lambda,      │
        │             Terraform/CI)            -> approved, log only    │
        │           - Okta's own "System" actor (e.g. a dynamic group   │
        │             rule reacting to an HR-driven attribute change)   │
        │                                       -> approved, log only   │
        │           - anything else (a live human)                      │
        │                                       -> ESCALATE             │
        │                                                               │
        │      5. always: structured JSON log entry -> CloudWatch Logs  │
        │      6. on escalation: open a GitHub Issue                    │
        │         "Manual Okta change detected — review required" AND   │
        │         post a Slack alert (#iam-alerts, warning severity),   │
        │         then record {issue_number, title, opened_at} to SSM   │
        │         for the follow-up check below (3b)                   │
        │                                                               │
        └─── slow path: daily at 08:00 UTC ─────────────────────────────┘
             GitHub Actions: terraform-drift.yml
               1. terraform plan -detailed-exitcode   (against real Okta)
               2. exit code 2 (changes found) -> open a GitHub Issue
                  "Drift detected in Okta infrastructure",
                  full plan output attached


3b) ESCALATION FOLLOW-UP  (every 6 hours, follows up on 3's escalations)
──────────────────────────────────────────────────────────────────────

  EventBridge rule (terraform/modules/okta_drift_auditor, separate schedule
  from 3's 15-minute one, same Lambda deployment package and IAM role)
        │
        ▼
  Lambda: okta-drift-auditor-escalation-check
      (handler.check_unacknowledged_escalations - a second aws_lambda_function
       resource, since one Lambda can only run one handler)
        │
        │  reads the open-escalations list handler() wrote in step 6 above
        ▼
  for each {issue_number, title, opened_at}:
      - github.get_issue(issue_number).state != "open" -> acknowledged,
        drop it from the list
      - still open, <= 24h since opened_at -> leave it, no reminder yet
      - still open, > 24h since opened_at -> Slack reminder (critical
        severity: issue title, link, hours open), keep it in the list -
        repeats every 6 hours for as long as it stays open
        │
        ▼
  SSM open-escalations list rewritten with only the still-open records


4) ACCESS REVIEW  (periodic, state-based - not event-driven)
──────────────────────────────────────────────────────────────────────

  (no trigger shown here - no Terraform module schedules this Lambda yet;
   see the "Known gap" in the README)
        │
        ▼
  Lambda: access_review  (lambda/src/access_review.py)
        │
        │  reads its Okta token from SSM, same as the other two Lambdas
        ▼
  okta.list_active_users()   (paginated GET /api/v1/users, ACTIVE only)
        │
        │  for each user: okta.get_user_groups(user_id)
        ▼
      1. group/department cross-check (DEPARTMENT_GROUP_MAP, shared with
         the provisioning Lambda's assign_to_groups()):
           - in eng-base but department != "Engineering" -> flag
           - department == "Engineering" but not in eng-base -> flag
           - same pair, ops-base / "Operations"
      2. stale-access check:
           - lastLogin more than 90 days ago -> flag
           - never logged in AND created more than 7 days ago -> flag
        │
        ▼
  structured report -> CloudWatch Logs (always, every run)
        │
        │  only if mismatches or stale accounts were found
        ▼
  GitHub Issue: "Access review findings — manual review required"
      (Markdown table: user id, email, current groups, expected group,
       reason - and separately, user id, email, last login, days since login)
```

## Why two drift-detection paths, not one

These two loops answer different questions, and neither one covers the other:

- **`okta-drift-auditor` (every 15 min)** answers *"who just did this, and
  should they have?"* It reasons about individual System Log events as they
  happen and is the only place actor identity is evaluated. It has no notion
  of Terraform's declarative config at all - it only knows the *list* of
  resource IDs Terraform currently owns (`managed_resources.json`), not their
  desired attribute values.
- **`terraform-drift.yml` (daily)** answers *"does the live Okta org still
  match the `.tf` config, in full?"* It's a real `terraform plan`, so it
  catches attribute-level drift (e.g. a description silently edited) that the
  auditor Lambda has no way to detect, since that's not an "event" - just a
  changed value it would only notice by re-reading current state and diffing
  against config, which is exactly what `terraform plan` does.

A manual group edit gets caught almost immediately by the auditor Lambda
(who did it), and confirmed/reconciled by the next scheduled `terraform plan`
(what it actually changed). See `docs/drift-detection.md` for the full
detect → log → evaluate → resolve/escalate story, including a worked example.

## Why access review is a different kind of check, not a third drift path

Both checks above are triggered by a *change*: a plan diff, or a System Log
event. `access_review.py` isn't - it has no "before" to compare against. It
directly inspects current state (every active user's group membership and
login recency) and flags internal inconsistencies that may have built up
gradually with no single change ever having triggered either drift check:

- A user transferred from Engineering to Sales six months ago. Their
  `department` attribute changed then (which `okta-drift-auditor` would have
  seen and approved as an HR-driven pattern, if Sales had a mapped group -
  it doesn't). Nobody ever removed them from `eng-base`, and no further
  "change" has happened since to catch it.
- An account has simply sat unused for 91 days. There's no event here at
  all - staleness is a fact about elapsed time, not a change to detect.

Because of that, access review runs at its own cadence, is expected to *find
things* that have been true for a while, and answers a question the other
two structurally can't: not "did anything change," but "is everything still
correct right now."

## Resource ownership

| Concern                                   | Owned by                          |
|--------------------------------------------|------------------------------------|
| User lifecycle (create/deactivate)         | `lambda/` provisioning Lambda      |
| Group/group-rule/app-assignment/policy config | Terraform (`terraform/`)        |
| Admin role grants (`SUPER_ADMIN`, etc.)     | `terraform/modules/okta_admin_roles` - empty by default, tracked in `managed_resources.json` once populated |
| `pending_removal` holding group             | Terraform (`terraform/main.tf`'s `okta_groups` module) creates it; `okta_client.py` manages its membership imperatively, not a dynamic rule |
| Multi-app offboarding sequencing            | `lambda/src/offboarding_manager.py`, driven by `offboarding_config.json` |
| Mocked Google Workspace actions             | `lambda/src/clients/google_workspace_client.py` (no real credentials in this demo) |
| Scheduled permanent deletion + issue follow-up | `lambda/src/scheduled_removal.py` (no deploying Terraform module yet) |
| Provisioning Lambda + its HTTP trigger     | `terraform/modules/lambda_provisioning`, `terraform/modules/api_gateway` |
| Drift auditor Lambda + its schedule        | `terraform/modules/okta_drift_auditor` |
| Terraform state                            | Terraform Cloud - `jangus-iam-demo` workspace for the root config; `iam-automation-demo-dev`/`iam-automation-demo-prod` for `terraform/environments/*` (not yet created - see the README's "Environment promotion pattern") |
| CI/CD for the above                        | GitHub Actions                     |
| Secret values (Okta token, GitHub token, Slack webhook) | SSM Parameter Store (SecureString) — created out-of-band, never in Terraform config/state; each Lambda's IAM role can read only the parameter(s) it needs |
| Pending-removal state (not a secret)        | SSM Parameter Store (plain String) — read *and written* by `offboarding_manager.py`/`scheduled_removal.py` |
| "Was this change authorized?" audit        | `lambda-drift-auditor/`            |
| "Does reality match config?" audit         | `terraform-drift.yml`              |
| "Is everything still correct right now?" audit | `lambda/src/access_review.py` (no deploying Terraform module yet) |
| Slack alerting                              | `lambda/src/clients/slack_client.py`, `lambda-drift-auditor/src/slack_client.py` (two copies, one per deployed package) |
| Dashboards for all of the above            | `terraform/modules/cloudwatch_dashboard` |

## Observability

`terraform/modules/cloudwatch_dashboard` builds one `aws_cloudwatch_dashboard`
with nine widgets: invocations/errors/error-rate/p50-p95-duration for the
provisioning Lambda, invocations/errors/a "ran in the last 15 minutes"
single-value widget for the drift auditor, invocations for the access review
Lambda, and three custom-metric widgets (access review findings count,
failed ADP validations, orphaned account age) under an `IAMAutomationDemo`
namespace. All three custom-metric widgets are real Terraform, wired up in
advance of anything actually publishing to them - no code in this repo calls
`put_metric_data` yet, so those three will render with no data until
something does.
