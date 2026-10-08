"""
GitHub MCP Server for BigBro2454
================================
A production-grade local MCP server built with FastMCP that exposes GitHub tools
scoped to BigBro2454's account. Designed to run via stdio transport
in Claude Desktop, Antigravity, or Cursor.

Features:
- Scoped to BigBro2454 namespace with 18 high-fidelity tools
- Multi-stage security guardrails & path traversal protection
- Outbound credential leak interception & redacting
- Token-bucket rate limiting for GitHub API quota preservation
- Real-time tool execution telemetry & latency SLA profiling
- Repository governance security audits & automated release notes

Usage:
    python server.py              # Run with stdio (for Claude Desktop / Antigravity)
    python server.py --dev        # Run with MCP Inspector for testing
"""

import json
import sys
import os
from functools import wraps

# Ensure the server's own directory is on the path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
from fastmcp import FastMCP

from github_client import GitHubClient
from guardrails import guardrails
from telemetry import telemetry

# Load .env for local development
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

# ── Initialize ────────────────────────────────────────────────────────────────

mcp = FastMCP(
    "GitHub Personal",
    instructions="Production MCP server for interacting with BigBro2454's GitHub repos, PRs, commits, governance audits, and release notes.",
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


def _gate(tool_name: str, cost: float = 1.0):
    """Decorator applying rate limiting, wall-clock telemetry profiling, and payload accounting."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if cost > 0.0:
                allowed, reason = guardrails.check_rate_limit(tool_name, cost=cost)
                if not allowed:
                    return _format({
                        "error": "RATE_LIMIT_EXCEEDED",
                        "tool": tool_name,
                        "message": reason,
                    })

            with telemetry.profile(tool_name):
                result = fn(*args, **kwargs)
                telemetry.record_payload(tool_name, str(result))
                return result
        return wrapper
    return decorator


# ── Repo Tools ────────────────────────────────────────────────────────────────


@mcp.tool()
@_gate("list_my_repos")
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
@_gate("get_repo_info")
def get_repo_info(repo_name: str) -> str:
    """Get detailed information about a specific BigBro2454 repository.

    Args:
        repo_name: Repository name (e.g. "my-project"). No need to include the owner.
    """
    return _format(_get_client().get_repo_info(repo_name))


@mcp.tool()
@_gate("list_branches")
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
@_gate("get_file_contents")
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
    is_safe, reason = guardrails.validate_file_path(file_path)
    if not is_safe:
        return _format({
            "error": "SECURITY_POLICY_VIOLATION",
            "message": reason,
            "path": file_path,
        })
    return _format(_get_client().get_file_contents(repo_name, file_path, ref=ref))


# ── Pull Request Tools ────────────────────────────────────────────────────────


@mcp.tool()
@_gate("list_pull_requests")
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
@_gate("get_pull_request")
def get_pull_request(repo_name: str, pr_number: int) -> str:
    """Get detailed information about a specific pull request.

    Args:
        repo_name: Repository name (e.g. "my-project").
        pr_number: The PR number (e.g. 42).
    """
    return _format(_get_client().get_pull_request(repo_name, pr_number))


@mcp.tool()
@_gate("get_pr_diff")
def get_pr_diff(repo_name: str, pr_number: int) -> str:
    """Get the full unified diff for a pull request — all file changes as a patch.

    Args:
        repo_name: Repository name (e.g. "my-project").
        pr_number: The PR number.
    """
    diff = _get_client().get_pr_diff(repo_name, pr_number)
    return diff if diff else "No changes found in this PR."


@mcp.tool()
@_gate("get_pr_files")
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
@_gate("list_pr_comments")
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
@_gate("list_recent_commits")
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
@_gate("get_commit_details")
def get_commit_details(repo_name: str, sha: str) -> str:
    """Get full details and diff for a specific commit.

    Args:
        repo_name: Repository name (e.g. "my-project").
        sha: The commit SHA (full or abbreviated).
    """
    return _format(_get_client().get_commit_details(repo_name, sha))


@mcp.tool()
@_gate("compare_branches")
def compare_branches(repo_name: str, base: str, head: str) -> str:
    """Compare two branches or refs — shows ahead/behind counts, changed files, and commits.

    Args:
        repo_name: Repository name (e.g. "my-project").
        base: Base branch or ref (e.g. "main").
        head: Head branch or ref (e.g. "develop").
    """
    return _format(_get_client().compare_branches(repo_name, base, head))


# ── Search & Review Tools ─────────────────────────────────────────────────────


@mcp.tool()
@_gate("search_code")
def search_code(
    query: str,
    repo_name: str | None = None,
    language: str | None = None,
    path: str | None = None,
    limit: int = 10,
) -> str:
    """Search code across BigBro2454's GitHub repositories.

    Args:
        query: Search keywords, symbol name, function, class, or imports.
        repo_name: Optional repository name filter (e.g. "crewai-studio").
        language: Optional language filter (e.g. "Python", "TypeScript").
        path: Optional directory path filter (e.g. "backend/utils").
        limit: Max results to return (default 10, max 50).
    """
    results = _get_client().search_code(
        query=query,
        repo_name=repo_name,
        language=language,
        path=path,
        limit=limit,
    )
    if not results:
        return f"No code matches found for '{query}'."
    return _format(results)


@mcp.tool()
@_gate("review_pull_request")
def review_pull_request(
    repo_name: str,
    pr_number: int,
) -> str:
    """Perform automated code review, security credential scan, and test coverage audit on a PR.

    Args:
        repo_name: Repository name (e.g. "crewai-studio").
        pr_number: The pull request number to review.
    """
    return _format(_get_client().review_pull_request(repo_name, pr_number))


@mcp.tool()
@_gate("post_pr_comment")
def post_pr_comment(
    repo_name: str,
    pr_number: int,
    body: str,
) -> str:
    """Post a comment or review analysis directly on a pull request with credential leak protection.

    Args:
        repo_name: Repository name (e.g. "crewai-studio").
        pr_number: The pull request number.
        body: Markdown content of the comment.
    """
    return _format(_get_client().post_pr_comment(repo_name, pr_number, body))


# ── Governance & Telemetry Tools ──────────────────────────────────────────────


@mcp.tool()
@_gate("audit_repo_security_health")
def audit_repo_security_health(repo_name: str) -> str:
    """Audit repository security posture, governance files, branch protection, and configuration hygiene.

    Args:
        repo_name: Repository name (e.g. "crewai-studio").
    """
    return _format(_get_client().audit_repo_security_health(repo_name))


@mcp.tool()
@_gate("generate_release_notes")
def generate_release_notes(
    repo_name: str,
    base_ref: str,
    head_ref: str = "main",
) -> str:
    """Generate structured release notes and conventional commit changelog between two git refs.

    Args:
        repo_name: Repository name (e.g. "google-adk").
        base_ref: Starting tag, branch, or commit SHA (e.g. "v1.0.0" or "0a8e9fc").
        head_ref: Ending tag, branch, or commit SHA (defaults to "main").
    """
    return _format(_get_client().generate_release_notes(repo_name, base_ref, head_ref=head_ref))


@mcp.tool()
@_gate("get_api_quota_telemetry", cost=0.0)
def get_api_quota_telemetry() -> str:
    """Inspect upstream GitHub API rate-limit quota and runtime tool latency performance metrics."""
    return _format(_get_client().get_api_quota_telemetry())


# ── Entry Point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    mcp.run()
