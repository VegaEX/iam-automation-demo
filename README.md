# IAM Automation Demo

Terraform owns the Okta baseline. Lambda handles provisioning events. GitHub Actions runs the pipeline. Two separate auditing loops verify the live org matches what's declared, and a third checks every active user periodically for access that's quietly gone wrong.

This isn't a greenfield demo : it's a rebuild of patterns from a real IAM environment, rewritten with the architecture I'd use if I were starting from scratch.

See `docs/architecture.md` for the full system diagram and `docs/drift-detection.md` for a deep dive on the drift governance loop.

## What this demonstrates

- Okta managed as code: groups, group rules, app assignments, policies, and admin roles all declared in Terraform. Console changes are drift.
- Event-driven provisioning from ADP: schema validation and normalization before any Okta API call, dead letter queue for failures, exponential backoff on retries.
- A real CI/CD pipeline: plan posted as a PR comment, apply on merge, daily drift check that opens a GitHub issue if anything diverges.
- Two drift detection approaches that answer different questions: does the live org match config, and did an authorized actor make each change.
- Periodic access review that catches what event-driven detection misses: accounts nobody changed but that have quietly become wrong.

## Components

| Path | What it does |
|------|-------------|
| `terraform/` | Root config: providers, variables, Terraform Cloud backend, module wiring. |
| `terraform/modules/okta_groups` | `eng-base`, `ops-base`, `it-base`, `all-staff`, `pending_removal` : plus dynamic group rules assigning users by `department` attribute. |
| `terraform/modules/okta_app_assignments` | Bookmark apps and group-to-app assignments. |
| `terraform/modules/okta_policies` | MFA enrollment policy and admin sign-on policy. |
| `terraform/modules/okta_admin_roles` | Declarative admin role grants. Empty by default : granting `SUPER_ADMIN` is high-impact enough that nothing is assumed. Tested with `terraform test` and `mock_provider`. |
| `terraform/environments/dev`, `terraform/environments/prod` | Separate root modules per environment, each with its own Terraform Cloud workspace and variables. See environment promotion pattern below. |
| `terraform/modules/lambda_provisioning` | Lambda function and IAM execution role. `reserved_concurrent_executions = 10` caps blast radius. |
| `terraform/modules/api_gateway` | HTTP API with `POST /provision` routed to the provisioning Lambda. |
| `terraform/modules/okta_drift_auditor` | Two Lambdas on one deployment package: `okta-drift-auditor` runs every 15 minutes, `okta-drift-auditor-escalation-check` runs every 6 hours. |
| `terraform/modules/scheduled_removal` | Daily Lambda for 30-day hold processing and permanent deletion. |
| `terraform/modules/cloudwatch_dashboard` | Nine-widget CloudWatch dashboard, version controlled like everything else. |
| `lambda/` | Provisioning Lambda: ADP schema validation, Okta user lifecycle, full offboarding sequence. `handler.py` rejects batches over 25 records. `okta_client.py` retries 429 and 5xx with exponential backoff and jitter. |
| `lambda/src/offboarding_config.json` | Per-app termination behavior. Adding a new app is a config change, not a code change. |
| `lambda/src/clients/google_workspace_client.py` | Mocked Workspace client: inbox delegation, Drive transfer, hidden group creation, account rename. No real credentials in this demo. |
| `lambda/src/offboarding_manager.py` | Reads the offboarding config, dispatches per-app actions, generates the manager checklist GitHub issue, records the pending removal to SSM. |
| `lambda/src/scheduled_removal.py` | Daily Lambda: reads pending removals from SSM, permanently deletes users past their hold period, posts completion back to the original checklist issue. |
| `lambda/src/access_review.py` | Pulls every active user, checks group membership against department attribute, flags stale accounts, opens a GitHub issue when findings exist. Implemented and tested; no Terraform module deploys it yet. |
| `lambda/src/clients/slack_client.py`, `lambda-drift-auditor/src/slack_client.py` | Webhook alerts with severity-coded colors. Duplicated per Lambda package, same pattern as the other shared clients. |
| `lambda-drift-auditor/` | 15-minute System Log polling, actor classification, admin grant detection, admin role holder audit against `KNOWN_ADMIN_EMAILS`, unacknowledged escalation follow-up every 6 hours. Secrets fetched from SSM at runtime. |
| `.github/workflows/terraform-plan.yml` | PR to main: fmt check, validate, plan, plan posted as comment. |
| `.github/workflows/terraform-apply.yml` | Push to main: apply. |
| `.github/workflows/terraform-drift.yml` | Daily 08:00 UTC: plan, open issue if anything changed. |
| `docs/architecture.md` | Full system diagram and resource ownership table. |
| `docs/drift-detection.md` | Drift types, shadow resource audit, governance loop with worked example. |

## Implementation status

**Done:**
- Okta groups, rules, app assignments, and policies : live in a real Okta developer org.
- Terraform Cloud remote backend, all three GitHub Actions workflows.
- Drift auditor Lambda : implemented, unit-tested, runtime SSM secret fetching.
- AWS-side Terraform modules : lambda_provisioning, api_gateway, okta_drift_auditor : wired and validated.
- Provisioning Lambda : schema validation, normalization, Okta user lifecycle, full test coverage.
- Access review Lambda : department/group mismatch detection, stale account flagging, unit-tested.
- CloudWatch dashboard module : nine widgets behind `enable_aws_resources`.
- Full offboarding pipeline : per-app config, Google Workspace mock, manager checklist, 30-day hold, scheduled deletion.
- Slack alerting across all GitHub-issue-opening code paths.
- Consistent alert format: plain-English summary up top, numbered actions, technical details below. Shared helpers in `issue_format.py`.
- Slack webhook and SSM permissions wired on both Lambda sides.
- Admin grant detection: event-based (System Log) and state-based (current role holder audit), with SSM-backed deduplication.
- Exponential backoff with jitter on all Okta API calls.
- Blast radius protection: concurrency cap in Terraform, record count guard in handler.
- Unacknowledged escalation follow-up every 6 hours until closed.
- Multi-environment scaffold: dev and prod with separate backends and variables.

**Known gaps, called out rather than papered over:**
- CloudWatch custom metric widgets (access review findings, failed ADP validations, orphaned account age) reference a namespace nothing publishes to yet. Widgets are real; data requires `put_metric_data` calls to exist.
- `access_review.py` has no deploying Terraform module. Real, tested Python locally. Would need to transition into Lambda.
- Both environment configs default to the same Okta org. Applying both simultaneously would create conflicting resources. A real split into DEV and PROD is ready to go.
- AWS resources haven't been applied as they are behind an irritating paywall. All AWS modules gate behind `enable_aws_resources = false`. See setup below for what's needed to flip it.

## Setup from scratch

**1. Okta developer org.**
Sign up at [developer.okta.com](https://developer.okta.com/), generate an API token under Security → API → Tokens. Note the org subdomain (`okta_org_name`) and `okta.com` as `okta_base_url`.

**2. Terraform Cloud.**
Create a free account at [app.terraform.io](https://app.terraform.io/), an organization, and a CLI-driven workspace. Set workspace variables:
- `okta_org_name`, `okta_base_url` : plain Terraform variables.
- `okta_api_token` : sensitive.

**3. Local Terraform.**
Run `terraform login`. Copy `terraform/terraform.tfvars.example` to `terraform/terraform.tfvars` and fill in real values (gitignored). From `terraform/`, run `init`, `plan`, `apply`.

**4. GitHub Actions secrets.**
Add to Settings → Secrets → Actions:
- `TF_API_TOKEN` : Terraform Cloud team or organization token, not your personal user token.
- `GH_TOKEN` : GitHub PAT with `repo` scope.

**5. Push to main or open a PR.**
Plan runs on every PR, apply runs on merge, drift check runs daily at 08:00 UTC.

**6. Lambda deployment (opt-in).**
Set `enable_aws_resources = true`. Also needed:
- AWS credentials for Terraform's `aws` provider.
- Deployment zips built first: `lambda/build.sh` and `lambda-drift-auditor/build.sh`.
- SSM parameters created out-of-band before applying:
  ```
  aws ssm put-parameter --name /iam-automation-demo/okta/api_token --type SecureString --value <token>
  aws ssm put-parameter --name /iam-automation-demo/github/token --type SecureString --value <pat>
  aws ssm put-parameter --name /iam-demo/slack-webhook --type SecureString --value <webhook-url>
  ```
- `github_repo` set to your `owner/repo`.
- Leave `known_automation_actor_ids` empty on first apply : you won't know the Lambda's Okta actor ID until it's made a call. Look it up in the System Log afterward.
- Leave `known_admin_emails` empty until you know who your actual admins are. Populating it wrong on first apply will escalate every legitimate admin.
- `MANAGED_RESOURCE_IDS_JSON` defaults to `{}`. Run `terraform output -json` after every apply and push the resource IDs into the deployed Lambda's environment to narrow the auditor's scope.

## How the drift governance loop works

Two loops, two questions:

**`terraform-drift.yml` (daily, 08:00 UTC):** does the live Okta org still match what Terraform declared? Exit code 2 opens a GitHub issue with the full plan output. Plain-English format: what happened, what to do, technical details.

**`okta-drift-auditor` (every 15 minutes):** who made this change, and should they have? Pulls Okta System Log events, filters for managed resources, classifies the actor:
- Known automation token → approved, logged only.
- Okta System actor (dynamic group rule reacting to an HR event) → approved, logged only.
- Anyone else → escalated: GitHub issue opened, red Slack alert posted.

Every classified event gets a CloudWatch log entry regardless of outcome.

Escalations don't close themselves. When an issue opens, the issue number and timestamp go into SSM. `check_unacknowledged_escalations()` runs every 6 hours, checks whether each recorded issue is still open, and posts a Slack reminder for anything open past 24 hours : repeating until it's closed.

Admin access gets its own path. A privilege grant is high-impact enough to handle separately:
- Every 15-minute run scans for `user.account.privilege.grant` events targeting an admin role. Any grant from an actor outside `KNOWN_AUTOMATION_ACTOR_IDS` opens a separate high-priority GitHub issue and posts a red Slack alert with a 24-hour response requirement.
- Every run also checks who currently holds an admin role against `KNOWN_ADMIN_EMAILS`. Anyone not on that list gets escalated the same way. This catches grants that predated the auditor : there's no System Log event to react to, so state-based checking is the only way to find them. Already-escalated holders are tracked in SSM so the same grant doesn't reopen a duplicate issue every run.

## Access review

Both drift loops fire off a change. Some problems never produce one : a department transfer six months ago that never updated group membership, or an account nobody has touched in months. `access_review.py` handles this by pulling every active user and checking current state directly:

- Group/department mismatches: eng-base with department not "Engineering," ops-base with department not "Operations," and the reverse.
- Stale access: no login in 90+ days, or never logged in and created more than 7 days ago.

Full report logged to CloudWatch every run. GitHub issue opened only when there's something to act on.

## Offboarding

Termination is a sequence, not a single call. The order matters:

1. **Cut Okta access first.** Deactivate, clear sessions (OAuth tokens included), rename to `username_deactivated`, move to `pending_removal`, remove from everything else. Nothing below this runs until this completes.

2. **Per-app actions from `offboarding_config.json`.** Slack: already handled by step 1 via SCIM. Google Workspace: inbox delegated to manager, Drive transferred, hidden group created for ongoing mail routing, deletion scheduled (mocked : no real credentials). GitHub, Salesforce, Atlassian: manual checklist items, not automated by design.

3. **Manager checklist issue.** What was automated, what needs human attention per app, 30-day data review deadline, final deletion date.

4. **Pending removal recorded to SSM** for `scheduled_removal.py` to pick up daily.

`scheduled_removal.py` runs daily: anyone past their removal date gets permanently deleted from Okta, completion posted to the original checklist issue, informational Slack note sent. Everyone still in the window gets a log entry with days remaining.

## Admin role assignments

`terraform/modules/okta_admin_roles` manages admin role grants the same way groups are managed : declaratively, not through the console. Input is a flat list of `(user_email, role_type)` pairs. Empty by default. Granting `SUPER_ADMIN` without knowing who you're granting it to is not a default this project makes.

Role assignment IDs feed into `managed_resources.json` so the drift auditor treats out-of-band admin grants the same as any other unauthorized change to a managed resource.

## Environment promotion pattern

`terraform/environments/dev/` and `terraform/environments/prod/` are independent root modules : separate backends, separate Terraform Cloud workspaces, same shared modules. Neither workspace exists yet; that's a manual step.

Intended flow: change lands in `terraform/modules/*`, applies to dev, gets reviewed, then applies to prod. Same config, promoted, not re-derived.

Honest gap: both environments default to the same Okta org. Applying both simultaneously would fight over identically-named resources. A real split needs a second org or namespaced names. The scaffold shows the structure : workspace isolation, backend separation, promotion flow : without solving the one-org problem.
