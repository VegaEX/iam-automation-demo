import boto3

_ssm_client = None


def _ssm():
    # Lazy so importing this module never requires a resolvable AWS region -
    # constructing the client at import time breaks in any environment
    # without one configured (e.g. running the test suite locally).
    global _ssm_client
    if _ssm_client is None:
        _ssm_client = boto3.client("ssm")
    return _ssm_client


def get_secret(parameter_name):
    """Fetch a SecureString value from SSM Parameter Store at call time.

    Secrets are never held in plain-text environment variables - the
    Lambda's env vars only carry the parameter *name*, and the execution
    role is granted ssm:GetParameter (plus kms:Decrypt) scoped to exactly
    the parameters it needs. See terraform/modules/okta_drift_auditor.

    Named secret_store, not secrets, so it doesn't shadow the stdlib
    `secrets` module - this package's src/ dir sits directly on sys.path.
    """
    response = _ssm().get_parameter(Name=parameter_name, WithDecryption=True)
    return response["Parameter"]["Value"]
