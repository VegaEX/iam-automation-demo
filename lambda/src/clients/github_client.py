import requests


class GitHubClient:
    """Thin wrapper around the GitHub Issues REST API."""

    def __init__(self, token, repo):
        self.repo = repo
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def create_issue(self, title, body):
        url = f"https://api.github.com/repos/{self.repo}/issues"
        response = requests.post(
            url,
            headers=self.headers,
            json={"title": title, "body": body},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def add_comment(self, issue_number, body):
        url = f"https://api.github.com/repos/{self.repo}/issues/{issue_number}/comments"
        response = requests.post(
            url,
            headers=self.headers,
            json={"body": body},
            timeout=10,
        )
        response.raise_for_status()
        return response.json()
