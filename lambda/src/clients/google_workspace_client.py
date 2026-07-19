import json
import logging
import os

logger = logging.getLogger()
logger.setLevel(os.environ.get("LOG_LEVEL", "INFO"))


class GoogleWorkspaceClient:
    """Mocked Google Workspace Admin SDK client.

    This is a demo environment with no real Google Workspace credentials or
    API access - every method below logs a structured entry and returns a
    realistic-looking mock response instead of making a real API call. Swap
    these method bodies for actual Admin SDK calls (google-api-python-client,
    authenticated via a service account) once real credentials exist.
    """

    def delegate_inbox(self, user_email, manager_email):
        """Grant the manager delegate access to the departed user's inbox."""
        result = {
            "action": "delegate_inbox",
            "user_email": user_email,
            "delegate_email": manager_email,
            "status": "DELEGATION_ACTIVE",
        }
        logger.info(json.dumps({"google_workspace_action": result}))
        return result

    def rename_account(self, user_email, new_username):
        """Rename the account so the original address can be reused."""
        result = {
            "action": "rename_account",
            "user_email": user_email,
            "new_username": new_username,
            "status": "RENAMED",
        }
        logger.info(json.dumps({"google_workspace_action": result}))
        return result

    def transfer_drive(self, user_email, manager_email):
        """Transfer ownership of the departed user's Drive files to their manager."""
        result = {
            "action": "transfer_drive",
            "user_email": user_email,
            "new_owner_email": manager_email,
            "status": "TRANSFER_QUEUED",
        }
        logger.info(json.dumps({"google_workspace_action": result}))
        return result

    def create_hidden_group(self, user_email, manager_email):
        """Create a hidden distribution group at the departed user's address
        so incoming mail keeps routing to their manager after the account
        itself is renamed/removed."""
        result = {
            "action": "create_hidden_group",
            "group_email": user_email,
            "forwards_to": manager_email,
            "status": "GROUP_CREATED",
        }
        logger.info(json.dumps({"google_workspace_action": result}))
        return result

    def schedule_deletion(self, user_email, days=30):
        """Mark the account for deletion once the data-review hold period elapses."""
        result = {
            "action": "schedule_deletion",
            "user_email": user_email,
            "hold_days": days,
            "status": "DELETION_SCHEDULED",
        }
        logger.info(json.dumps({"google_workspace_action": result}))
        return result
