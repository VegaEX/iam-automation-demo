import os

# Okta System Log actor.type values seen in this org: "User" (a live person in
# the admin console), "SSWS" (an API token - what both the provisioning Lambda
# and the Terraform/CI pipeline authenticate as), and "System" (Okta's own
# internal automation, e.g. a dynamic group rule re-evaluating membership
# after a profile attribute changes). Verify these against the current Okta
# System Log API reference before relying on them in production - actor.type
# values aren't exhaustively documented and can vary by org configuration.
SYSTEM_ACTOR_TYPE = "System"


def _known_automation_actor_ids():
    raw = os.environ.get("KNOWN_AUTOMATION_ACTOR_IDS", "")
    return {value.strip() for value in raw.split(",") if value.strip()}


def classify_event(log_event):
    """Classify a single Okta System Log event as one of:

    - "approved_automation": made by a known service actor (the provisioning
      Lambda's API token or the Terraform/CI API token), listed in the
      KNOWN_AUTOMATION_ACTOR_IDS env var.
    - "approved_hr_pattern": made by Okta's own System actor - e.g. a dynamic
      group rule moving a user between eng-base/ops-base because HR updated
      their department attribute. Expected, not drift.
    - "manual_review_required": made by anything else, i.e. a live human
      changing a Terraform-managed resource directly.
    """
    actor = log_event.get("actor", {}) or {}
    actor_id = actor.get("id")
    actor_type = actor.get("type")

    if actor_id in _known_automation_actor_ids():
        return "approved_automation"

    if actor_type == SYSTEM_ACTOR_TYPE:
        return "approved_hr_pattern"

    return "manual_review_required"
