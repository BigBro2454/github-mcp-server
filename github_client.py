"""
GitHub client scoped to BigBro2454's account.
Thin wrapper around PyGithub that auto-prefixes the owner on all repo operations.
"""

import os
from github import Github, Auth
from github.GithubException import GithubException, UnknownObjectException


GITHUB_USERNAME = "BigBro2454"


class GitHubClient:
    """GitHub API client hardcoded to BigBro2454's account."""

    def __init__(self):
        token = os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError(
                "GITHUB_TOKEN environment variable is required. "
                "Generate one at https://github.com/settings/tokens"
            )
        self.gh = Github(auth=Auth.Token(token))
        self.username = GITHUB_USERNAME

    def _full_repo_name(self, repo_name: str) -> str:
        """Convert a short repo name to owner/repo format."""
        if "/" in repo_name:
            return repo_name
        return f"{self.username}/{repo_name}"

    def _get_repo(self, repo_name: str):
        return self.gh.get_repo(self._full_repo_name(repo_name))

    # ── Repo Operations ──────────────────────────────────────────────

    def list_repos(
        self,
        visibility: str = "all",
        sort: str = "updated",
        language: str | None = None,
    ) -> list[dict]:
        """List BigBro2454's repositories."""
        user = self.gh.get_user(self.username)

        kwargs = {"sort": sort}
        if visibility in ("public", "private"):
            kwargs["type"] = visibility
        else:
            kwargs["type"] = "all"

        repos = []
        for repo in user.get_repos(**kwargs):
            if language and repo.language and repo.language.lower() != language.lower():
                continue
            repos.append({
                "name": repo.name,
                "full_name": repo.full_name,
                "description": repo.description or "",
                "language": repo.language or "N/A",
                "stars": repo.stargazers_count,
                "forks": repo.forks_count,
                "private": repo.private,
                "default_branch": repo.default_branch,
                "updated_at": repo.updated_at.isoformat() if repo.updated_at else "",
                "url": repo.html_url,
            })
        return repos

    def get_repo_info(self, repo_name: str) -> dict:
        """Get detailed info for a specific repo."""
        repo = self._get_repo(repo_name)
        return {
            "name": repo.name,
            "full_name": repo.full_name,
            "description": repo.description or "",
            "language": repo.language or "N/A",
            "stars": repo.stargazers_count,
            "forks": repo.forks_count,
            "open_issues": repo.open_issues_count,
            "private": repo.private,
            "default_branch": repo.default_branch,
            "created_at": repo.created_at.isoformat() if repo.created_at else "",
            "updated_at": repo.updated_at.isoformat() if repo.updated_at else "",
            "topics": repo.get_topics(),
            "url": repo.html_url,
            "clone_url": repo.clone_url,
        }

    def list_branches(self, repo_name: str) -> list[dict]:
        """List all branches for a repo."""
        repo = self._get_repo(repo_name)
        return [
            {
                "name": branch.name,
                "sha": branch.commit.sha[:8],
                "protected": branch.protected,
            }
            for branch in repo.get_branches()
        ]

    def get_file_contents(
        self, repo_name: str, file_path: str, ref: str | None = None
    ) -> dict:
        """Read a file from a repo at a given ref."""
        repo = self._get_repo(repo_name)
        kwargs = {}
        if ref:
            kwargs["ref"] = ref
        content = repo.get_contents(file_path, **kwargs)
        if isinstance(content, list):
            # It's a directory
            return {
                "type": "directory",
                "path": file_path,
                "entries": [
                    {"name": c.name, "type": c.type, "path": c.path}
                    for c in content
                ],
            }
        return {
            "type": "file",
            "path": content.path,
            "size": content.size,
            "encoding": content.encoding,
            "content": content.decoded_content.decode("utf-8", errors="replace"),
        }

    # ── Pull Request Operations ───────────────────────────────────────

    def list_pull_requests(
        self, repo_name: str, state: str = "open", limit: int = 25
    ) -> list[dict]:
        """List PRs for a repo."""
        repo = self._get_repo(repo_name)
        prs = []
        for i, pr in enumerate(repo.get_pulls(state=state, sort="updated", direction="desc")):
            if i >= limit:
                break
            prs.append({
                "number": pr.number,
                "title": pr.title,
                "state": pr.state,
                "author": pr.user.login if pr.user else "unknown",
                "created_at": pr.created_at.isoformat() if pr.created_at else "",
                "updated_at": pr.updated_at.isoformat() if pr.updated_at else "",
                "base": pr.base.ref,
                "head": pr.head.ref,
                "mergeable": pr.mergeable,
                "url": pr.html_url,
            })
        return prs

    def get_pull_request(self, repo_name: str, pr_number: int) -> dict:
        """Get detailed info for a single PR."""
        repo = self._get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        return {
            "number": pr.number,
            "title": pr.title,
            "body": pr.body or "",
            "state": pr.state,
            "author": pr.user.login if pr.user else "unknown",
            "created_at": pr.created_at.isoformat() if pr.created_at else "",
            "updated_at": pr.updated_at.isoformat() if pr.updated_at else "",
            "base": pr.base.ref,
            "head": pr.head.ref,
            "mergeable": pr.mergeable,
            "merged": pr.merged,
            "additions": pr.additions,
            "deletions": pr.deletions,
            "changed_files": pr.changed_files,
            "requested_reviewers": [r.login for r in pr.get_review_requests()[0]],
            "labels": [l.name for l in pr.labels],
            "url": pr.html_url,
        }

    def get_pr_diff(self, repo_name: str, pr_number: int) -> str:
        """Get the full unified diff for a PR."""
        repo = self._get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        diff_parts = []
        for f in pr.get_files():
            header = f"--- a/{f.filename}\n+++ b/{f.filename}"
            patch = f.patch or "(binary or empty)"
            diff_parts.append(f"{header}\n{patch}")
        return "\n\n".join(diff_parts)

    def get_pr_files(self, repo_name: str, pr_number: int) -> list[dict]:
        """List files changed in a PR with their patches."""
        repo = self._get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        return [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "changes": f.changes,
                "patch": f.patch or "",
            }
            for f in pr.get_files()
        ]

    def list_pr_comments(self, repo_name: str, pr_number: int) -> list[dict]:
        """List review comments on a PR."""
        repo = self._get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        comments = []
        # Issue comments (general PR comments)
        for c in pr.get_issue_comments():
            comments.append({
                "type": "issue_comment",
                "author": c.user.login if c.user else "unknown",
                "body": c.body,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            })
        # Review comments (inline code comments)
        for c in pr.get_review_comments():
            comments.append({
                "type": "review_comment",
                "author": c.user.login if c.user else "unknown",
                "body": c.body,
                "path": c.path,
                "line": c.line,
                "created_at": c.created_at.isoformat() if c.created_at else "",
            })
        return sorted(comments, key=lambda x: x["created_at"])

    # ── Commit Operations ─────────────────────────────────────────────

    def list_recent_commits(
        self, repo_name: str, branch: str | None = None, limit: int = 10
    ) -> list[dict]:
        """List recent commits on a branch."""
        repo = self._get_repo(repo_name)
        kwargs = {}
        if branch:
            kwargs["sha"] = branch
        commits = []
        for i, commit in enumerate(repo.get_commits(**kwargs)):
            if i >= limit:
                break
            commits.append({
                "sha": commit.sha[:8],
                "full_sha": commit.sha,
                "message": commit.commit.message.split("\n")[0],
                "author": commit.commit.author.name if commit.commit.author else "unknown",
                "date": commit.commit.author.date.isoformat()
                if commit.commit.author and commit.commit.author.date
                else "",
            })
        return commits

    def get_commit_details(self, repo_name: str, sha: str) -> dict:
        """Get details and diff for a specific commit."""
        repo = self._get_repo(repo_name)
        commit = repo.get_commit(sha)
        files = [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch or "",
            }
            for f in commit.files
        ]
        return {
            "sha": commit.sha,
            "message": commit.commit.message,
            "author": commit.commit.author.name if commit.commit.author else "unknown",
            "date": commit.commit.author.date.isoformat()
            if commit.commit.author and commit.commit.author.date
            else "",
            "additions": commit.stats.additions,
            "deletions": commit.stats.deletions,
            "total_changes": commit.stats.total,
            "files": files,
            "url": commit.html_url,
        }

    def compare_branches(
        self, repo_name: str, base: str, head: str
    ) -> dict:
        """Compare two branches/refs."""
        repo = self._get_repo(repo_name)
        comparison = repo.compare(base, head)
        return {
            "status": comparison.status,
            "ahead_by": comparison.ahead_by,
            "behind_by": comparison.behind_by,
            "total_commits": comparison.total_commits,
            "files_changed": len(comparison.files),
            "files": [
                {
                    "filename": f.filename,
                    "status": f.status,
                    "additions": f.additions,
                    "deletions": f.deletions,
                }
                for f in comparison.files
            ],
            "commits": [
                {
                    "sha": c.sha[:8],
                    "message": c.commit.message.split("\n")[0],
                    "author": c.commit.author.name if c.commit.author else "unknown",
                }
                for c in comparison.commits
            ],
            "url": comparison.html_url,
        }
