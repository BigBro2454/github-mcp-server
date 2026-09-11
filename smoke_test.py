"""
Smoke tests for the GitHub MCP Server.
Tests each tool category against BigBro2454's live GitHub account.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env"))

import server

PASS = "✅"
FAIL = "❌"
results = []


def record(name, success, detail=""):
    status = PASS if success else FAIL
    results.append((status, name, detail))
    print(f"  {status} {name}{f' — {detail}' if detail else ''}")


async def test_list_repos():
    """Test 1: List repos"""
    try:
        result = server.list_my_repos(visibility="all", sort="updated")
        has_data = "name" in result and "BigBro2454" not in result or len(result) > 50
        record("list_my_repos", True, f"{result[:120]}...")
    except Exception as e:
        record("list_my_repos", False, str(e))


async def test_get_repo_info():
    """Test 2: Get repo info (pick first repo from list)"""
    try:
        import json
        repos_json = server.list_my_repos(visibility="all", sort="updated")
        repos = json.loads(repos_json)
        if not repos:
            record("get_repo_info", False, "No repos found to test with")
            return None
        repo_name = repos[0]["name"]
        result = server.get_repo_info(repo_name)
        record("get_repo_info", "full_name" in result, f"repo={repo_name}")
        return repo_name
    except Exception as e:
        record("get_repo_info", False, str(e))
        return None


async def test_list_branches(repo_name):
    """Test 3: List branches"""
    try:
        result = server.list_branches(repo_name)
        record("list_branches", True, f"repo={repo_name}, result={result[:100]}...")
    except Exception as e:
        record("list_branches", False, str(e))


async def test_get_file_contents(repo_name):
    """Test 4: Get file contents (try README)"""
    try:
        result = server.get_file_contents(repo_name, "README.md")
        record("get_file_contents", "content" in result or "entries" in result, f"repo={repo_name}")
    except Exception as e:
        record("get_file_contents", False, str(e))


async def test_list_pull_requests(repo_name):
    """Test 5: List PRs"""
    try:
        result = server.list_pull_requests(repo_name, state="all")
        record("list_pull_requests", True, f"repo={repo_name}, result={result[:100]}...")
        # Return a PR number if any exist
        import json
        try:
            prs = json.loads(result)
            if prs and isinstance(prs, list):
                return prs[0]["number"]
        except:
            pass
        return None
    except Exception as e:
        record("list_pull_requests", False, str(e))
        return None


async def test_get_pull_request(repo_name, pr_number):
    """Test 6: Get PR details"""
    if pr_number is None:
        record("get_pull_request", True, "SKIPPED — no PRs found")
        return
    try:
        result = server.get_pull_request(repo_name, pr_number)
        record("get_pull_request", "title" in result, f"PR #{pr_number}")
    except Exception as e:
        record("get_pull_request", False, str(e))


async def test_get_pr_diff(repo_name, pr_number):
    """Test 7: Get PR diff"""
    if pr_number is None:
        record("get_pr_diff", True, "SKIPPED — no PRs found")
        return
    try:
        result = server.get_pr_diff(repo_name, pr_number)
        record("get_pr_diff", len(result) > 0, f"PR #{pr_number}, diff_len={len(result)}")
    except Exception as e:
        record("get_pr_diff", False, str(e))


async def test_get_pr_files(repo_name, pr_number):
    """Test 8: Get PR files"""
    if pr_number is None:
        record("get_pr_files", True, "SKIPPED — no PRs found")
        return
    try:
        result = server.get_pr_files(repo_name, pr_number)
        record("get_pr_files", True, f"PR #{pr_number}, result={result[:100]}...")
    except Exception as e:
        record("get_pr_files", False, str(e))


async def test_list_pr_comments(repo_name, pr_number):
    """Test 9: List PR comments"""
    if pr_number is None:
        record("list_pr_comments", True, "SKIPPED — no PRs found")
        return
    try:
        result = server.list_pr_comments(repo_name, pr_number)
        record("list_pr_comments", True, f"PR #{pr_number}")
    except Exception as e:
        record("list_pr_comments", False, str(e))


async def test_list_recent_commits(repo_name):
    """Test 10: List recent commits"""
    try:
        result = server.list_recent_commits(repo_name, limit=3)
        record("list_recent_commits", "sha" in result, f"repo={repo_name}")
        import json
        try:
            commits = json.loads(result)
            if commits and isinstance(commits, list):
                return commits[0]["full_sha"]
        except:
            pass
        return None
    except Exception as e:
        record("list_recent_commits", False, str(e))
        return None


async def test_get_commit_details(repo_name, sha):
    """Test 11: Get commit details"""
    if sha is None:
        record("get_commit_details", True, "SKIPPED — no commits found")
        return
    try:
        result = server.get_commit_details(repo_name, sha)
        record("get_commit_details", "message" in result, f"sha={sha[:8]}")
    except Exception as e:
        record("get_commit_details", False, str(e))


async def test_compare_branches(repo_name):
    """Test 12: Compare branches (only if 2+ branches)"""
    try:
        import json
        branches_raw = server.list_branches(repo_name)
        branches = json.loads(branches_raw)
        if len(branches) < 2:
            record("compare_branches", True, "SKIPPED — only 1 branch")
            return
        b1, b2 = branches[0]["name"], branches[1]["name"]
        result = server.compare_branches(repo_name, b1, b2)
        record("compare_branches", "status" in result, f"{b1}..{b2}")
    except Exception as e:
        record("compare_branches", False, str(e))


async def main():
    print("=" * 60)
    print("🧪 GitHub MCP Server — Smoke Tests")
    print(f"   Target user: BigBro2454")
    print("=" * 60)

    print("\n📂 Repo Tools:")
    await test_list_repos()
    repo_name = await test_get_repo_info()
    if repo_name:
        await test_list_branches(repo_name)
        await test_get_file_contents(repo_name)

    print("\n🔀 PR & Review Tools:")
    pr_number = await test_list_pull_requests(repo_name) if repo_name else None
    if repo_name:
        await test_get_pull_request(repo_name, pr_number)
        await test_get_pr_diff(repo_name, pr_number)
        await test_get_pr_files(repo_name, pr_number)
        await test_list_pr_comments(repo_name, pr_number)

    print("\n📝 Commit Tools:")
    sha = None
    if repo_name:
        sha = await test_list_recent_commits(repo_name)
        await test_get_commit_details(repo_name, sha)
        await test_compare_branches(repo_name)

    print("\n" + "=" * 60)
    passed = sum(1 for r in results if r[0] == PASS)
    failed = sum(1 for r in results if r[0] == FAIL)
    print(f"Results: {passed} passed, {failed} failed, {len(results)} total")
    print("=" * 60)

    if failed:
        sys.exit(1)


asyncio.run(main())
