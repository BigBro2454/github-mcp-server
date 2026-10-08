"""
Unit tests for Governance & Developer Productivity MCP Tools
============================================================
Validates audit_repo_security_health, generate_release_notes,
and get_api_quota_telemetry across offline mock scenarios.
"""

import json
from unittest.mock import MagicMock, patch
import pytest

import server
from github_client import GitHubClient


def test_audit_repo_security_health_clean_repo():
    """Verify repository security audit calculates high grade for compliant repo."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    mock_repo = MagicMock()
    mock_repo.name = "google-adk"
    mock_repo.full_name = "BigBro2454/google-adk"
    mock_repo.default_branch = "main"

    # 1. Protected branch
    mock_branch = MagicMock()
    mock_branch.protected = True
    mock_repo.get_branch.return_value = mock_branch

    # 2. .gitignore with secrets
    mock_gi = MagicMock()
    mock_gi.decoded_content = b".env\n.env.*\n.venv/\n__pycache__/\n*.pyc\n"

    # 3. Root contents (clean)
    mock_file1 = MagicMock()
    mock_file1.name = "README.md"
    mock_file2 = MagicMock()
    mock_file2.name = "server.py"

    # 4. License
    mock_license = MagicMock()

    # 5. README (>500B)
    mock_readme = MagicMock()
    mock_readme.decoded_content = b"# Google ADK Multi-Agent Architecture\n" + (b"Detailed systems documentation\n" * 30)

    # 6. Security policy
    mock_sec = MagicMock()

    def get_contents_side_effect(path, **kwargs):
        if path == ".gitignore":
            return mock_gi
        if path == "":
            return [mock_file1, mock_file2]
        if path in ("SECURITY.md", ".github/SECURITY.md"):
            return mock_sec
        raise Exception("File not found")

    mock_repo.get_contents.side_effect = get_contents_side_effect
    mock_repo.get_license.return_value = mock_license
    mock_repo.get_readme.return_value = mock_readme

    client._get_repo = MagicMock(return_value=mock_repo)

    audit = client.audit_repo_security_health("google-adk")
    assert audit["repo_name"] == "google-adk"
    assert audit["health_score"] >= 90
    assert audit["grade"] in ("A", "A+")
    assert audit["checks"]["default_branch_protection"]["passed"] is True
    assert audit["checks"]["gitignore_hygiene"]["passed"] is True
    assert audit["checks"]["secret_free_workspace"]["passed"] is True
    assert audit["checks"]["license"]["passed"] is True
    assert audit["checks"]["readme_documentation"]["passed"] is True
    assert audit["checks"]["security_policy"]["passed"] is True
    assert "Governance Dimension Scorecard" in audit["markdown_scorecard"]


def test_audit_repo_security_health_flags_leaks():
    """Verify repository security audit catches sensitive file in root."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    mock_repo = MagicMock()
    mock_repo.name = "vulnerable-repo"
    mock_repo.full_name = "BigBro2454/vulnerable-repo"
    mock_repo.default_branch = "main"

    mock_branch = MagicMock()
    mock_branch.protected = False
    mock_repo.get_branch.return_value = mock_branch

    # Root contains .env
    mock_env = MagicMock()
    mock_env.name = ".env"

    def get_contents_side_effect(path, **kwargs):
        if path == "":
            return [mock_env]
        raise Exception("File not found")

    mock_repo.get_contents.side_effect = get_contents_side_effect
    mock_repo.get_license.side_effect = Exception("No license")
    mock_repo.get_readme.side_effect = Exception("No readme")

    client._get_repo = MagicMock(return_value=mock_repo)

    audit = client.audit_repo_security_health("vulnerable-repo")
    assert audit["health_score"] < 50
    assert audit["grade"] == "F"
    assert audit["checks"]["secret_free_workspace"]["passed"] is False
    assert len(audit["findings"]) > 0
    assert any("Sensitive files committed" in f for f in audit["findings"])
    assert len(audit["recommendations"]) > 0


def test_generate_release_notes_categorization():
    """Verify release notes generator groups commits into conventional taxonomy."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    comparison_data = {
        "files_changed": 14,
        "commits": [
            {"sha": "a1b2c3d", "message": "feat: add automated release notes tool", "author": "BigBro2454"},
            {"sha": "b2c3d4e", "message": "fix: resolve token bucket refill timestamp drift", "author": "BigBro2454"},
            {"sha": "c3d4e5f", "message": "sec: sanitize outbound PR comments against credential leak", "author": "security-bot"},
            {"sha": "d4e5f6a", "message": "perf: cache repository metadata lookups", "author": "BigBro2454"},
            {"sha": "e5f6a7b", "message": "docs: document MCP latency telemetry profiler", "author": "BigBro2454"},
            {"sha": "f6a7b8c", "message": "feat!: breaking change in tool schema parameters\n\nBREAKING CHANGE: updated signature", "author": "BigBro2454"},
        ],
    }

    client.compare_branches = MagicMock(return_value=comparison_data)

    notes = client.generate_release_notes("crewai-studio", "v1.0.0", "main")
    assert notes["repo_name"] == "crewai-studio"
    assert notes["total_commits"] == 6
    assert notes["files_changed"] == 14
    assert "BigBro2454" in notes["contributors"]
    assert "security-bot" in notes["contributors"]

    # Verify categories
    cats = notes["categories"]
    assert "features" in cats
    assert "fixes" in cats
    assert "security" in cats
    assert "performance" in cats
    assert "docs" in cats

    # Verify breaking changes flagged
    assert len(notes["breaking_changes"]) >= 1

    md = notes["markdown_notes"]
    assert "# 🚀 Release Notes: `crewai-studio`" in md
    assert "BREAKING CHANGES" in md
    assert "🚀 Features" in md
    assert "🐛 Bug Fixes" in md
    assert "🛡️ Security & Guardrails" in md


def test_get_api_quota_telemetry_live_and_offline():
    """Verify get_api_quota_telemetry fetches quota and merges telemetry stats."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    mock_rate = MagicMock()
    mock_rate.core.limit = 5000
    mock_rate.core.remaining = 4980
    mock_rate.core.reset.timestamp.return_value = 1750000000
    mock_rate.search.limit = 30
    mock_rate.search.remaining = 28

    client.gh = MagicMock()
    client.gh.get_rate_limit.return_value = mock_rate

    summary = client.get_api_quota_telemetry()
    assert summary["github_api_quota"]["core_remaining"] == 4980
    assert summary["github_api_quota"]["core_limit"] == 5000
    assert summary["github_api_quota"]["search_remaining"] == 28


def test_server_wrapper_governance_tools():
    """Verify FastMCP server wrapper invokes governance tools correctly."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"
    client.audit_repo_security_health = MagicMock(return_value={"status": "audit_ok", "grade": "A+"})
    client.generate_release_notes = MagicMock(return_value={"status": "notes_ok", "total_commits": 5})
    client.get_api_quota_telemetry = MagicMock(return_value={"status": "quota_ok", "remaining": 5000})

    with patch.object(server, "_get_client", return_value=client):
        # 1. audit_repo_security_health
        res_audit = server.audit_repo_security_health("google-adk")
        assert "audit_ok" in res_audit

        # 2. generate_release_notes
        res_notes = server.generate_release_notes("google-adk", "v1.0.0", "main")
        assert "notes_ok" in res_notes

        # 3. get_api_quota_telemetry
        res_quota = server.get_api_quota_telemetry()
        assert "quota_ok" in res_quota
