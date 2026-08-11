"""Publish a locally-created website (tools/website_tools.py) somewhere
actually reachable online — level 2 of website creation.

Free/default path: push the site's files to a GitHub repo via the REST API
and enable Pages on it. Needs GITHUB_PAGES_TOKEN (a personal access token
with 'repo' scope — https://github.com/settings/tokens) and
GITHUB_PAGES_OWNER (a GitHub username or org). Only registers as a tool
when both are set (see tools/registry_builder.py).

Infomaniak (paid, Swiss hosting) is the planned alternative but isn't built
yet — it needs SFTP support (paramiko), a real dependency choice worth
confirming before adding rather than pulling in silently.
"""
from __future__ import annotations

import base64
from pathlib import Path

import httpx

from core.config import config
from core.store import Store
from tools.base import Tool

_GITHUB_API = "https://api.github.com"


def _github_headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {config.github_pages_token}",
        "Accept": "application/vnd.github+json",
    }


def _site_files(site_dir: Path) -> list[Path]:
    """Every file that should actually be published — everything except
    the internal manifest, which is bookkeeping for tools/website_tools.py
    and has no meaning to a browser."""
    return [p for p in site_dir.rglob("*") if p.is_file() and p.name != "_site.json"]


class PublishWebsiteToGithubPagesTool(Tool):
    name = "publish_website_to_github_pages"
    description = (
        "Publish a website (created with create_website) to GitHub Pages, for free — creates a "
        "GitHub repo named after the site if one doesn't already exist, pushes its files, and "
        "enables Pages. Returns the live URL. Can take a minute to actually go live after this "
        "returns, that's normal."
    )
    input_schema = {
        "type": "object",
        "properties": {"site_name": {"type": "string"}},
        "required": ["site_name"],
    }

    def __init__(self, store: Store):
        self._store = store

    def run(self, site_name: str) -> str:
        doc = self._store.get_document(site_name)
        if not doc or doc.kind != "website":
            return f"No website named '{site_name}'. Use create_website first."

        site_dir = Path(doc.path)
        owner = config.github_pages_owner
        repo = site_name

        repo_response = httpx.get(f"{_GITHUB_API}/repos/{owner}/{repo}", headers=_github_headers(), timeout=15)
        if repo_response.status_code == 404:
            create_response = httpx.post(
                f"{_GITHUB_API}/user/repos",
                headers=_github_headers(),
                json={
                    "name": repo,
                    "auto_init": True,
                    "description": f"Published by Orion from the local site '{site_name}'.",
                },
                timeout=15,
            )
            if create_response.status_code >= 300:
                return f"Could not create repo '{owner}/{repo}': {create_response.text[:300]}"
        elif repo_response.status_code >= 300:
            return f"Could not look up repo '{owner}/{repo}': {repo_response.text[:300]}"

        for file_path in _site_files(site_dir):
            relative = file_path.relative_to(site_dir).as_posix()
            content_b64 = base64.b64encode(file_path.read_bytes()).decode()

            existing = httpx.get(
                f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{relative}",
                headers=_github_headers(),
                timeout=15,
            )
            body = {"message": f"Publish {relative} via Orion", "content": content_b64}
            if existing.status_code == 200:
                body["sha"] = existing.json()["sha"]

            put_response = httpx.put(
                f"{_GITHUB_API}/repos/{owner}/{repo}/contents/{relative}",
                headers=_github_headers(),
                json=body,
                timeout=30,
            )
            if put_response.status_code >= 300:
                return f"Failed to upload '{relative}': {put_response.text[:300]}"

        pages_response = httpx.post(
            f"{_GITHUB_API}/repos/{owner}/{repo}/pages",
            headers=_github_headers(),
            json={"source": {"branch": "main", "path": "/"}},
            timeout=15,
        )
        # 409 means Pages is already enabled on this repo — not an error.
        if pages_response.status_code >= 300 and pages_response.status_code != 409:
            return f"Files uploaded, but couldn't enable Pages: {pages_response.text[:300]}"

        return f"Published to https://{owner}.github.io/{repo}/ (may take a minute to go live)."
