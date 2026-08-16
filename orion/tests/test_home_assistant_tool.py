"""tools/home_assistant_tool.py's confirmation gate for dangerous domains.
Regression coverage for a real bug found during a full-codebase audit:
CallServiceTool was a raw passthrough to *any* Home Assistant domain.service
with no allowlist and no confirmation step, so a misheard voice command or a
jailbroken request could unlock a door or disarm an alarm in one shot."""
from __future__ import annotations

import tools.home_assistant_tool as home_assistant_tool_module
from tools.home_assistant_tool import (
    CallServiceTool,
    ConfirmSmartHomeActionTool,
    ListDevicesTool,
)


class _FakeResponse:
    def __init__(self, payload=None):
        self._payload = payload if payload is not None else {}

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_list_devices_still_works(monkeypatch):
    calls = []
    monkeypatch.setattr(
        home_assistant_tool_module.client,
        "get",
        lambda *a, **kw: calls.append((a, kw)) or _FakeResponse(
            [{"entity_id": "light.living_room", "state": "on"}]
        ),
    )

    result = ListDevicesTool().run()

    assert len(calls) == 1
    assert "light.living_room: on" in result


def test_non_dangerous_domain_executes_immediately(monkeypatch):
    calls = []
    monkeypatch.setattr(
        home_assistant_tool_module.client,
        "post",
        lambda *a, **kw: calls.append((a, kw)) or _FakeResponse(),
    )

    result = CallServiceTool().run(domain="light", service="turn_on", entity_id="light.living_room")

    assert len(calls) == 1
    assert "Called light.turn_on on light.living_room" in result


def test_dangerous_domain_is_proposed_not_executed(monkeypatch):
    calls = []
    monkeypatch.setattr(
        home_assistant_tool_module.client,
        "post",
        lambda *a, **kw: calls.append((a, kw)) or _FakeResponse(),
    )

    result = CallServiceTool().run(domain="lock", service="unlock", entity_id="lock.front_door")

    assert calls == []  # never called Home Assistant
    assert "Proposal #1" in result
    assert "PENDING" in result


def test_confirming_a_valid_pending_action_executes_it(monkeypatch):
    calls = []
    monkeypatch.setattr(
        home_assistant_tool_module.client,
        "post",
        lambda *a, **kw: calls.append((a, kw)) or _FakeResponse(),
    )

    call_service_tool = CallServiceTool()
    confirm_tool = ConfirmSmartHomeActionTool(call_service_tool)

    proposal = call_service_tool.run(domain="lock", service="unlock", entity_id="lock.front_door")
    assert calls == []

    result = confirm_tool.run(action_id=1)

    assert len(calls) == 1
    assert "Called lock.unlock on lock.front_door" in result
    assert "#1" in proposal


def test_confirming_an_unknown_action_id_does_not_call_home_assistant(monkeypatch):
    calls = []
    monkeypatch.setattr(
        home_assistant_tool_module.client,
        "post",
        lambda *a, **kw: calls.append((a, kw)) or _FakeResponse(),
    )

    call_service_tool = CallServiceTool()
    confirm_tool = ConfirmSmartHomeActionTool(call_service_tool)

    result = confirm_tool.run(action_id=999)

    assert calls == []
    assert "No pending action #999" in result


def test_confirming_the_same_action_id_twice_only_executes_once(monkeypatch):
    calls = []
    monkeypatch.setattr(
        home_assistant_tool_module.client,
        "post",
        lambda *a, **kw: calls.append((a, kw)) or _FakeResponse(),
    )

    call_service_tool = CallServiceTool()
    confirm_tool = ConfirmSmartHomeActionTool(call_service_tool)

    call_service_tool.run(domain="alarm_control_panel", service="alarm_disarm", entity_id="alarm_control_panel.home")

    first = confirm_tool.run(action_id=1)
    second = confirm_tool.run(action_id=1)

    assert len(calls) == 1
    assert "Called alarm_control_panel.alarm_disarm" in first
    assert "No pending action #1" in second
