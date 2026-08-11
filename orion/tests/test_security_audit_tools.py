from tools.security_audit_tools import SecurityAuditCodeTool


def test_audit_finds_no_issues_in_clean_code(tmp_path):
    (tmp_path / "clean.py").write_text("def add(a, b):\n    return a + b\n")

    result = SecurityAuditCodeTool().run(directory=str(tmp_path))
    assert "No issues found" in result


def test_audit_finds_known_issue(tmp_path):
    # eval() on dynamic input is a classic bandit-flagged pattern (B307).
    (tmp_path / "risky.py").write_text("import os\ndef run(cmd):\n    return eval(cmd)\n")

    result = SecurityAuditCodeTool().run(directory=str(tmp_path))
    assert "eval" in result.lower() or "B307" in result
