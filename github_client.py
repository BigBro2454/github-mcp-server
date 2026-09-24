"""
GitHub client scoped to BigBro2454's account.
Thin wrapper around PyGithub that auto-prefixes the owner on all repo operations.
"""

import os
import re
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

    # ── Search & Review Operations ───────────────────────────────────

    def search_code(
        self,
        query: str,
        repo_name: str | None = None,
        language: str | None = None,
        path: str | None = None,
        limit: int = 10,
    ) -> list[dict]:
        """Search code across BigBro2454's repositories."""
        limit = min(limit, 50)
        query_parts = [query, f"user:{self.username}"]

        if repo_name:
            query_parts.append(f"repo:{self._full_repo_name(repo_name)}")
        if language:
            query_parts.append(f"language:{language}")
        if path:
            query_parts.append(f"path:{path}")

        full_query = " ".join(query_parts)
        try:
            results = self.gh.search_code(full_query)
            try:
                if results.totalCount == 0:
                    return []
            except (IndexError, GithubException):
                return []

            items = []
            for idx, item in enumerate(results):
                items.append({
                    "name": item.name,
                    "path": item.path,
                    "repository": item.repository.name,
                    "sha": item.sha[:8],
                    "url": item.html_url,
                })
                if idx + 1 >= limit:
                    break
            return items
        except (GithubException, IndexError) as exc:
            # Fallback or empty if search index is rate-limited or unavailable
            return [{"error": str(exc), "query": full_query}]

    def review_pull_request(self, repo_name: str, pr_number: int) -> dict:
        """Perform automated security, testing, and architecture review on a PR."""
        repo = self._get_repo(repo_name)
        pr = repo.get_pull(pr_number)

        files = list(pr.get_files())
        additions = pr.additions
        deletions = pr.deletions
        total_changes = additions + deletions

        security_patterns = [
            (re.compile(r"AKIA[0-9A-Z]{16}"), "AWS Access Key ID detected"),
            (re.compile(r"gh[pousr]_[A-Za-z0-9_]{36,}"), "GitHub Personal Access Token detected"),
            (re.compile(r"AIzaSy[A-Za-z0-9_-]{30,}"), "Google / Gemini API Key detected"),
            (re.compile(r"sk-[A-Za-z0-9_-]{32,}"), "OpenAI API Key detected"),
            (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |PGP )?PRIVATE KEY-----"), "Private cryptographic key detected"),

        ]

        security_findings: list[dict] = []
        code_files_changed: list[str] = []
        test_files_changed: list[str] = []
        doc_files_changed: list[str] = []

        code_extensions = {".py", ".ts", ".tsx", ".js", ".jsx", ".go", ".rs", ".java", ".c", ".cpp"}
        test_indicators = {"test", "tests", "spec", "evals"}

        for f in files:
            fname = f.filename.lower()
            ext = os.path.splitext(fname)[1]

            # Categorize files
            if any(ind in fname for ind in test_indicators):
                test_files_changed.append(f.filename)
            elif ext in code_extensions:
                code_files_changed.append(f.filename)
            elif ext in {".md", ".txt", ".rst", ".adoc"}:
                doc_files_changed.append(f.filename)

            # Security inspection on patch
            patch = f.patch or ""
            if patch:
                for line in patch.splitlines():
                    if line.startswith("+") and not line.startswith("+++"):
                        for pat, label in security_patterns:
                            if pat.search(line):
                                security_findings.append({
                                    "file": f.filename,
                                    "severity": "CRITICAL",
                                    "issue": label,
                                    "snippet": line[:80].strip(),
                                })

            # Check if sensitive file directly tracked
            if any(sens in fname for sens in [".env", "id_rsa", ".pem", ".key", "credentials.json"]):
                if f.filename != ".env.example":
                    security_findings.append({
                        "file": f.filename,
                        "severity": "CRITICAL",
                        "issue": f"Sensitive file committed: {f.filename}",
                        "snippet": f.filename,
                    })

        # Test coverage assessment
        if code_files_changed and not test_files_changed:
            test_status = "TESTS_MISSING"
        elif test_files_changed:
            test_status = "TESTS_PRESENT"
        else:
            test_status = "NO_CODE_CHANGES"

        # Risk classification
        if security_findings:
            risk_level = "CRITICAL"
            verdict = "REQUEST_CHANGES"
        elif total_changes > 500 and test_status == "TESTS_MISSING":
            risk_level = "HIGH"
            verdict = "REQUEST_CHANGES"
        elif total_changes > 300 or test_status == "TESTS_MISSING":
            risk_level = "MEDIUM"
            verdict = "COMMENT"
        else:
            risk_level = "LOW"
            verdict = "APPROVE"

        # Recommendations
        recommendations = []
        if security_findings:
            recommendations.append("Immediately revoke and remove detected secrets from git history.")
        if test_status == "TESTS_MISSING":
            recommendations.append(
                f"PR modifies {len(code_files_changed)} code file(s) without test updates. Add unit/integration tests."
            )
        if total_changes > 400:
            recommendations.append("PR exceeds 400 lines changed. Consider splitting into focused, atomic pull requests.")
        if not recommendations:
            recommendations.append("Changes look clean and well-structured. Good to merge.")

        # Markdown review report
        md_summary = [
            f"## 🤖 Automated PR Review — #{pr.number}: {pr.title}",
            "",
            f"**Verdict:** `[{verdict}]` | **Risk Level:** `{risk_level}`",
            "",
            "### 📊 Metrics & Scope",
            f"- **Files Changed:** {len(files)} ({len(code_files_changed)} code, {len(test_files_changed)} test, {len(doc_files_changed)} doc)",
            f"- **Volume:** +{additions} / -{deletions} ({total_changes} total lines)",
            f"- **Test Coverage Status:** `{test_status}`",
            "",
            "### 🛡️ Security Audit",
        ]

        if security_findings:
            for s in security_findings:
                md_summary.append(f"- 🚨 **[{s['severity']}]** `{s['file']}`: {s['issue']}")
        else:
            md_summary.append("- ✅ Zero secrets or sensitive credentials detected in diff patch.")

        md_summary.extend([
            "",
            "### 💡 Recommendations",
        ])
        for rec in recommendations:
            md_summary.append(f"- {rec}")

        return {
            "pr_number": pr.number,
            "title": pr.title,
            "verdict": verdict,
            "risk_level": risk_level,
            "metrics": {
                "total_files": len(files),
                "code_files": len(code_files_changed),
                "test_files": len(test_files_changed),
                "doc_files": len(doc_files_changed),
                "additions": additions,
                "deletions": deletions,
                "total_changes": total_changes,
            },
            "test_coverage_status": test_status,
            "security_findings": security_findings,
            "recommendations": recommendations,
            "markdown_summary": "\n".join(md_summary),
        }

    def post_pr_comment(self, repo_name: str, pr_number: int, body: str) -> dict:
        """Post a comment on a pull request."""
        repo = self._get_repo(repo_name)
        pr = repo.get_pull(pr_number)
        comment = pr.create_issue_comment(body)
        return {
            "id": comment.id,
            "url": comment.html_url,
            "body": comment.body,
            "created_at": comment.created_at.isoformat() if comment.created_at else "",
        }

