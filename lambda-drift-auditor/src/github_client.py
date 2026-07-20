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

    def get_issue(self, issue_number):
        url = f"https://api.github.com/repos/{self.repo}/issues/{issue_number}"
        response = requests.get(url, headers=self.headers, timeout=10)
        response.raise_for_status()
        return response.json()
