import asyncio
import json
from unittest.mock import MagicMock, patch
import pytest

import server
from github_client import GitHubClient


def test_mcp_tool_registration():
    """Verify all 15 MCP tools are registered with FastMCP."""
    tool_names = [t.name for t in asyncio.run(server.mcp.list_tools())]
    expected_tools = [
        "list_my_repos",
        "get_repo_info",
        "list_branches",
        "get_file_contents",
        "list_pull_requests",
        "get_pull_request",
        "get_pr_diff",
        "get_pr_files",
        "list_pr_comments",
        "list_recent_commits",
        "get_commit_details",
        "compare_branches",
        "search_code",
        "review_pull_request",
        "post_pr_comment",
    ]
    for exp in expected_tools:
        assert exp in tool_names, f"Tool '{exp}' not found in registered tools"
    assert len(tool_names) == 15



def test_pr_review_security_leak_detection():
    """Verify automated PR review flags hardcoded credentials and secret keys."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    mock_repo = MagicMock()
    mock_pr = MagicMock()
    mock_pr.number = 42
    mock_pr.title = "test: add external credentials"
    mock_pr.additions = 15
    mock_pr.deletions = 2

    # Mock file with leaked Gemini and OpenAI keys
    mock_file = MagicMock()
    mock_file.filename = "src/config.py"
    mock_file.patch = (
        "@@ -1,3 +1,6 @@\n"
        "+# API keys\n"
        "+GEMINI_KEY = \"AIzaSyB1234567890abcdef1234567890abc\"\n"
        "+OPENAI_KEY = \"sk-1234567890abcdef1234567890abcdef\"\n"
    )

    mock_pr.get_files.return_value = [mock_file]
    mock_repo.get_pull.return_value = mock_pr
    client._get_repo = MagicMock(return_value=mock_repo)

    review = client.review_pull_request("test-repo", 42)
    assert review["pr_number"] == 42
    assert review["verdict"] == "REQUEST_CHANGES"
    assert review["risk_level"] == "CRITICAL"
    assert len(review["security_findings"]) >= 2
    assert any("Gemini API Key" in f["issue"] for f in review["security_findings"])
    assert any("OpenAI API Key" in f["issue"] for f in review["security_findings"])


def test_pr_review_test_coverage_audit():
    """Verify automated PR review warns when code changes lack test coverage."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    mock_repo = MagicMock()
    mock_pr = MagicMock()
    mock_pr.number = 10
    mock_pr.title = "feat: add user billing module"
    mock_pr.additions = 350
    mock_pr.deletions = 20

    # Mock code file without tests
    mock_file = MagicMock()
    mock_file.filename = "backend/billing/service.py"
    mock_file.patch = "@@ -0,0 +1,50 @@\n+def charge_customer(): pass\n"

    mock_pr.get_files.return_value = [mock_file]
    mock_repo.get_pull.return_value = mock_pr
    client._get_repo = MagicMock(return_value=mock_repo)

    review = client.review_pull_request("test-repo", 10)
    assert review["test_coverage_status"] == "TESTS_MISSING"
    assert review["risk_level"] in ("MEDIUM", "HIGH")
    assert any("test updates" in r for r in review["recommendations"])


def test_search_code_formatting():
    """Verify search_code tool formatting and results output."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    mock_item = MagicMock()
    mock_item.name = "server.py"
    mock_item.path = "playground/github-mcp-server/server.py"
    mock_item.repository.name = "github-mcp-server"
    mock_item.sha = "abcdef1234567890"
    mock_item.html_url = "https://github.com/BigBro2454/github-mcp-server/blob/main/server.py"

    mock_results = MagicMock()
    mock_results.totalCount = 1
    mock_results.__iter__.return_value = [mock_item]

    client.gh = MagicMock()
    client.gh.search_code.return_value = mock_results

    with patch.object(server, "_get_client", return_value=client):
        output = server.search_code("FastMCP", limit=5)
        parsed = json.loads(output)
        assert isinstance(parsed, list)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "server.py"
        assert parsed[0]["repository"] == "github-mcp-server"
