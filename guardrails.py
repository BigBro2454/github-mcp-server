"""
Security Guardrails & Access Policy Engine for GitHub MCP Server
=================================================================
Provides defense-in-depth protection for MCP tool operations:
- Pre-execution path traversal and sensitive file access prevention
- Outbound text and comment sanitization (zero secret leakage)
- Token-bucket rate limiting to protect GitHub API quotas
- Audit logging for enterprise security compliance
"""

import re
import time
import threading
from typing import Any


class SecurityPolicyViolation(Exception):
    """Raised when an operation violates MCP security policy."""
    pass


class TokenBucketRateLimiter:
    """Thread-safe Token Bucket Rate Limiter for GitHub API quota protection."""

    def __init__(self, capacity: float = 60.0, refill_rate: float = 1.0):
        """
        Args:
            capacity: Maximum burst capacity in tokens (default 60 tokens).
            refill_rate: Tokens replenished per second (default 1 token/sec = 60 rpm).
        """
        self.capacity = float(capacity)
        self.refill_rate = float(refill_rate)
        self.tokens = float(capacity)
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def _refill(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last_refill
        self.last_refill = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_rate)

    def acquire(self, tokens: float = 1.0) -> bool:
        """Attempt to acquire tokens. Returns True if granted, False if throttled."""
        with self._lock:
            self._refill()
            if self.tokens >= tokens:
                self.tokens -= tokens
                return True
            return False

    def get_available_tokens(self) -> float:
        """Inspect current token balance."""
        with self._lock:
            self._refill()
            return self.tokens

    def reset(self) -> None:
        """Reset tokens to maximum capacity."""
        with self._lock:
            self.tokens = self.capacity
            self.last_refill = time.monotonic()


class MCPGuardrails:
    """Enterprise security gatekeeper for MCP tool calls."""

    # Sensitive path patterns
    BLOCKED_PATH_PATTERNS = [
        re.compile(r"(^|[/\\])\.env(\..+)?$", re.IGNORECASE),
        re.compile(r"\.(pem|key|pkcs12|pfx)$", re.IGNORECASE),
        re.compile(r"(^|[/\\])(id_rsa|id_ed25519|id_dsa|id_ecdsa)(\..+)?$", re.IGNORECASE),
        re.compile(r"(^|[/\\])credentials\.json$", re.IGNORECASE),
        re.compile(r"(^|[/\\])service_account\.json$", re.IGNORECASE),
        re.compile(r"(^|[/\\])secrets?\.(ya?ml|json|conf)$", re.IGNORECASE),
    ]

    # Secret detection regexes for outbound comments/content
    SECRET_PATTERNS = [
        (re.compile(r"AIza[0-9A-Za-z\-_]{30,45}"), "Google Gemini / Cloud API Key"),
        (re.compile(r"sk-[a-zA-Z0-9]{20,48}"), "OpenAI API Key"),
        (re.compile(r"(?:AKIA|ABIA|ACCA|ASIA)[0-9A-Z]{16}"), "AWS Access Key ID"),
        (re.compile(r"(?:ghp|gho|ghu|ghs|ghr)_[a-zA-Z0-9]{36,255}"), "GitHub Personal Access Token"),
        (re.compile(r"ghp_[a-zA-Z0-9]{30,40}"), "GitHub Legacy PAT"),
        (re.compile(r"(?i)bearer\s+[a-zA-Z0-9_\-\.]{25,}"), "Generic Bearer Token"),
        (re.compile(r"-----BEGIN (?:RSA|EC|OPENSSH|DSA|PGP)?\s*PRIVATE KEY-----"), "Cryptographic Private Key"),
    ]

    def __init__(self, rate_limit_capacity: float = 60.0, refill_rate: float = 1.0):
        self.rate_limiter = TokenBucketRateLimiter(rate_limit_capacity, refill_rate)
        self.audit_log: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def record_audit(self, event_type: str, details: dict[str, Any]) -> None:
        """Record a security or access audit event."""
        with self._lock:
            self.audit_log.append({
                "timestamp": time.time(),
                "event_type": event_type,
                **details,
            })

    def validate_file_path(self, file_path: str) -> tuple[bool, str | None]:
        """
        Validate file path against path traversal and sensitive credential access.

        Returns:
            (is_valid, rejection_reason)
        """
        cleaned = file_path.strip().replace("\\", "/")

        # 1. Path traversal detection
        if ".." in cleaned.split("/"):
            reason = f"Security Policy Violation: Path traversal detected in '{file_path}'"
            self.record_audit("PATH_TRAVERSAL_BLOCKED", {"path": file_path, "reason": reason})
            return False, reason

        if cleaned.startswith("/") and not cleaned.startswith("./"):
            # Normalize absolute path check
            if any(cleaned.startswith(p) for p in ["/etc", "/var", "/root", "/Users"]):
                reason = f"Security Policy Violation: Host filesystem traversal blocked in '{file_path}'"
                self.record_audit("HOST_TRAVERSAL_BLOCKED", {"path": file_path, "reason": reason})
                return False, reason

        # Safe template files allowlist
        filename = cleaned.split("/")[-1]
        if filename.lower() in (".env.example", ".env.sample", ".env.template"):
            return True, None

        # 2. Sensitive credential file protection
        for pattern in self.BLOCKED_PATH_PATTERNS:
            if pattern.search(cleaned) or pattern.search(filename):
                reason = f"Security Policy Violation: Access to sensitive file '{file_path}' is strictly blocked."
                self.record_audit("SENSITIVE_FILE_BLOCKED", {"path": file_path, "reason": reason})
                return False, reason

        return True, None

    def sanitize_outbound_text(self, text: str, block_on_critical: bool = False) -> dict[str, Any]:
        """
        Scan outbound comments or PR posts for secrets, redacting or blocking leaks.

        Returns:
            Dictionary with safety status, findings, sanitized text, and action taken.
        """
        if not text:
            return {"is_safe": True, "findings": [], "sanitized_text": "", "action": "PASSED"}

        findings = []
        sanitized = text

        for pattern, label in self.SECRET_PATTERNS:
            matches = list(pattern.finditer(sanitized))
            if matches:
                findings.append({"pattern": label, "count": len(matches)})
                for match in matches:
                    val = match.group(0)
                    masked = f"[REDACTED_{label.upper().replace(' ', '_')}]"
                    sanitized = sanitized.replace(val, masked)

        if findings:
            if block_on_critical:
                self.record_audit("OUTBOUND_SECRET_BLOCKED", {"findings": findings})
                return {
                    "is_safe": False,
                    "findings": findings,
                    "sanitized_text": "",
                    "action": "BLOCKED",
                    "reason": f"Outbound content contained {len(findings)} sensitive credential(s).",
                }
            self.record_audit("OUTBOUND_SECRET_REDACTED", {"findings": findings})
            return {
                "is_safe": False,
                "findings": findings,
                "sanitized_text": sanitized,
                "action": "REDACTED",
            }

        return {
            "is_safe": True,
            "findings": [],
            "sanitized_text": text,
            "action": "PASSED",
        }

    def check_rate_limit(self, tool_name: str, cost: float = 1.0) -> tuple[bool, str | None]:
        """Check and consume rate limit tokens for a tool execution."""
        allowed = self.rate_limiter.acquire(cost)
        if not allowed:
            reason = f"Rate limit exceeded: Too many requests for '{tool_name}'. Available quota exhausted."
            self.record_audit("RATE_LIMIT_EXCEEDED", {"tool": tool_name, "reason": reason})
            return False, reason
        return True, None


# Global guardrails instance
guardrails = MCPGuardrails()
