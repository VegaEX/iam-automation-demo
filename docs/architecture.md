# Architecture

This project has three moving parts that all touch the same Okta org from
different angles:

1. A **real-time provisioning path** — Workday pushes new-hire/termination
   events, a Lambda acts on them immediately.
2. A **declarative baseline** — Terraform owns the org's groups, group rules,
   app assignments, and policies as code, applied through GitHub Actions.
3. A **drift governance loop** — a second Lambda and a scheduled GitHub Action
   both watch for the baseline and the real world falling out of sync, from
   two different angles (see the note at the end of this doc).

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
  Lambda: provisioning  (lambda/, deployed by terraform/modules/lambda_provisioning)
        │
        │  reads its Okta token from SSM at invocation time (execution role
        │  has ssm:GetParameter on /iam-automation-demo/okta/api_token only -
        │  the token's value never appears in Terraform config, state, or a
        │  plain Lambda environment variable)
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
              1. deactivate_user(email) - looks the user up by email first;
                 not found is logged as a warning and returns cleanly, not
                 an error (the account may already be gone)
              2. remove_from_all_groups() - every group except Okta's
                 built-in Everyone group
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
        │         "Manual Okta change detected — review required"       │
        │                                                               │
        └─── slow path: daily at 08:00 UTC ─────────────────────────────┘
             GitHub Actions: terraform-drift.yml
               1. terraform plan -detailed-exitcode   (against real Okta)
               2. exit code 2 (changes found) -> open a GitHub Issue
                  "Drift detected in Okta infrastructure",
                  full plan output attached
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

## Resource ownership

| Concern                                   | Owned by                          |
|--------------------------------------------|------------------------------------|
| User lifecycle (create/deactivate)         | `lambda/` provisioning Lambda      |
| Group/group-rule/app-assignment/policy config | Terraform (`terraform/`)        |
| Provisioning Lambda + its HTTP trigger     | `terraform/modules/lambda_provisioning`, `terraform/modules/api_gateway` |
| Drift auditor Lambda + its schedule        | `terraform/modules/okta_drift_auditor` |
| Terraform state                            | Terraform Cloud (`jangus-iam-demo`)|
| CI/CD for the above                        | GitHub Actions                     |
| Secret values (Okta token, GitHub token)   | SSM Parameter Store (SecureString) — created out-of-band, never in Terraform config/state; each Lambda's IAM role can read only the parameter(s) it needs |
| "Was this change authorized?" audit        | `lambda-drift-auditor/`            |
| "Does reality match config?" audit         | `terraform-drift.yml`              |
