# IAM Automation Demo

A working demo of IAM-as-code for Okta. Terraform owns the declarative baseline (groups, dynamic group rules, app assignments, policies), a Lambda handles real-time HR provisioning events, GitHub Actions and Terraform Cloud run the CI/CD pipeline, and a second Lambda plus a scheduled workflow continuously verify that the live Okta org matches what's declared — and that any change that doesn't match came from an authorized source.

See `docs/architecture.md` for the full system diagram and `docs/drift-detection.md` for a deep dive on the drift governance loop.

## What this demonstrates

- Managing an identity provider (Okta) as code, including dynamic attribute-based group membership, not just static resources.
- Event-driven provisioning (HR system → API Gateway → Lambda → Okta) kept separate from, but consistent with, the Terraform-managed baseline.
- A real CI/CD pipeline for infrastructure: plan-on-PR with a posted plan comment, apply-on-merge, and a remote Terraform Cloud backend.
- Two complementary drift detection approaches: whether live state still matches config, and whether every change to a managed resource came from an authorized actor.

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
| `lambda/` | Provisioning Lambda (new-hire/termination webhook handler). Implemented and unit-tested: ADP payload validation/normalization (`schema_validator.py`), an `OktaClient` (`clients/okta_client.py`) that creates/activates/assigns users on hire and deactivates/unassigns them on termination, all secrets fetched from SSM at runtime. |
| `lambda-drift-auditor/` | Polls the Okta System Log every 15 minutes, classifies who made each change, logs to CloudWatch, and opens a GitHub issue for anything unexpected. Fully implemented and unit-tested; secrets are fetched from SSM at runtime, never held in plain env vars. |
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
- **Not yet done:** an actual `terraform apply` of the AWS resources. All three AWS modules are gated behind `enable_aws_resources` (default `false`, so the Okta-only config applies with no AWS credentials at all) — flipping it to `true` also needs real AWS credentials, a real `github_repo` value, and the SSM parameters (`/iam-automation-demo/okta/api_token`, `/iam-automation-demo/github/token`) created out-of-band first — see [Setup from scratch](#setup-from-scratch).

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

6. **Lambda deployment** (`modules/lambda_provisioning`, `modules/api_gateway`, `modules/okta_drift_auditor`) is opt-in and needs a few things the Okta-only setup above doesn't:
   - Set `enable_aws_resources = true` in `terraform.tfvars` — it defaults to `false`, so none of these three modules are created (all gated with `count = var.enable_aws_resources ? 1 : 0`) until you flip it.
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
- Anyone else (a human changing a managed resource directly) → **escalated**, opening a "Manual Okta change detected — review required" issue with who, what, and when.

Every event that reaches classification gets a structured CloudWatch log entry regardless of outcome — full audit trail, including the changes that needed no action.
