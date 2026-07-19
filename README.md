# IAM Automation Demo

A working demo of IAM-as-code for Okta. Terraform owns the declarative baseline (groups, dynamic group rules, app assignments, policies), a Lambda handles real-time HR provisioning events — including a full multi-app offboarding sequence on termination — GitHub Actions and Terraform Cloud run the CI/CD pipeline, a second Lambda plus a scheduled workflow continuously verify that the live Okta org matches what's declared, and a third Lambda periodically audits every active user for group/department mismatches and stale access.

See `docs/architecture.md` for the full system diagram and `docs/drift-detection.md` for a deep dive on the drift governance loop.

## What this demonstrates

- Managing an identity provider (Okta) as code, including dynamic attribute-based group membership, not just static resources.
- Event-driven provisioning (HR system → API Gateway → Lambda → Okta) kept separate from, but consistent with, the Terraform-managed baseline.
- A real CI/CD pipeline for infrastructure: plan-on-PR with a posted plan comment, apply-on-merge, and a remote Terraform Cloud backend.
- Two complementary drift detection approaches: whether live state still matches config, and whether every change to a managed resource came from an authorized actor.
- A periodic access review that catches what event-driven drift detection can't: accounts nobody actively changed, but that have quietly become wrong or stale over time.

## Components

| Path | What it is |
|------|------------|
| `terraform/` | Root Terraform config: providers, variables, Terraform Cloud backend, and module wiring for Okta groups, app assignments, and policies. |
| `terraform/modules/okta_groups` | `eng-base`, `ops-base`, `it-base`, `all-staff` groups, plus dynamic group rules assigning users based on their `department` profile attribute. |
| `terraform/modules/okta_app_assignments` | Bookmark apps (Slack, GitHub, AWS SSO, Salesforce) and group-to-app assignments. |
| `terraform/modules/okta_policies` | MFA enrollment policy (org-wide) and an admin sign-on policy requiring MFA for `ops-base`. |
| `terraform/modules/lambda_provisioning` | Provisioning Lambda function + IAM execution role (CloudWatch Logs, SSM read for the Okta token). |
| `terraform/modules/api_gateway` | HTTP API with a `POST /provision` route wired to the provisioning Lambda. |
| `terraform/modules/okta_drift_auditor` | `okta-drift-auditor` Lambda + IAM execution role (CloudWatch Logs, SSM read for both secrets) + a 15-minute EventBridge schedule. |
| `terraform/modules/cloudwatch_dashboard` | A single `aws_cloudwatch_dashboard` covering all three Lambdas' invocations/errors/duration, plus three custom-metric widgets nothing publishes to yet (see Implementation status). |
| `lambda/` | Provisioning Lambda (new-hire/termination webhook handler). Implemented and unit-tested: ADP payload validation/normalization (`schema_validator.py`), an `OktaClient` (`clients/okta_client.py`) that creates/activates/assigns new hires and, on termination, immediately deactivates/clears sessions/renames/holds the departing user before handing off to the offboarding flow below. |
| `lambda/src/offboarding_config.json` | Per-app termination behavior: Slack (SCIM, automatic), Google Workspace (delegated to manager, automatic, 30-day hold), GitHub/Salesforce/Atlassian (manual checklist). |
| `lambda/src/clients/google_workspace_client.py` | Mocked Google Workspace Admin SDK client (`delegate_inbox`, `rename_account`, `transfer_drive`, `create_hidden_group`, `schedule_deletion`) — no real Workspace credentials exist in this demo, so every method logs and returns a realistic mock response instead of calling a real API. |
| `lambda/src/offboarding_manager.py` | Reads `offboarding_config.json`, dispatches each app's configured action, collects manual-checklist items, and opens the **"Offboarding checklist — [name]"** GitHub issue. Records the pending removal (email, manager, removal date, issue number) to SSM for `scheduled_removal.py` to pick up later. |
| `lambda/src/scheduled_removal.py` | Second Lambda handler (daily EventBridge, once deployed): reads pending removals from SSM, permanently deletes any Okta user past their hold period, comments completion back on the original checklist issue, and logs days-remaining for everyone still in the window. No Terraform module deploys it yet. |
| `lambda/src/access_review.py` | Standalone module (also a Lambda handler): fetches every active Okta user, flags group-membership/department mismatches and stale accounts (no login in 90+ days, or never logged in and created 7+ days ago), logs the full report, and opens a GitHub issue when there's anything to review. Implemented and unit-tested; no Terraform module deploys it yet. |
| `lambda/src/clients/slack_client.py`, `lambda-drift-auditor/src/slack_client.py` | `SlackClient.post_alert(channel, message, severity)` — posts to a Slack incoming webhook with a color-coded attachment (info/warning/critical). Two copies, one per independently-deployed Lambda package, same pattern as the duplicated `github_client.py`/`secret_store.py`. |
| `lambda-drift-auditor/` | Polls the Okta System Log every 15 minutes, classifies who made each change, logs to CloudWatch, opens a GitHub issue and posts a Slack alert for anything unexpected. Fully implemented and unit-tested; secrets are fetched from SSM at runtime, never held in plain env vars. |
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
- **Done:** Provisioning Lambda (`lambda/`) — `schema_validator.py` validates and normalizes every ADP payload before anything else touches Okta; `clients/okta_client.py` creates/activates/assigns new hires to groups and deactivates/unassigns terminated users, with all Okta API errors logged and re-raised. Unit-tested (`pytest` in `lambda/tests/`).
- **Done:** `modules/lambda_provisioning`'s IAM role now grants `ssm:GetParameter`/`kms:Decrypt` for both the Okta token and a GitHub token (`github_token_param_name`, default `/iam-demo/github-token`), and `GITHUB_TOKEN_PARAM_NAME`/`GITHUB_REPO` are wired through as environment variables - so `schema_validator.py`'s unknown-field GitHub issue path is no longer just tested in isolation, it's actually deployable.
- **Done:** `lambda/src/access_review.py` — fetches active users via a new `OktaClient.list_active_users()` (paginated) and `get_user_groups()`, cross-checks group membership against the `department` profile attribute using the same `DEPARTMENT_GROUP_MAP` the provisioning Lambda uses, flags stale accounts, logs the full report, and opens a `GitHub` issue when there's anything to review. Unit-tested (`pytest` in `lambda/tests/test_access_review.py`).
- **Done:** `terraform/modules/cloudwatch_dashboard` — one dashboard, nine widgets, wired into root `main.tf` behind `enable_aws_resources`.
- **Known gap:** the dashboard's three custom-metric widgets (access review findings count, failed ADP validations, orphaned account age) reference a `IAMAutomationDemo` CloudWatch namespace that nothing publishes to yet - no code in this repo calls `put_metric_data`. The widgets are real and will render once something does; until then they'll show no data.
- **Known gap:** `access_review.py` has no Terraform module deploying it (no Lambda resource, no IAM role, no schedule) - it's real, tested Python with nowhere to run yet. The dashboard's `access_review_lambda_function_name` variable (default `okta-access-review`) just names the function its widgets expect, in advance of that module existing.
- **Done:** the full offboarding expansion - `offboarding_config.json`, `google_workspace_client.py`, `offboarding_manager.py`, the rewired `termination.py` (Okta lockdown first, then per-app actions, then the checklist issue), and `scheduled_removal.py`. 21 new/updated tests across `lambda/tests/`, all passing.
- **Done:** Slack alerting - `slack_client.py` (duplicated into both Lambda packages, same pattern as the other shared clients) and the drift auditor now posts to Slack alongside its GitHub issue on every escalation.
- **Known gap:** none of this new AWS-side plumbing is wired into Terraform yet. Specifically: `modules/lambda_provisioning`'s IAM role and environment don't grant `ssm:GetParameter`/`PutParameter` for a `PENDING_REMOVALS_PARAM_NAME` parameter (read *and* written by `offboarding_manager.py`/`scheduled_removal.py`); neither Lambda's role grants `ssm:GetParameter` for a `SLACK_WEBHOOK_URL_PARAM_NAME`; and `scheduled_removal.py`, like `access_review.py`, has no deploying Terraform module (no Lambda resource, no IAM role, no daily EventBridge schedule) at all. All of this code is real and tested against mocks - none of it can run in AWS yet.
- **Not yet done:** an actual `terraform apply` of the AWS resources. All AWS modules are gated behind `enable_aws_resources` (default `false`, so the Okta-only config applies with no AWS credentials at all) — flipping it to `true` also needs real AWS credentials, a real `github_repo` value, and the SSM parameters (`/iam-automation-demo/okta/api_token`, `/iam-automation-demo/github/token`) created out-of-band first — see [Setup from scratch](#setup-from-scratch).

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

6. **Lambda deployment** (`modules/lambda_provisioning`, `modules/api_gateway`, `modules/okta_drift_auditor`, `modules/cloudwatch_dashboard`) is opt-in and needs a few things the Okta-only setup above doesn't:
   - Set `enable_aws_resources = true` in `terraform.tfvars` — it defaults to `false`, so none of these four modules are created (all gated with `count = var.enable_aws_resources ? 1 : 0`) until you flip it. Note the dashboard's widgets for `access_review_function_name` (default `okta-access-review`) will render with no data until that Lambda actually exists - see the Access review section below.
   - AWS credentials for Terraform's `aws` provider (the default credential chain — environment variables, shared config, or an IAM role — works as-is).
   - Build the deployment zips first: `lambda/build.sh` and `lambda-drift-auditor/build.sh` each install dependencies and produce the `.zip` the corresponding Terraform module points at (`filebase64sha256` on a missing zip fails `plan`, not just `apply`).
   - Create the two secrets **in SSM directly** before ever applying — Terraform only ever references their *names*, never their values, so it can't create them for you:
     ```
     aws ssm put-parameter --name /iam-automation-demo/okta/api_token --type SecureString --value <your Okta token>
     aws ssm put-parameter --name /iam-automation-demo/github/token --type SecureString --value <a GitHub PAT with issues:write>
     ```
   - Set `github_repo` (in `terraform.tfvars`) to your real `owner/repo`.
   - Leave `known_automation_actor_ids` empty on first apply — you can't know the provisioning Lambda's or CI's Okta token actor IDs until they've actually made a call that shows up in the Okta System Log. Look those IDs up afterward and set the variable so the auditor stops flagging your own automation as manual changes.
   - The auditor's `MANAGED_RESOURCE_IDS_JSON` env var defaults to `"{}"` (no `file()` reference — Terraform Cloud's remote runners can't reach `lambda-drift-auditor/managed_resources.json` relative to the module path). With it empty, the auditor doesn't skip anything - it evaluates *every* group/policy/app-assignment event org-wide, not just Terraform-managed ones - so run `terraform output -json` after every apply and push the resulting resource IDs into the deployed Lambda's environment yourself to narrow it back down to what Terraform actually manages.

## How the drift governance loop works

Two independent checks run continuously, answering different questions:

**`terraform-drift.yml` (daily, 08:00 UTC)** asks: *does the live Okta org still match the Terraform config?* Exit code `2` (changes found) opens a "Drift detected in Okta infrastructure" issue with the full plan output.

**`okta-drift-auditor` (every 15 minutes)** asks: *who made this change, and should they have?* It pulls recent Okta System Log events, filters for changes to Terraform-managed resources, and classifies the actor:

- Known automation token (provisioning Lambda or CI) → **approved**, logged only.
- Okta's own `System` actor (a dynamic group rule reacting to an HR-driven department change, e.g. a manager reassignment in Workday cascading to group membership) → **approved**, logged only.
- Anyone else (a human changing a managed resource directly) → **escalated**, opening a "Manual Okta change detected — review required" issue **and** a Slack alert (`#iam-alerts`, warning severity) with who, what, and when.

Every event that reaches classification gets a structured CloudWatch log entry regardless of outcome — full audit trail, including the changes that needed no action.

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

**`scheduled_removal.py`** (a second Lambda, daily EventBridge trigger once
deployed) reads that list every day: anyone past their removal date gets
permanently deleted from Okta and a completion comment posted back on their
original checklist issue; everyone still inside the hold window is left
alone, with a log entry noting how many days are left.
