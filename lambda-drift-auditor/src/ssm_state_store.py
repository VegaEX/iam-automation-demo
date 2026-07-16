import json

import boto3

_ssm_client = None


def _ssm():
    # Lazy for the same reason as secret_store._ssm() - constructing the
    # client at import time requires a resolvable AWS region, which breaks
    # in any environment without one configured (e.g. the test suite).
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def get_json_list(parameter_name):
    """Return the JSON list stored at this SSM parameter (plain String, not
    a secret), or an empty list if the parameter doesn't exist yet."""
    try:
        response = _ssm().get_parameter(Name=parameter_name)
    except _ssm().exceptions.ParameterNotFound:
        return []
    return json.loads(response["Parameter"]["Value"])


def put_json_list(parameter_name, records):
    """Overwrite the JSON list stored at this SSM parameter."""
    _ssm().put_parameter(
        Name=parameter_name,
        Value=json.dumps(records),
        Type="String",
        Overwrite=True,
    )


# Named aliases for the open-escalations use case specifically - same
# generic list storage as above, kept as their own names at call sites
# since "get_open_escalations" reads clearer there than "get_json_list".
get_open_escalations = get_json_list
put_open_escalations = put_json_list
