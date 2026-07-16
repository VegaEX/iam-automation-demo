# IAM Automation Demo

<<<<<<< HEAD
A working demo of IAM-as-code for Okta. Terraform owns the declarative baseline (groups, dynamic group rules, app assignments, policies), a Lambda handles real-time HR provisioning events — including a full multi-app offboarding sequence on termination — GitHub Actions and Terraform Cloud run the CI/CD pipeline, a second Lambda plus a scheduled workflow continuously verify that the live Okta org matches what's declared, and a third Lambda periodically audits every active user for group/department mismatches and stale access.
=======
A working demo of IAM-as-code for Okta. Terraform owns the declarative baseline (groups, dynamic group rules, app assignments, policies), a Lambda handles real-time HR provisioning events, GitHub Actions and Terraform Cloud run the CI/CD pipeline, and a second Lambda plus a scheduled workflow continuously verify that the live Okta org matches what's declared — and that any change that doesn't match came from an authorized source.
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)

See `docs/architecture.md` for the full system diagram and `docs/drift-detection.md` for a deep dive on the drift governance loop.

## What this demonstrates

- Managing an identity provider (Okta) as code, including dynamic attribute-based group membership, not just static resources.
- Event-driven provisioning (HR system → API Gateway → Lambda → Okta) kept separate from, but consistent with, the Terraform-managed baseline.
- A real CI/CD pipeline for infrastructure: plan-on-PR with a posted plan comment, apply-on-merge, and a remote Terraform Cloud backend.
- Two complementary drift detection approaches: whether live state still matches config, and whether every change to a managed resource came from an authorized actor.
<<<<<<< HEAD
- A periodic access review that catches what event-driven drift detection can't: accounts nobody actively changed, but that have quietly become wrong or stale over time.
=======
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)

## Components

| Path | What it is |
|------|------------|
| `terraform/` | Root Terraform config: providers, variables, Terraform Cloud backend, and module wiring for Okta groups, app assignments, and policies. |
| `terraform/modules/okta_groups` | `eng-base`, `ops-base`, `it-base`, `all-staff` groups, plus dynamic group rules assigning users based on their `department` profile attribute. |
| `terraform/modules/okta_app_assignments` | Bookmark apps (Slack, GitHub, AWS SSO, Salesforce) and group-to-app assignments. |
| `terraform/modules/okta_policies` | MFA enrollment policy (org-wide) and an admin sign-on policy requiring MFA for `ops-base`. |
<<<<<<< HEAD
| `terraform/modules/okta_admin_roles` | Declarative Okta admin role grants (`okta_user_admin_roles`) from a flat `(user_email, role_type)` list, grouped into one resource per user. Starts with zero assignments - granting `SUPER_ADMIN`/`ORG_ADMIN` is high-impact, so nothing is granted until explicitly populated. Tested with `terraform test` + `mock_provider` (no real Okta user needed to validate the module's structure). |
| `terraform/environments/dev`, `terraform/environments/prod` | Per-environment root configs - own Terraform Cloud workspace, own `backend.tf`/`variables.tf`, same modules as root `main.tf`. See "Environment promotion pattern" below. |
| `terraform/modules/lambda_provisioning` | Provisioning Lambda function + IAM execution role (CloudWatch Logs, SSM read for the Okta token). `reserved_concurrent_executions = 10` caps blast radius regardless of incoming traffic. |
| `terraform/modules/api_gateway` | HTTP API with a `POST /provision` route wired to the provisioning Lambda. |
| `terraform/modules/okta_drift_auditor` | Two Lambdas sharing one deployment package and IAM role: `okta-drift-auditor` (15-minute schedule - the audit loop, plus admin-privilege-grant detection and a periodic admin-role-holder audit against `KNOWN_ADMIN_EMAILS` - see below) and `okta-drift-auditor-escalation-check` (6-hour schedule, follows up on escalations nobody's acknowledged yet). |
| `terraform/modules/scheduled_removal` | Deploys `scheduled_removal.py` as its own Lambda function + IAM execution role (CloudWatch Logs, SSM read for the Okta/GitHub/Slack secrets, SSM read/write for the pending-removals parameter) on a daily EventBridge schedule. |
| `terraform/modules/cloudwatch_dashboard` | A single `aws_cloudwatch_dashboard` covering all three Lambdas' invocations/errors/duration, plus three custom-metric widgets nothing publishes to yet (see Implementation status). |
| `lambda/` | Provisioning Lambda (new-hire/termination webhook handler). Implemented and unit-tested: ADP payload validation/normalization (`schema_validator.py`), an `OktaClient` (`clients/okta_client.py`) that creates/activates/assigns new hires and, on termination, immediately deactivates/clears sessions/renames/holds the departing user before handing off to the offboarding flow below. `okta_client.py`'s `_request()` retries 429/5xx responses with exponential backoff + jitter (max 3 retries) before giving up; `handler.py` rejects any single invocation with more than 25 records outright rather than processing a runaway batch. |
| `lambda/src/offboarding_config.json` | Per-app termination behavior: Slack (SCIM, automatic), Google Workspace (delegated to manager, automatic, 30-day hold), GitHub/Salesforce/Atlassian (manual checklist). |
| `lambda/src/clients/google_workspace_client.py` | Mocked Google Workspace Admin SDK client (`delegate_inbox`, `rename_account`, `transfer_drive`, `create_hidden_group`, `schedule_deletion`) — no real Workspace credentials exist in this demo, so every method logs and returns a realistic mock response instead of calling a real API. |
| `lambda/src/offboarding_manager.py` | Reads `offboarding_config.json`, dispatches each app's configured action, collects manual-checklist items, and opens the **"Offboarding checklist — [name]"** GitHub issue. Records the pending removal (email, manager, removal date, issue number) to SSM for `scheduled_removal.py` to pick up later. |
| `lambda/src/scheduled_removal.py` | Second Lambda handler, deployed by `terraform/modules/scheduled_removal` (daily EventBridge schedule): reads pending removals from SSM, permanently deletes any Okta user past their hold period, comments completion back on the original checklist issue (and posts an informational Slack note), and logs days-remaining for everyone still in the window. |
| `lambda/src/access_review.py` | Standalone module (also a Lambda handler): fetches every active Okta user, flags group-membership/department mismatches and stale accounts (no login in 90+ days, or never logged in and created 7+ days ago), logs the full report, and opens a GitHub issue when there's anything to review. Implemented and unit-tested; no Terraform module deploys it yet. |
| `lambda/src/clients/slack_client.py`, `lambda-drift-auditor/src/slack_client.py` | `SlackClient.post_alert(channel, message, severity)` — posts to a Slack incoming webhook with a color-coded attachment (info/warning/critical). Two copies, one per independently-deployed Lambda package, same pattern as the duplicated `github_client.py`/`secret_store.py`. |
| `lambda-drift-auditor/` | `handler()` polls the Okta System Log every 15 minutes, classifies who made each change, logs to CloudWatch, opens a GitHub issue and posts a Slack alert for anything unexpected - and now also records that issue's number in SSM. It also classifies admin-privilege-grant events (`user.account.privilege.grant`, `user.mfa.factor.activate` against an admin-role target) separately, escalating any grant from an actor outside `KNOWN_AUTOMATION_ACTOR_IDS` immediately, and cross-checks every current Okta admin-role holder against `KNOWN_ADMIN_EMAILS` on every run - so an admin role granted before the auditor was even running still gets caught. `check_unacknowledged_escalations()`, a second entry point on its own 6-hour schedule, re-checks every recorded issue: closed ones drop off the list, anything still open past 24 hours gets a repeated Slack reminder. Fully implemented and unit-tested; secrets are fetched from SSM at runtime, never held in plain env vars. |
=======
| `terraform/modules/lambda_provisioning` | Provisioning Lambda function + IAM execution role (CloudWatch Logs, SSM read for the Okta token). |
| `terraform/modules/api_gateway` | HTTP API with a `POST /provision` route wired to the provisioning Lambda. |
| `terraform/modules/okta_drift_auditor` | `okta-drift-auditor` Lambda + IAM execution role (CloudWatch Logs, SSM read for both secrets) + a 15-minute EventBridge schedule. |
| `lambda/` | Provisioning Lambda (new-hire/termination webhook handler). Scaffolded — Terraform will deploy it, but the handler logic itself isn't written yet. |
| `lambda-drift-auditor/` | Polls the Okta System Log every 15 minutes, classifies who made each change, logs to CloudWatch, and opens a GitHub issue for anything unexpected. Fully implemented and unit-tested; secrets are fetched from SSM at runtime, never held in plain env vars. |
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)
| `.github/workflows/terraform-plan.yml` | On every PR to `main`: `fmt -check`, `validate`, `plan`, plan output posted as a PR comment. |
| `.github/workflows/terraform-apply.yml` | On every push to `main`: `apply -auto-approve`. |
| `.github/workflows/terraform-drift.yml` | Daily at 08:00 UTC: `terraform plan -detailed-exitcode`; opens a GitHub issue if anything has changed. |
| `docs/architecture.md` | Full system diagram and resource-ownership table. |
| `docs/drift-detection.md` | Drift types, the out-of-band shadow-resource audit, and the full governance loop with a worked example. |

## Implementation status

- **Done:** Okta groups, group rules, app assignments, and policies — implemented in Terraform and applied to a real Okta developer org.
- **Done:** Terraform Cloud remote backend, all three GitHub Actions workflows.
- **Done:** `okta-drift-auditor` Lambda — implemented and unit-tested (`pytest` in `lambda-drift-auditor/tests/`), including runtime SSM secret lookups (`secret_store.py`) instead of plain-text secret env vars.
- **Done:** AWS-side Terraform — `modules/lambda_provisioning` (Lambda + execution role), `modules/api_gateway` (HTTP API, `POST /provision`), and `modules/okta_drift_auditor` (Lambda + execution role + 15-minute EventBridge schedule) are all wired into the root module and validate cleanly (`terraform validate`).
<<<<<<< HEAD
- **Done:** Provisioning Lambda (`lambda/`) — `schema_validator.py` validates and normalizes every ADP payload before anything else touches Okta; `clients/okta_client.py` creates/activates/assigns new hires to groups and deactivates/unassigns terminated users, with all Okta API errors logged and re-raised. Unit-tested (`pytest` in `lambda/tests/`).
- **Done:** `modules/lambda_provisioning`'s IAM role now grants `ssm:GetParameter`/`kms:Decrypt` for both the Okta token and a GitHub token (`github_token_param_name`, default `/iam-demo/github-token`), and `GITHUB_TOKEN_PARAM_NAME`/`GITHUB_REPO` are wired through as environment variables - so `schema_validator.py`'s unknown-field GitHub issue path is no longer just tested in isolation, it's actually deployable.
- **Done:** `lambda/src/access_review.py` — fetches active users via a new `OktaClient.list_active_users()` (paginated) and `get_user_groups()`, cross-checks group membership against the `department` profile attribute using the same `DEPARTMENT_GROUP_MAP` the provisioning Lambda uses, flags stale accounts, logs the full report, and opens a `GitHub` issue when there's anything to review. Unit-tested (`pytest` in `lambda/tests/test_access_review.py`).
- **Done:** `terraform/modules/cloudwatch_dashboard` — one dashboard, nine widgets, wired into root `main.tf` behind `enable_aws_resources`.
- **Known gap:** the dashboard's three custom-metric widgets (access review findings count, failed ADP validations, orphaned account age) reference a `IAMAutomationDemo` CloudWatch namespace that nothing publishes to yet - no code in this repo calls `put_metric_data`. The widgets are real and will render once something does; until then they'll show no data.
- **Known gap:** `access_review.py` has no Terraform module deploying it (no Lambda resource, no IAM role, no schedule) - it's real, tested Python with nowhere to run yet. The dashboard's `access_review_lambda_function_name` variable (default `okta-access-review`) just names the function its widgets expect, in advance of that module existing.
- **Done:** the full offboarding expansion - `offboarding_config.json`, `google_workspace_client.py`, `offboarding_manager.py`, the rewired `termination.py` (Okta lockdown first, then per-app actions, then the checklist issue), and `scheduled_removal.py`. 21 new/updated tests across `lambda/tests/`, all passing.
- **Done:** Slack alerting - `slack_client.py` (duplicated into both Lambda packages, same pattern as the other shared clients) and every GitHub-issue-opening code path (drift auditor escalation + reminder, access review, offboarding checklist, ADP unknown-field alert, scheduled removal completion, admin-grant alerts) now also posts a matching Slack message.
- **Done:** every GitHub issue and Slack message in the project follows one consistent format - GitHub issues use `## What happened` (plain English) / `## What needs to happen` (numbered actions) / `## Technical details` / an optional `## Deadline`; Slack messages lead with a bold plain-English summary, then the action needed, then a link to the GitHub issue. Shared helpers live in `issue_format.py` (duplicated into both Lambda packages, same pattern as `slack_client.py`).
- **Done:** the Slack webhook SSM wiring gap is closed on both sides - `modules/lambda_provisioning` and `modules/okta_drift_auditor` both grant `ssm:GetParameter` for `SLACK_WEBHOOK_PARAM_NAME` (same default path, `/iam-demo/slack-webhook`, on both) and pass it through as an environment variable to every Lambda function in both modules. `modules/lambda_provisioning`'s IAM role also grants `ssm:GetParameter`/`PutParameter`/`DeleteParameter` for `PENDING_REMOVALS_PARAM_NAME`, and `terraform/modules/scheduled_removal` now deploys `scheduled_removal.py` (Lambda + execution role + daily EventBridge schedule), closing what was previously an open gap.
- **Done:** admin-privilege-grant detection - `lambda-drift-auditor/src/classifier.py` classifies `user.account.privilege.grant`/`user.mfa.factor.activate` events targeting an admin role, separately from the general drift classification. Any grant from an actor outside `KNOWN_AUTOMATION_ACTOR_IDS` opens its own high-priority GitHub issue and a red/urgent Slack alert (24-hour response deadline), regardless of whether the granted role touches a Terraform-managed resource. `handler()` also cross-checks every current Okta admin-role holder (`GET /api/v1/iam/assignees/users`) against a configurable `KNOWN_ADMIN_EMAILS` allow-list on every 15-minute run, catching admin roles granted before the auditor was ever deployed - already-escalated holders are deduplicated via an SSM-stored list (`REPORTED_ADMIN_ALERTS_PARAM_NAME`) so the same unresolved grant doesn't reopen an issue every run.
- **Done:** exponential backoff with jitter on `OktaClient._request()` - 429/5xx responses get retried up to 3 times (1s, 2s, 4s base delays + up to 500ms jitter) before raising `OktaApiError`; anything else (400/401/403/404) still raises on the first attempt, no retry. Covered by dedicated tests, including one that pins jitter to zero to assert the exact backoff sequence.
- **Done:** blast radius protection on the provisioning Lambda - `reserved_concurrent_executions = 10` in Terraform, plus a guard in `handler.py` that rejects (structured log + raised exception) any single invocation carrying more than 25 records rather than partially processing a runaway batch. This is also the first real implementation of `handler.py` itself - it was a placeholder until this pass, dispatching a single event or a `{"records": [...]}` batch to `new_hire`/`termination` by a top-level `event_type` field.
- **Done:** unacknowledged escalation follow-up - the drift auditor's `handler()` now records `{issue_number, title, opened_at}` to SSM on every escalation; a new `check_unacknowledged_escalations()` entry point (separate `aws_lambda_function`, same zip and role, 6-hour EventBridge schedule) re-checks each one's GitHub state and posts a Slack reminder (critical severity) for anything still open past 24 hours, repeating every 6 hours until closed.
- **Done:** multi-environment scaffold - `terraform/environments/dev` and `terraform/environments/prod`, each a fully independent root module (own `backend.tf` pointing at its own not-yet-created Terraform Cloud workspace, own `variables.tf`, a `main.tf` calling the same modules as root). Both validate (`terraform init -backend=false && terraform validate`) since neither workspace exists yet. See "Environment promotion pattern" below.
- **Known gap, called out on purpose:** this project only has one real Okta developer org. `environments/dev` and `environments/prod` both default `okta_org_name`/`okta_base_url` to that same org. A real dev/prod split needs either a second Okta org or clearly namespaced resource names per environment - applying both environments against the same org at the same time, unmodified, would fight over identically-named groups/apps. Documented in both environments' `variables.tf`, not hidden.
- **Not yet done:** an actual `terraform apply` of the AWS resources. All AWS modules are gated behind `enable_aws_resources` (default `false`, so the Okta-only config applies with no AWS credentials at all) — flipping it to `true` also needs real AWS credentials, a real `github_repo` value, and the SSM parameters (`/iam-automation-demo/okta/api_token`, `/iam-automation-demo/github/token`, and `/iam-demo/slack-webhook`) created out-of-band first — see [Setup from scratch](#setup-from-scratch).
- **Known gap, called out on purpose:** `access_review.py` still has no deploying Terraform module (no Lambda resource, no IAM role, no schedule) - only `scheduled_removal.py` and the admin-grant/admin-holder-audit logic (inside the already-deployed `okta_drift_auditor` module) were closed out this pass.
=======
- **In progress:** Provisioning Lambda (`lambda/`) — directory scaffolded, handler logic not yet written. The Terraform above will happily deploy it, but it won't do anything useful until that's implemented.
- **Not yet done:** an actual `terraform apply` of the AWS resources. That needs real AWS credentials, a real `github_repo` value, and the SSM parameters (`/iam-automation-demo/okta/api_token`, `/iam-automation-demo/github/token`) created out-of-band first — see [Setup from scratch](#setup-from-scratch).
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)

## Setup from scratch

1. **Okta developer org.** Sign up at [developer.okta.com](https://developer.okta.com/) and generate an API token under **Security → API → Tokens**. Note your org hostname — the subdomain is `okta_org_name`, `okta.com` is `okta_base_url`.

2. **Terraform Cloud.** Create a free account at [app.terraform.io](https://app.terraform.io/), an organization, and a workspace using the **CLI-driven workflow**. Set these as workspace variables:
   - `okta_org_name`, `okta_base_url` — plain Terraform variables.
   - `okta_api_token` — mark as **sensitive**.

3. **Local Terraform CLI.** Run `terraform login` to authenticate to Terraform Cloud. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars`, fill in real values (gitignored). From `terraform/`, run `init`, `plan`, `apply`.

4. **GitHub Actions secrets.** Add to **Settings → Secrets → Actions**:
   - `TF_API_TOKEN` — a Terraform Cloud team or organization token (not your personal user token).
   - `GH_TOKEN` — a GitHub PAT with `repo` scope, used by the drift auditor to open issues.

5. **Push to `main` or open a PR.** Plan runs on every PR, apply runs on merge, drift check runs daily at 08:00 UTC.

<<<<<<< HEAD
6. **Lambda deployment** (`modules/lambda_provisioning`, `modules/api_gateway`, `modules/okta_drift_auditor`, `modules/scheduled_removal`, `modules/cloudwatch_dashboard`) is opt-in and needs a few things the Okta-only setup above doesn't:
   - Set `enable_aws_resources = true` in `terraform.tfvars` — it defaults to `false`, so none of these four modules are created (all gated with `count = var.enable_aws_resources ? 1 : 0`) until you flip it. Note the dashboard's widgets for `access_review_function_name` (default `okta-access-review`) will render with no data until that Lambda actually exists - see the Access review section below.
   - AWS credentials for Terraform's `aws` provider (the default credential chain — environment variables, shared config, or an IAM role — works as-is).
   - Build the deployment zips first: `lambda/build.sh` and `lambda-drift-auditor/build.sh` each install dependencies and produce the `.zip` the corresponding Terraform module points at (`filebase64sha256` on a missing zip fails `plan`, not just `apply`).
   - Create the secrets **in SSM directly** before ever applying — Terraform only ever references their *names*, never their values, so it can't create them for you:
     ```
     aws ssm put-parameter --name /iam-automation-demo/okta/api_token --type SecureString --value <your Okta token>
     aws ssm put-parameter --name /iam-automation-demo/github/token --type SecureString --value <a GitHub PAT with issues:write>
     aws ssm put-parameter --name /iam-demo/slack-webhook --type SecureString --value <a Slack incoming webhook URL>
     ```
   - Set `github_repo` (in `terraform.tfvars`) to your real `owner/repo`.
   - Leave `known_automation_actor_ids` empty on first apply — you can't know the provisioning Lambda's or CI's Okta token actor IDs until they've actually made a call that shows up in the Okta System Log. Look those IDs up afterward and set the variable so the auditor stops flagging your own automation as manual changes.
   - Similarly, leave `known_admin_emails` empty until you know who your real Okta admins are, then populate it (comma-separated emails) — otherwise the periodic admin-role-holder audit will open an escalation for every legitimate admin on the very first run.
   - The auditor's `MANAGED_RESOURCE_IDS_JSON` env var defaults to `"{}"` (no `file()` reference — Terraform Cloud's remote runners can't reach `lambda-drift-auditor/managed_resources.json` relative to the module path). With it empty, the auditor doesn't skip anything - it evaluates *every* group/policy/app-assignment event org-wide, not just Terraform-managed ones - so run `terraform output -json` after every apply and push the resulting resource IDs into the deployed Lambda's environment yourself to narrow it back down to what Terraform actually manages.
=======
6. **Lambda deployment** (`modules/lambda_provisioning`, `modules/api_gateway`, `modules/okta_drift_auditor`) needs a few things the Okta-only setup above doesn't:
   - AWS credentials for Terraform's `aws` provider (the default credential chain — environment variables, shared config, or an IAM role — works as-is).
   - Build the deployment zips first: `lambda/build.sh` and `lambda-drift-auditor/build.sh` each install dependencies and produce the `.zip` the corresponding Terraform module points at (`filebase64sha256` on a missing zip fails `plan`, not just `apply`).
   - Create the two secrets **in SSM directly** before ever applying — Terraform only ever references their *names*, never their values, so it can't create them for you:
     ```
     aws ssm put-parameter --name /iam-automation-demo/okta/api_token --type SecureString --value <your Okta token>
     aws ssm put-parameter --name /iam-automation-demo/github/token --type SecureString --value <a GitHub PAT with issues:write>
     ```
   - Set `github_repo` (in `terraform.tfvars`) to your real `owner/repo`.
   - Leave `known_automation_actor_ids` empty on first apply — you can't know the provisioning Lambda's or CI's Okta token actor IDs until they've actually made a call that shows up in the Okta System Log. Look those IDs up afterward and set the variable so the auditor stops flagging your own automation as manual changes.
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)

## How the drift governance loop works

Two independent checks run continuously, answering different questions:

**`terraform-drift.yml` (daily, 08:00 UTC)** asks: *does the live Okta org still match the Terraform config?* Exit code `2` (changes found) opens a "Drift detected in Okta infrastructure" issue with the full plan output.

**`okta-drift-auditor` (every 15 minutes)** asks: *who made this change, and should they have?* It pulls recent Okta System Log events, filters for changes to Terraform-managed resources, and classifies the actor:

- Known automation token (provisioning Lambda or CI) → **approved**, logged only.
- Okta's own `System` actor (a dynamic group rule reacting to an HR-driven department change, e.g. a manager reassignment in Workday cascading to group membership) → **approved**, logged only.
<<<<<<< HEAD
- Anyone else (a human changing a managed resource directly) → **escalated**, opening a "Manual Okta change detected — review required" issue **and** a Slack alert (`#iam-alerts`, warning severity) with who, what, and when.

Every event that reaches classification gets a structured CloudWatch log entry regardless of outcome — full audit trail, including the changes that needed no action.

**Escalations don't just fire and forget.** Every time `handler()` opens a "Manual Okta change" issue, it also appends `{issue_number, title, opened_at}` to an SSM-stored list. A second entry point, `check_unacknowledged_escalations()`, runs every 6 hours (its own EventBridge rule, same Lambda deployment package and IAM role): it re-checks each recorded issue's state via the GitHub API, drops anything already closed off the list, and posts a Slack reminder (critical severity, with the issue title, link, and hours-open) for anything still open past 24 hours - repeating every 6 hours for as long as it stays open. An escalation nobody looked at doesn't just sit quietly in a GitHub issue list; it starts nagging.

**Admin access is watched separately, and more aggressively.** A grant of Okta admin privileges is high-impact enough to warrant its own path rather than folding it into the general drift classification above:

- On every 15-minute run, `handler()` also scans the same System Log pull for `user.account.privilege.grant`/`user.mfa.factor.activate` events whose target is an admin role - regardless of whether that role happens to be a Terraform-managed resource. A grant from an actor outside `KNOWN_AUTOMATION_ACTOR_IDS` opens its own "Administrator access granted" GitHub issue and posts a **red/urgent** Slack alert immediately, day or night, with a 24-hour response deadline.
- Separately, at the end of every run, it calls the Okta IAM API to list everyone who *currently* holds an admin role and compares that list against a configurable `KNOWN_ADMIN_EMAILS` allow-list. Anyone holding admin access who isn't on that list gets escalated the same way - this is what catches an admin role that was granted before the auditor was ever deployed, which the event-based check above structurally can't see (there's no System Log event to react to). Already-escalated holders are recorded to an SSM list (`REPORTED_ADMIN_ALERTS_PARAM_NAME`) so the same unresolved grant doesn't reopen a duplicate issue on every run - ongoing reminders for it come from the same 6-hour escalation follow-up loop described above.

## Access review: the check the other two can't do

Both drift checks above only fire off a *change* - a plan diff or a System Log
event. Some problems never produce either: an employee transferred
departments six months ago and their group membership just never got
updated, or an account nobody has touched (or logged into) in months is
still sitting there active. Nothing "changed" recently enough for the other
two loops to notice.

`lambda/src/access_review.py` closes that gap by not waiting for a change at
all - it periodically pulls every active user and checks their *current
state* directly:

- **Group/department mismatches**: a user in `eng-base` whose `department`
  isn't `"Engineering"` (and the reverse - `"Engineering"` but not in
  `eng-base`), same for `ops-base`/`"Operations"`.
- **Stale access**: no login in 90+ days, or never logged in and the account
  is more than 7 days old.

Every run logs the full report to CloudWatch regardless of findings, and
opens a **"Access review findings — manual review required"** GitHub issue
(with a Markdown table of every mismatch/stale account) only when there's
something to act on - same shape as the other two loops' escalation paths,
just checking state instead of watching for events.

## Offboarding: what happens when someone leaves

Termination isn't a single API call - it's a security step, then a fan-out
across every app that person had access to, most of which can't be
deprovisioned automatically. `provisioning/termination.py` runs the sequence
in this order, deliberately:

1. **Cut Okta access first.** `OktaClient.initiate_offboarding()` deactivates
   the user, clears every active session (`DELETE .../sessions`, revoking
   OAuth tokens too), renames their login to `<original>_deactivated`, and
   moves them into the `pending_removal` holding group - removed from every
   other group in the same step. Nothing below this runs until all of that
   has completed.
2. **Per-app actions, driven by `offboarding_config.json`** (`offboarding_manager.py`):
   - **Slack** - nothing to do here; it's SCIM-provisioned from Okta group
     membership, so step 1 already deprovisioned it.
   - **Google Workspace** - delegates the inbox to the manager, transfers
     Drive ownership, renames the account, creates a hidden group so mail
     keeps routing to the manager, and schedules deletion after the hold
     period (mocked - see `google_workspace_client.py`, no real Workspace
     credentials in this demo).
   - **GitHub, Salesforce, Atlassian** - none of these are automated; each
     is collected into a manual checklist item instead.
3. **Manager checklist issue.** One GitHub issue, **"Offboarding checklist —
   [name]"**, listing what was done automatically, a table of what the
   manager still has to do by hand (per-app instructions included), the
   data-review deadline, and the final removal date - all computed from the
   *same* hold period Okta's lockdown already committed to in step 1, so the
   two never drift apart.
4. **Record the pending removal.** Email, manager, removal date, and the
   checklist issue number get appended to an SSM-stored JSON list, for
   `scheduled_removal.py` to act on later.

**`scheduled_removal.py`** (a second Lambda, deployed by
`terraform/modules/scheduled_removal` on a daily EventBridge trigger) reads
that list every day: anyone past their removal date gets permanently deleted
from Okta, a completion comment posted back on their original checklist
issue, and an informational Slack note; everyone still inside the hold
window is left alone, with a log entry noting how many days are left.

## Admin role assignments

`terraform/modules/okta_admin_roles` manages Okta administrator role grants
(`SUPER_ADMIN`, `ORG_ADMIN`, `APP_ADMIN`, and the rest of the standard set)
declaratively, the same way groups and policies are managed - not through
the Okta admin console. The input is a flat list of `(user_email,
role_type)` pairs; since the underlying `okta_user_admin_roles` resource is
one-per-user (a list of roles, not one resource per role), the module groups
the flat list by email before creating anything, and looks up each email's
Okta user ID via a data source (the user must already exist - this module
doesn't create users).

It's wired into root `main.tf` with an **empty list by default** - granting
`SUPER_ADMIN` is high-impact enough that this project doesn't want to guess
at real admins' emails. A real plan against the actual Okta org confirms
this: with the empty default, the module creates nothing (verified with a
live `terraform plan`, not just `validate`). Populate `admin_assignments`
when you're ready to manage real grants.

Its role assignment IDs feed into `managed_resources.json` alongside
groups/apps/policies, so `okta-drift-auditor` treats an out-of-band admin
role change (someone granting themselves `SUPER_ADMIN` directly in the Okta
console) exactly like any other unauthorized change to a Terraform-managed
resource - logged, classified, and escalated if it wasn't the provisioning
Lambda or CI that did it.

Tested with Terraform's native test framework (`terraform test` +
`mock_provider "okta" {}`) rather than Python - this validates the module's
actual HCL (grouping logic, resource count, role-list contents) without
needing a real Okta user to look up, since `mock_provider` fabricates
placeholder values for the `data "okta_user"` lookup instead of calling the
real API.

## Environment promotion pattern

`terraform/environments/dev/` and `terraform/environments/prod/` are
separate root modules - each with its own `backend.tf` pointing at its own
Terraform Cloud workspace (`iam-automation-demo-dev`,
`iam-automation-demo-prod`), its own `variables.tf`, and a `main.tf` that
calls the exact same modules as the original root `terraform/main.tf`, just
from one directory deeper (`../../modules/...` instead of `./modules/...`).

**Neither workspace has been created yet - that's a manual step.** Before
either environment can be applied:

1. Create the `iam-automation-demo-dev` and `iam-automation-demo-prod`
   workspaces in the `jangus-iam-demo` Terraform Cloud organization (same
   process as the original workspace - see [Setup from scratch](#setup-from-scratch)
   step 2), using the CLI-driven workflow.
2. Set each workspace's own variables (`okta_api_token` as sensitive,
   `github_repo`, etc.) - they don't inherit anything from the root
   workspace or from each other.
3. `cd terraform/environments/dev && terraform init && terraform plan`
   (and the equivalent for `prod`) once its workspace exists.

**The intended promotion flow, once both workspaces exist:** a change lands
in `terraform/modules/*` or in one environment's own config, gets applied to
**dev first**, gets reviewed there (does the plan look right, does the
change actually behave correctly against dev's Okta org), and only then
gets applied to **prod** - the same change, promoted, not re-derived. In
practice that means: open a PR touching the shared modules → CI plans
against whichever workspace(s) are wired to run in CI → apply to dev →
confirm it's correct → apply the identical, already-reviewed config to prod.
The value of separate workspaces is that dev mistakes can't touch prod
state, and prod never runs anything that wasn't already proven in dev first.

**Honest gap, not papered over:** this demo has exactly one real Okta
developer org, so both environments' `variables.tf` currently default
`okta_org_name`/`okta_base_url` to that same org. Since Terraform state is
separate per workspace but the *target Okta org* would be the same, actually
applying both environments unmodified, at the same time, would create
duplicate/conflicting groups and apps in that one org. A real dev/prod split
needs either a second Okta org (the clean fix) or environment-namespaced
resource names (e.g. `dev-eng-base` vs `eng-base`) if a second org isn't an
option. This scaffold demonstrates the *structure* of environment
separation - the workspaces, the backend/variable isolation, the promotion
flow - without yet solving the "one Okta org" problem, since that requires
either spending real money on a second org or a naming-convention change
this pass didn't make.
=======
- Anyone else (a human changing a managed resource directly) → **escalated**, opening a "Manual Okta change detected — review required" issue with who, what, and when.

Every event that reaches classification gets a structured CloudWatch log entry regardless of outcome — full audit trail, including the changes that needed no action.
>>>>>>> f0e70ef (feat: add drift auditor Lambda, AWS Terraform modules, GitHub Actions drift workflow, updated docs)
