"""GitHub API client for repo-ctl."""

import requests
from datetime import datetime, timezone
from typing import List, Optional, Dict

GITHUB_API = "https://api.github.com"


class GitHubClient:

    def __init__(self, token: str, org: str = "k4rlski"):
        self.token = token
        self.org = org
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        })

    def _get(self, path: str, params: dict = None) -> dict:
        r = self.session.get(f"{GITHUB_API}{path}", params=params)
        r.raise_for_status()
        return r.json()

    def _get_all(self, path: str, params: dict = None) -> list:
        """Paginate through all results."""
        params = params or {}
        params["per_page"] = 100
        results = []
        page = 1
        while True:
            params["page"] = page
            r = self.session.get(f"{GITHUB_API}{path}", params=params)
            r.raise_for_status()
            data = r.json()
            if not data:
                break
            results.extend(data)
            if len(data) < 100:
                break
            page += 1
        return results

    def list_repos(self) -> List[dict]:
        """List all repos for the user."""
        return self._get_all(f"/users/{self.org}/repos")

    def get_repo(self, repo: str) -> dict:
        return self._get(f"/repos/{self.org}/{repo}")

    def list_issues(self, repo: str, state: str = "open") -> List[dict]:
        return self._get_all(f"/repos/{self.org}/{repo}/issues", {"state": state})

    def list_all_issues(self, repos: List[str], state: str = "open") -> Dict[str, List[dict]]:
        result = {}
        for repo in repos:
            try:
                issues = self.list_issues(repo, state=state)
                if issues:
                    result[repo] = issues
            except Exception:
                pass
        return result

    def get_tree(self, repo: str, branch: str = "main") -> List[dict]:
        """Get flat file tree for a repo."""
        try:
            data = self._get(f"/repos/{self.org}/{repo}/git/trees/{branch}", {"recursive": "1"})
            return data.get("tree", [])
        except Exception:
            return []

    def get_file_content(self, repo: str, path: str) -> Optional[str]:
        """Fetch raw file content from GitHub."""
        try:
            import base64
            data = self._get(f"/repos/{self.org}/{repo}/contents/{path}")
            return base64.b64decode(data["content"]).decode("utf-8")
        except Exception:
            return None

    def get_commits(self, repo: str, count: int = 5) -> List[dict]:
        try:
            return self._get_all(f"/repos/{self.org}/{repo}/commits")[:count]
        except Exception:
            return []

    def create_issue(self, repo: str, title: str, body: str, labels: List[str] = None) -> dict:
        data = {"title": title, "body": body}
        if labels:
            data["labels"] = labels
        r = self.session.post(f"{GITHUB_API}/repos/{self.org}/{repo}/issues", json=data)
        r.raise_for_status()
        return r.json()
