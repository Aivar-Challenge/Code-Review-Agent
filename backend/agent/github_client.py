"""
GitHub REST API v3 client.
Handles: PR metadata, diff fetch, file listing, existing review comments.
"""
import re
import logging
from typing import Any
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from backend.config import settings

logger = logging.getLogger("agent.github")


class GitHubClient:
    def __init__(self, token: str | None = None):
        self.token = token or settings.github_token
        self.base_url = settings.github_api_base
        self._client: httpx.AsyncClient | None = None

    @property
    def headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github.v3+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self.headers,
            timeout=60.0,
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    def parse_pr_url(self, pr_url: str) -> tuple[str, str, int]:
        """
        Parse a GitHub PR URL into (owner, repo, pr_number).
        Supports: https://github.com/owner/repo/pull/123
        """
        pattern = r"github\.com/([^/]+)/([^/]+)/pull/(\d+)"
        match = re.search(pattern, pr_url)
        if not match:
            raise ValueError(f"Invalid GitHub PR URL: {pr_url}")
        owner, repo, pr_number = match.groups()
        return owner, repo, int(pr_number)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_pull_request(self, owner: str, repo: str, pr_number: int) -> dict:
        """Fetch PR metadata."""
        resp = await self._client.get(f"/repos/{owner}/{repo}/pulls/{pr_number}")
        resp.raise_for_status()
        return resp.json()

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_pr_diff(self, owner: str, repo: str, pr_number: int) -> str:
        """Fetch the unified diff of the PR."""
        headers = {**self.headers, "Accept": "application/vnd.github.v3.diff"}
        resp = await self._client.get(
            f"/repos/{owner}/{repo}/pulls/{pr_number}",
            headers=headers,
        )
        resp.raise_for_status()
        return resp.text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[dict]:
        """Fetch list of changed files with patch info."""
        files = []
        page = 1
        while True:
            resp = await self._client.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            files.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return files

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=1, max=10))
    async def get_existing_review_comments(
        self, owner: str, repo: str, pr_number: int
    ) -> list[dict]:
        """Fetch all existing review comments on the PR for deduplication."""
        comments = []
        page = 1
        while True:
            resp = await self._client.get(
                f"/repos/{owner}/{repo}/pulls/{pr_number}/comments",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            batch = resp.json()
            if not batch:
                break
            comments.extend(batch)
            if len(batch) < 100:
                break
            page += 1
        return comments

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str | None:
        """Fetch raw file content at a specific ref (for context injection)."""
        try:
            resp = await self._client.get(
                f"/repos/{owner}/{repo}/contents/{path}",
                params={"ref": ref},
                headers={**self.headers, "Accept": "application/vnd.github.v3.raw"},
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.text
        except Exception as e:
            logger.warning(f"Could not fetch {path}@{ref}: {e}")
            return None

    async def create_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        comments: list[dict],
        event: str = "COMMENT",
        body: str = "",
    ) -> dict:
        """
        Create a GitHub review with inline comments.
        event: APPROVE | REQUEST_CHANGES | COMMENT
        """
        payload = {
            "commit_id": commit_id,
            "body": body,
            "event": event,
            "comments": comments,
        }
        resp = await self._client.post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()

    async def create_review_comment(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        commit_id: str,
        path: str,
        position: int,
        body: str,
    ) -> dict:
        """Post a single inline review comment."""
        payload = {
            "body": body,
            "commit_id": commit_id,
            "path": path,
            "position": position,
        }
        resp = await self._client.post(
            f"/repos/{owner}/{repo}/pulls/{pr_number}/comments",
            json=payload,
        )
        resp.raise_for_status()
        return resp.json()
