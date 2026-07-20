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


# Event types that can carry an admin role grant as their target. Admin
# privilege escalation gets its own detection path, separate from
# classify_event() above - there's no "approved_hr_pattern" equivalent for an
# admin grant the way there is for department-driven group membership; any
# admin grant not made by known automation is inherently suspicious.
ADMIN_PRIVILEGE_EVENT_TYPES = {
    "user.account.privilege.grant",
    # user.mfa.factor.activate is an unusual inclusion here - it's normally
    # an MFA enrollment event, not an admin role change, and isn't otherwise
    # documented as carrying an admin-role target. Included because it was
    # explicitly requested; verify against real Okta System Log payloads
    # whether it ever actually carries an admin-role target before relying
    # on it as a signal in production.
    "user.mfa.factor.activate",
}


# Standard Okta admin role display names, used to recognize an admin-role
# target precisely - deliberately not a loose "admin" substring match, since
# that would also match an ordinary person's target displayName (e.g. a user
# literally named "Jane Admin"). Verify this list against the current Okta
# role reference before relying on it in production; role names/labels can
# change or vary by org configuration.
KNOWN_ADMIN_ROLE_DISPLAY_NAMES = {
    "super administrator",
    "organization administrator",
    "application administrator",
    "user administrator",
    "help desk administrator",
    "read-only administrator",
    "report administrator",
    "group administrator",
    "group membership administrator",
    "api access management administrator",
    "mobile administrator",
}


def _is_admin_role_target(target):
    # Okta System Log target entries for privilege grants are documented (at
    # time of writing) with an admin-role-shaped type (e.g. "AdminRoleTarget")
    # and the role name in displayName - verify the exact shape against a
    # real event before relying on this in production; this is a heuristic,
    # not a confirmed schema.
    target_type = (target.get("type") or "").lower().replace("_", "").replace(" ", "")
    display_name = (target.get("displayName") or "").lower()
    return "adminrole" in target_type or display_name in KNOWN_ADMIN_ROLE_DISPLAY_NAMES


def is_admin_privilege_event(log_event):
    """True if this event's type is one that can carry an admin role grant,
    AND its target list actually names an admin role - not just any event
    of a matching type."""
    if log_event.get("eventType") not in ADMIN_PRIVILEGE_EVENT_TYPES:
        return False

    return any(_is_admin_role_target(t) for t in log_event.get("target", []) or [])


def find_admin_role_target(log_event):
    """Return the target entry that names the admin role in a privilege
    grant event, or None if none of its targets look like one."""
    for target in log_event.get("target", []) or []:
        if _is_admin_role_target(target):
            return target
    return None


def classify_admin_privilege_event(log_event):
    """Classify who granted an admin privilege:

    - "admin_grant_known_automation": a known service actor (e.g. Terraform/
      CI applying a declared grant via terraform/modules/okta_admin_roles).
      Expected.
    - "admin_grant_unknown_actor": anyone else. Not expected - there's no
      legitimate "Okta System actor" reason for an admin grant to happen on
      its own the way there is for department-driven group membership, so
      this always needs a human to look at it.
    """
    actor = log_event.get("actor", {}) or {}
    if actor.get("id") in _known_automation_actor_ids():
        return "admin_grant_known_automation"
    return "admin_grant_unknown_actor"
