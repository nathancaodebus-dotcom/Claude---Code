import json
import subprocess

from tools import security_audit_tools
from tools.security_audit_tools import SecurityAuditCodeTool


def _issue(severity, test_name="test", filename="x.py", line=1):
    return {
        "issue_severity": severity,
        "test_name": test_name,
        "filename": filename,
        "line_number": line,
        "issue_text": f"{severity} issue",
    }


def test_findings_are_sorted_by_severity_not_scan_order(monkeypatch):
    """Regression test: bandit's results are ordered by scan position
    (file/line), not severity. Truncating to the first 30 in that raw
    order used to be able to silently drop a real HIGH-severity finding
    that happened to occur after many earlier LOW ones — a false negative
    in a tool whose entire purpose is surfacing real issues."""
    issues = [_issue("LOW", line=i) for i in range(29)] + [_issue("HIGH", line=99)]

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"results": issues}), stderr="")

    monkeypatch.setattr(security_audit_tools.subprocess, "run", fake_run)

    result = SecurityAuditCodeTool().run(directory="/fake")

    lines = [line for line in result.splitlines() if line.startswith("- [")]
    assert lines[0].startswith("- [HIGH]"), "HIGH-severity finding should sort first, not be truncated away"


def test_truncation_is_noted_when_there_are_more_than_30_issues(monkeypatch):
    issues = [_issue("LOW", line=i) for i in range(35)]

    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps({"results": issues}), stderr="")

    monkeypatch.setattr(security_audit_tools.subprocess, "run", fake_run)

    result = SecurityAuditCodeTool().run(directory="/fake")

    assert "5 more" in result
    assert "35 total" in result


def test_audit_finds_no_issues_in_clean_code(tmp_path):
    (tmp_path / "clean.py").write_text("def add(a, b):\n    return a + b\n")

    result = SecurityAuditCodeTool().run(directory=str(tmp_path))
    assert "No issues found" in result


def test_audit_finds_known_issue(tmp_path):
    # eval() on dynamic input is a classic bandit-flagged pattern (B307).
    (tmp_path / "risky.py").write_text("import os\ndef run(cmd):\n    return eval(cmd)\n")

    result = SecurityAuditCodeTool().run(directory=str(tmp_path))
    assert "eval" in result.lower() or "B307" in result
