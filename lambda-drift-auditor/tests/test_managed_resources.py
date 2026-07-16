import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from managed_resources import load_managed_resource_ids  # noqa: E402


def test_loads_from_env_var_when_set(monkeypatch):
    monkeypatch.setenv(
        "MANAGED_RESOURCE_IDS_JSON",
        json.dumps({"group_ids": {"eng-base": "00gabc123"}, "policy_ids": ["00pxyz789"]}),
    )

    ids = load_managed_resource_ids()

    assert ids == {"00gabc123", "00pxyz789"}


def test_falls_back_to_config_file(monkeypatch, tmp_path):
    monkeypatch.delenv("MANAGED_RESOURCE_IDS_JSON", raising=False)
    config_file = tmp_path / "managed_resources.json"
    config_file.write_text(json.dumps({"app_ids": {"Slack": "0oaabc123"}}))
    monkeypatch.setenv("MANAGED_RESOURCES_CONFIG_PATH", str(config_file))

    ids = load_managed_resource_ids()

    assert ids == {"0oaabc123"}
