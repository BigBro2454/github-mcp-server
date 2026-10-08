"""
Telemetry Profiler & GitHub API Quota Monitor
==============================================
Profiles tool execution latency (wall-clock ms), invocation counts,
data throughput, error rates, and GitHub API rate-limit quota consumption.
Automates export to structured JSON and presentation-grade Markdown.
"""

import json
import os
import time
import threading
from contextlib import contextmanager
from typing import Any, Generator


class MCPTelemetryTracker:
    """Thread-safe telemetry profiler for MCP tool invocations."""

    def __init__(self):
        self._lock = threading.Lock()
        self.tool_stats: dict[str, dict[str, Any]] = {}
        self.api_quota: dict[str, Any] = {
            "core_limit": 5000,
            "core_remaining": 5000,
            "core_reset_timestamp": 0,
            "search_limit": 30,
            "search_remaining": 30,
            "search_reset_timestamp": 0,
            "last_updated": 0,
        }
        self.start_time = time.time()

    def _ensure_tool(self, tool_name: str) -> dict[str, Any]:
        if tool_name not in self.tool_stats:
            self.tool_stats[tool_name] = {
                "calls": 0,
                "errors": 0,
                "durations_ms": [],
                "total_bytes_out": 0,
            }
        return self.tool_stats[tool_name]

    @contextmanager
    def profile(self, tool_name: str) -> Generator[None, None, None]:
        """Context manager to measure tool execution latency and error status."""
        start = time.perf_counter()
        error_occurred = False
        try:
            yield
        except Exception:
            error_occurred = True
            raise
        finally:
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            with self._lock:
                stats = self._ensure_tool(tool_name)
                stats["calls"] += 1
                if error_occurred:
                    stats["errors"] += 1
                stats["durations_ms"].append(elapsed_ms)

    def record_payload(self, tool_name: str, payload_str: str) -> None:
        """Record outbound payload byte volume."""
        with self._lock:
            stats = self._ensure_tool(tool_name)
            stats["total_bytes_out"] += len(payload_str.encode("utf-8"))

    def update_quota_info(self, core_remaining: int, core_limit: int, reset_ts: int,
                          search_remaining: int = 30, search_limit: int = 30) -> None:
        """Update live GitHub API rate-limit metadata."""
        with self._lock:
            self.api_quota["core_limit"] = core_limit
            self.api_quota["core_remaining"] = core_remaining
            self.api_quota["core_reset_timestamp"] = reset_ts
            self.api_quota["search_limit"] = search_limit
            self.api_quota["search_remaining"] = search_remaining
            self.api_quota["last_updated"] = time.time()

    def get_summary(self) -> dict[str, Any]:
        """Compute aggregated metrics across all recorded tool executions."""
        with self._lock:
            total_invocations = 0
            total_errors = 0
            all_durations: list[float] = []
            per_tool_summary: dict[str, Any] = {}

            for tool, data in self.tool_stats.items():
                calls = data["calls"]
                errors = data["errors"]
                durations = data["durations_ms"]
                total_invocations += calls
                total_errors += errors
                all_durations.extend(durations)

                if durations:
                    sorted_durations = sorted(durations)
                    mean_lat = sum(durations) / len(durations)
                    min_lat = min(durations)
                    max_lat = max(durations)
                    p95_idx = int(len(sorted_durations) * 0.95)
                    p95_lat = sorted_durations[min(p95_idx, len(sorted_durations) - 1)]
                else:
                    mean_lat = min_lat = max_lat = p95_lat = 0.0

                per_tool_summary[tool] = {
                    "total_calls": calls,
                    "error_count": errors,
                    "success_rate_pct": round(((calls - errors) / calls * 100.0) if calls else 100.0, 1),
                    "mean_latency_ms": round(mean_lat, 2),
                    "min_latency_ms": round(min_lat, 2),
                    "max_latency_ms": round(max_lat, 2),
                    "p95_latency_ms": round(p95_lat, 2),
                    "total_bytes_transferred": data["total_bytes_out"],
                }

            if all_durations:
                sorted_all = sorted(all_durations)
                overall_mean = sum(all_durations) / len(all_durations)
                p95_idx = int(len(sorted_all) * 0.95)
                overall_p95 = sorted_all[min(p95_idx, len(sorted_all) - 1)]
            else:
                overall_mean = overall_p95 = 0.0

            uptime_sec = time.time() - self.start_time

            return {
                "uptime_seconds": round(uptime_sec, 1),
                "total_invocations": total_invocations,
                "total_errors": total_errors,
                "overall_success_rate_pct": round(
                    ((total_invocations - total_errors) / total_invocations * 100.0)
                    if total_invocations else 100.0, 1
                ),
                "overall_mean_latency_ms": round(overall_mean, 2),
                "overall_p95_latency_ms": round(overall_p95, 2),
                "github_api_quota": self.api_quota,
                "tools": per_tool_summary,
            }

    def export_summary_json(self, target_path: str | None = None) -> str:
        """Export telemetry summary to JSON file."""
        summary = self.get_summary()
        content = json.dumps(summary, indent=2, ensure_ascii=False)
        if target_path:
            os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
        return content

    def export_summary_markdown(self, target_path: str | None = None) -> str:
        """Export executive presentation-grade Markdown scorecard."""
        s = self.get_summary()
        quota = s["github_api_quota"]

        lines = [
            "# 📈 GitHub MCP Server — Telemetry & Quota Scorecard",
            "",
            f"**Uptime:** `{s['uptime_seconds']}s` | **Total Invocations:** `{s['total_invocations']}` | **Success Rate:** `{s['overall_success_rate_pct']}%`",
            "",
            "## ⚡ Global Latency SLAs",
            f"- **Mean Latency:** `{s['overall_mean_latency_ms']} ms`",
            f"- **P95 Latency:** `{s['overall_p95_latency_ms']} ms`",
            f"- **Total Errors:** `{s['total_errors']}`",
            "",
            "## 🔑 Upstream GitHub API Rate Limit Quota",
            f"- **Core REST API:** `{quota['core_remaining']} / {quota['core_limit']}` remaining",
            f"- **Search API:** `{quota['search_remaining']} / {quota['search_limit']}` remaining",
            "",
            "## 🛠️ Tool Invocation Breakdown",
            "| Tool Name | Calls | Errors | Success % | Mean Latency | P95 Latency | Transferred |",
            "| :--- | :---: | :---: | :---: | :---: | :---: | :---: |",
        ]

        if not s["tools"]:
            lines.append("| *No invocations recorded* | - | - | - | - | - | - |")
        else:
            for tool, m in sorted(s["tools"].items()):
                lines.append(
                    f"| `{tool}` | {m['total_calls']} | {m['error_count']} | {m['success_rate_pct']}% | "
                    f"{m['mean_latency_ms']} ms | {m['p95_latency_ms']} ms | {m['total_bytes_transferred']} B |"
                )

        content = "\n".join(lines)
        if target_path:
            os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
            with open(target_path, "w", encoding="utf-8") as f:
                f.write(content)
        return content


# Global telemetry singleton
telemetry = MCPTelemetryTracker()
