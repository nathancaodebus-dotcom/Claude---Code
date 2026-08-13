"""Watch a GitHub repo's latest releases/commits — public API, works without
auth (rate-limited to 60 req/hour); set GITHUB_WATCH_TOKEN for 5000/hour."""
from __future__ import annotations

import httpx

from core.config import config
from core.http import client
from tools.base import Tool


def _headers() -> dict[str, str]:
    headers = {"Accept": "application/vnd.github+json"}
    if config.github_token:
        headers["Authorization"] = f"Bearer {config.github_token}"
    return headers


class LatestGithubReleaseTool(Tool):
    name = "get_latest_github_release"
    description = "Get the latest release of a GitHub repo, e.g. owner='anthropics', repo='claude-code'."
    input_schema = {
        "type": "object",
        "properties": {"owner": {"type": "string"}, "repo": {"type": "string"}},
        "required": ["owner", "repo"],
    }

    def run(self, owner: str, repo: str) -> str:
        response = client.get(
            f"https://api.github.com/repos/{owner}/{repo}/releases/latest",
            headers=_headers(),
            timeout=10,
        )
        if response.status_code == 404:
            return f"No releases found for {owner}/{repo}."
        response.raise_for_status()
        data = response.json()
        return f"{data['tag_name']} — {data['name']} (published {data['published_at']})\n{data.get('html_url', '')}"


class RecentGithubCommitsTool(Tool):
    name = "get_recent_github_commits"
    description = "Get the most recent commits on a GitHub repo's default branch."
    input_schema = {
        "type": "object",
        "properties": {
            "owner": {"type": "string"},
            "repo": {"type": "string"},
            "max_results": {"type": "integer", "description": "Default 5."},
        },
        "required": ["owner", "repo"],
    }

    def run(self, owner: str, repo: str, max_results: int = 5) -> str:
        response = client.get(
            f"https://api.github.com/repos/{owner}/{repo}/commits",
            params={"per_page": max_results},
            headers=_headers(),
            timeout=10,
        )
        response.raise_for_status()
        commits = response.json()
        if not commits:
            return f"No commits found for {owner}/{repo}."

        lines = []
        for c in commits:
            message = c["commit"]["message"].splitlines()[0]
            author = c["commit"]["author"]["name"]
            lines.append(f"- {c['sha'][:7]} {message} — {author}")
        return "\n".join(lines)
