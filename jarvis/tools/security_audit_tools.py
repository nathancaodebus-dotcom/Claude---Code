"""Basic, defensive code security checks for the user's own projects:
static analysis (bandit) and known-vulnerability lookups for installed
dependencies (OSV.dev, free/keyless)."""
from __future__ import annotations

import json
import subprocess
import sys

import httpx

from tools.base import Tool


class SecurityAuditCodeTool(Tool):
    name = "audit_code_security"
    description = "Run a static security scan (bandit) over a Python project directory and summarize findings."
    input_schema = {
        "type": "object",
        "properties": {"directory": {"type": "string"}},
        "required": ["directory"],
    }

    def run(self, directory: str) -> str:
        try:
            result = subprocess.run(
                [sys.executable, "-m", "bandit", "-r", directory, "-f", "json"],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except FileNotFoundError:
            return "bandit is not installed. Install it with: pip install bandit"

        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return f"Could not parse bandit output:\n{result.stdout or result.stderr}"

        issues = data.get("results", [])
        if not issues:
            return f"No issues found by bandit in '{directory}'."

        lines = []
        for issue in issues[:30]:
            lines.append(
                f"- [{issue['issue_severity']}] {issue['test_name']} in {issue['filename']}:"
                f"{issue['line_number']} — {issue['issue_text']}"
            )
        return "\n".join(lines)


class CheckDependencyVulnerabilitiesTool(Tool):
    name = "check_dependency_vulnerabilities"
    description = (
        "Check a package (by name and version, e.g. name='requests', version='2.25.0') against "
        "the OSV.dev database of known vulnerabilities."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "package_name": {"type": "string"},
            "version": {"type": "string"},
            "ecosystem": {"type": "string", "description": "Default 'PyPI'."},
        },
        "required": ["package_name", "version"],
    }

    def run(self, package_name: str, version: str, ecosystem: str = "PyPI") -> str:
        response = httpx.post(
            "https://api.osv.dev/v1/query",
            json={"package": {"name": package_name, "ecosystem": ecosystem}, "version": version},
            timeout=15,
        )
        response.raise_for_status()
        vulns = response.json().get("vulns", [])
        if not vulns:
            return f"No known vulnerabilities found for {package_name} {version}."

        lines = []
        for vuln in vulns:
            summary = vuln.get("summary", vuln.get("details", "")[:200])
            lines.append(f"- {vuln['id']}: {summary}")
        return "\n".join(lines)
