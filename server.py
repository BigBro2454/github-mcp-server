"""
GitHub MCP Server for BigBro2454
================================
A local MCP server built with FastMCP that exposes GitHub tools
scoped to BigBro2454's account. Designed to run via stdio transport
in Claude Desktop.

Usage:
    python server.py              # Run with stdio (for Claude Desktop)
    python server.py --dev        # Run with MCP Inspector for testing
"""

import json
import sys
import os

# Ensure the server's own directory is on the path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from fastmcp import FastMCP

from github_client import GitHubClient

# Load .env for local development
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ── Initialize ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "GitHub Personal",
    instructions="MCP server for interacting with BigBro2454's GitHub repos, PRs, and commits.",
)

_client: GitHubClient | None = None


def _get_client() -> GitHubClient:
    """Lazily initialize the GitHub client on first tool call."""
    global _client
    if _client is None:
        _client = GitHubClient()
    return _client


def _format(data) -> str:
    """Pretty-print dicts/lists as JSON for readable tool output."""
    if isinstance(data, (dict, list)):
        return json.dumps(data, indent=2, ensure_ascii=False)
    return str(data)


# ── Repo Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
def list_my_repos(
    visibility: str = "all",
    sort: str = "updated",
    language: str | None = None,
) -> str:
    """List all of BigBro2454's GitHub repositories.

    Args:
        visibility: Filter by visibility — "all", "public", or "private".
        sort: Sort order — "updated", "created", "pushed", or "full_name".
        language: Optional filter by primary language (e.g. "Python", "TypeScript").
    """
    repos = _get_client().list_repos(visibility=visibility, sort=sort, language=language)
    if not repos:
        return "No repositories found matching the given filters."
    return _format(repos)


@mcp.tool()
def get_repo_info(repo_name: str) -> str:
    """Get detailed information about a specific BigBro2454 repository.

    Args:
        repo_name: Repository name (e.g. "my-project"). No need to include the owner.
    """
    return _format(_get_client().get_repo_info(repo_name))


@mcp.tool()
def list_branches(repo_name: str) -> str:
    """List all branches for a BigBro2454 repository.

    Args:
        repo_name: Repository name (e.g. "my-project").
    """
    branches = _get_client().list_branches(repo_name)
    if not branches:
        return "No branches found."
    return _format(branches)


@mcp.tool()
def get_file_contents(
    repo_name: str,
    file_path: str,
    ref: str | None = None,
) -> str:
    """Read a file or list a directory from a BigBro2454 repository.

    Args:
        repo_name: Repository name (e.g. "my-project").
        file_path: Path to the file or directory within the repo.
        ref: Optional git ref (branch, tag, or commit SHA). Defaults to the repo's default branch.
    """
    return _format(_get_client().get_file_contents(repo_name, file_path, ref=ref))


# ── Pull Request Tools ────────────────────────────────────────────────────────


@mcp.tool()
def list_pull_requests(
    repo_name: str,
    state: str = "open",
) -> str:
    """List pull requests for a BigBro2454 repository.

    Args:
        repo_name: Repository name (e.g. "my-project").
        state: PR state filter — "open", "closed", or "all".
    """
    prs = _get_client().list_pull_requests(repo_name, state=state)
    if not prs:
        return f"No {state} pull requests found."
    return _format(prs)


@mcp.tool()
def get_pull_request(repo_name: str, pr_number: int) -> str:
    """Get detailed information about a specific pull request.

    Args:
        repo_name: Repository name (e.g. "my-project").
        pr_number: The PR number (e.g. 42).
    """
    return _format(_get_client().get_pull_request(repo_name, pr_number))


@mcp.tool()
def get_pr_diff(repo_name: str, pr_number: int) -> str:
    """Get the full unified diff for a pull request — all file changes as a patch.

    Args:
        repo_name: Repository name (e.g. "my-project").
        pr_number: The PR number.
    """
    diff = _get_client().get_pr_diff(repo_name, pr_number)
    return diff if diff else "No changes found in this PR."


@mcp.tool()
def get_pr_files(repo_name: str, pr_number: int) -> str:
    """List all files changed in a pull request with their status and patches.

    Args:
        repo_name: Repository name (e.g. "my-project").
        pr_number: The PR number.
    """
    files = _get_client().get_pr_files(repo_name, pr_number)
    if not files:
        return "No files changed in this PR."
    return _format(files)


@mcp.tool()
def list_pr_comments(repo_name: str, pr_number: int) -> str:
    """List all comments (issue comments and inline review comments) on a pull request.

    Args:
        repo_name: Repository name (e.g. "my-project").
        pr_number: The PR number.
    """
    comments = _get_client().list_pr_comments(repo_name, pr_number)
    if not comments:
        return "No comments on this PR."
    return _format(comments)


# ── Commit Tools ──────────────────────────────────────────────────────────────


@mcp.tool()
def list_recent_commits(
    repo_name: str,
    branch: str | None = None,
    limit: int = 10,
) -> str:
    """List recent commits on a branch of a BigBro2454 repository.

    Args:
        repo_name: Repository name (e.g. "my-project").
        branch: Branch name. Defaults to the repo's default branch.
        limit: Maximum number of commits to return (default 10, max 50).
    """
    limit = min(limit, 50)
    commits = _get_client().list_recent_commits(repo_name, branch=branch, limit=limit)
    if not commits:
        return "No commits found."
    return _format(commits)


@mcp.tool()
def get_commit_details(repo_name: str, sha: str) -> str:
    """Get full details and diff for a specific commit.

    Args:
        repo_name: Repository name (e.g. "my-project").
        sha: The commit SHA (full or abbreviated).
    """
    return _format(_get_client().get_commit_details(repo_name, sha))


@mcp.tool()
def compare_branches(repo_name: str, base: str, head: str) -> str:
    """Compare two branches or refs — shows ahead/behind counts, changed files, and commits.

    Args:
        repo_name: Repository name (e.g. "my-project").
        base: Base branch or ref (e.g. "main").
        head: Head branch or ref (e.g. "develop").
    """
    return _format(_get_client().compare_branches(repo_name, base, head))


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
