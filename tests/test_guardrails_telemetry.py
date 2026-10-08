"""
Unit tests for MCP Guardrails and Telemetry Profiler
=====================================================
Validates path traversal prevention, secret interception, token bucket
rate limiting, latency telemetry profiling, and scorecard generation.
"""

import json
import time
from unittest.mock import MagicMock
import pytest

from guardrails import MCPGuardrails, TokenBucketRateLimiter
from telemetry import MCPTelemetryTracker
from github_client import GitHubClient


def test_path_traversal_blocking():
    """Verify relative and absolute path traversal attempts are rejected."""
    guard = MCPGuardrails()
    unsafe_paths = [
        "../secret.txt",
        "foo/../../etc/passwd",
        "/etc/shadow",
        "/Users/attacker/.ssh/id_rsa",
    ]
    for p in unsafe_paths:
        is_safe, reason = guard.validate_file_path(p)
        assert not is_safe, f"Path '{p}' should have been blocked"
        assert "Security Policy Violation" in reason


def test_sensitive_file_blocking():
    """Verify access to sensitive credentials and configuration files is blocked."""
    guard = MCPGuardrails()
    sensitive_paths = [
        ".env",
        ".env.local",
        "config/.env.prod",
        "certs/server.pem",
        "keys/private.key",
        "auth/credentials.json",
        "auth/service_account.json",
        "id_rsa",
    ]
    for p in sensitive_paths:
        is_safe, reason = guard.validate_file_path(p)
        assert not is_safe, f"Sensitive file '{p}' should have been blocked"
        assert "sensitive file" in reason.lower()


def test_safe_path_allowed():
    """Verify standard source files pass path validation."""
    guard = MCPGuardrails()
    safe_paths = [
        "README.md",
        "src/server.py",
        "backend/utils/helper.py",
        ".env.example",
        "docs/architecture.png",
    ]
    for p in safe_paths:
        is_safe, reason = guard.validate_file_path(p)
        assert is_safe, f"Safe path '{p}' was incorrectly rejected: {reason}"
        assert reason is None


def test_outbound_secret_sanitization():
    """Verify outbound text scanning detects and masks multiple credential types."""
    guard = MCPGuardrails()
    leaked_payload = (
        "Here is the debug info:\n"
        "Gemini: AIzaSyB1234567890abcdef1234567890abc\n"
        "OpenAI: sk-abcdefghijklmnopqrstuvwxyz1234567890\n"
        "AWS: AKIAIOSFODNN7EXAMPLE\n"
        "GitHub: ghp_1234567890abcdefghijklmnopqrstuvwxyz\n"
    )

    result = guard.sanitize_outbound_text(leaked_payload)
    assert not result["is_safe"]
    assert result["action"] == "REDACTED"
    assert len(result["findings"]) >= 4

    sanitized = result["sanitized_text"]
    assert "AIzaSy" not in sanitized
    assert "sk-" not in sanitized
    assert "AKIA" not in sanitized
    assert "ghp_" not in sanitized
    assert "[REDACTED_" in sanitized


def test_token_bucket_rate_limiter():
    """Verify token bucket permits bursts up to capacity and blocks excess."""
    limiter = TokenBucketRateLimiter(capacity=3.0, refill_rate=1.0)
    assert limiter.acquire(1.0) is True
    assert limiter.acquire(1.0) is True
    assert limiter.acquire(1.0) is True
    # Capacity exhausted
    assert limiter.acquire(1.0) is False

    # Reset
    limiter.reset()
    assert limiter.acquire(1.0) is True


def test_telemetry_profiling_and_summary():
    """Verify telemetry measures tool invocations and latency metrics."""
    tracker = MCPTelemetryTracker()

    # Simulate tool calls
    for _ in range(5):
        with tracker.profile("get_repo_info"):
            time.sleep(0.005)

    with pytest.raises(ValueError):
        with tracker.profile("get_repo_info"):
            raise ValueError("Forced error")

    tracker.record_payload("get_repo_info", "{\"status\": \"ok\"}")

    summary = tracker.get_summary()
    assert summary["total_invocations"] == 6
    assert summary["total_errors"] == 1
    assert "get_repo_info" in summary["tools"]
    t_stats = summary["tools"]["get_repo_info"]
    assert t_stats["total_calls"] == 6
    assert t_stats["error_count"] == 1
    assert t_stats["mean_latency_ms"] > 0
    assert t_stats["total_bytes_transferred"] > 0


def test_telemetry_json_and_markdown_exports(tmp_path):
    """Verify telemetry exports valid JSON and presentation-grade Markdown."""
    tracker = MCPTelemetryTracker()
    with tracker.profile("list_branches"):
        time.sleep(0.002)

    tracker.update_quota_info(core_remaining=4950, core_limit=5000, reset_ts=1700000000)

    json_file = str(tmp_path / "telemetry.json")
    md_file = str(tmp_path / "telemetry.md")

    json_content = tracker.export_summary_json(json_file)
    md_content = tracker.export_summary_markdown(md_file)

    parsed = json.loads(json_content)
    assert parsed["github_api_quota"]["core_remaining"] == 4950
    assert "list_branches" in parsed["tools"]

    assert "# 📈 GitHub MCP Server — Telemetry & Quota Scorecard" in md_content
    assert "4950 / 5000" in md_content
    assert "list_branches" in md_content


def test_client_get_file_contents_blocked_by_guardrails():
    """Verify GitHubClient.get_file_contents stops at guardrail before hitting GitHub."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    res = client.get_file_contents("test-repo", ".env")
    assert res.get("error") == "SECURITY_POLICY_VIOLATION"
    assert "strictly blocked" in res.get("message", "")


def test_client_post_pr_comment_sanitizes_body():
    """Verify GitHubClient.post_pr_comment sanitizes credentials before sending."""
    client = GitHubClient.__new__(GitHubClient)
    client.username = "BigBro2454"

    mock_repo = MagicMock()
    mock_pr = MagicMock()
    mock_comment = MagicMock()
    mock_comment.id = 999
    mock_comment.html_url = "https://github.com/BigBro2454/test-repo/pull/1#comment-999"
    mock_comment.body = "Here is key: [REDACTED_GOOGLE_GEMINI_/_CLOUD_API_KEY]"
    mock_comment.created_at = None

    mock_pr.create_issue_comment.return_value = mock_comment
    mock_repo.get_pull.return_value = mock_pr
    client._get_repo = MagicMock(return_value=mock_repo)

    result = client.post_pr_comment(
        "test-repo", 1, "Here is key: AIzaSyB1234567890abcdef1234567890abc"
    )
    assert result["sanitized"] is True
    assert len(result["redacted_findings"]) >= 1

    # Ensure create_issue_comment received sanitized text
    called_body = mock_pr.create_issue_comment.call_args[0][0]
    assert "AIzaSy" not in called_body
    assert "[REDACTED_" in called_body
