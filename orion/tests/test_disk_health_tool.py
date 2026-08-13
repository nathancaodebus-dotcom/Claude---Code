import json
import subprocess

from tools import disk_health_tool
from tools.disk_health_tool import CheckDiskHealthTool


def _fake_run(stdout_data):
    def fake_run(cmd, capture_output, text, timeout):
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(stdout_data), stderr="")

    return fake_run


def test_reports_passed(monkeypatch):
    monkeypatch.setattr(disk_health_tool.subprocess, "run", _fake_run({"smart_status": {"passed": True}}))
    result = CheckDiskHealthTool().run(device="/dev/sda")
    assert "PASSED" in result


def test_reports_failed(monkeypatch):
    monkeypatch.setattr(disk_health_tool.subprocess, "run", _fake_run({"smart_status": {"passed": False}}))
    result = CheckDiskHealthTool().run(device="/dev/sda")
    assert "FAILED" in result


def test_reports_unknown_rather_than_failed_when_smart_status_is_missing(monkeypatch):
    """Regression test: smartctl can return valid JSON with no
    smart_status.passed field at all (an unsupported device/USB bridge, a
    permission issue) — reading that missing field as falsy used to report
    a hard 'FAILED' for a drive whose health is actually unknown, a false
    alarm rather than a missed one."""
    monkeypatch.setattr(disk_health_tool.subprocess, "run", _fake_run({"temperature": {"current": 40}}))

    result = CheckDiskHealthTool().run(device="/dev/sda")

    assert "UNKNOWN" in result
    assert "FAILED" not in result


def test_smartctl_not_installed(monkeypatch):
    def fake_run(cmd, capture_output, text, timeout):
        raise FileNotFoundError()

    monkeypatch.setattr(disk_health_tool.subprocess, "run", fake_run)
    result = CheckDiskHealthTool().run(device="/dev/sda")
    assert "not installed" in result
