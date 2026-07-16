import json
import os

DEFAULT_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "..", "managed_resources.json")


def load_managed_resource_ids():
    """Return the set of Okta resource IDs Terraform currently manages.

    Preferred source is the MANAGED_RESOURCE_IDS_JSON env var (a JSON string),
    so the Lambda can be updated with fresh IDs without a redeploy. Falls back
    to the bundled managed_resources.json config file otherwise. Either way,
    this should be regenerated from `terraform output -json` after every
    apply - see the "Keeping managed_resources.json current" section in the
    root README for how that's wired up.
    """
    raw_env = os.environ.get("MANAGED_RESOURCE_IDS_JSON")
    if raw_env:
        data = json.loads(raw_env)
    else:
        config_path = os.environ.get("MANAGED_RESOURCES_CONFIG_PATH", DEFAULT_CONFIG_PATH)
        with open(config_path) as fh:
            data = json.load(fh)

    ids = set()
    for value in data.values():
        if isinstance(value, dict):
            ids.update(value.values())
        elif isinstance(value, list):
            ids.update(value)
        elif isinstance(value, str):
            ids.add(value)
    return ids
