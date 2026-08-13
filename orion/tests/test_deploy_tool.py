import json

import pytest

from tools.deploy_tool import ListDeployCommandsTool, RunDeployCommandTool


@pytest.fixture(autouse=True)
def deploy_commands():
    from core.config import config

    object.__setattr__(config, "deploy_commands", json.dumps({"echo_test": "echo hello"}))
    yield
    object.__setattr__(config, "deploy_commands", None)


def test_run_known_command():
    result = RunDeployCommandTool().run(name="echo_test")
    assert "hello" in result


def test_run_unknown_command():
    result = RunDeployCommandTool().run(name="does_not_exist")
    assert "No command named" in result
    assert "echo_test" in result


def test_list_commands():
    result = ListDeployCommandsTool().run()
    assert "echo_test" in result


def test_list_commands_empty():
    from core.config import config

    object.__setattr__(config, "deploy_commands", None)
    result = ListDeployCommandsTool().run()
    assert "No deploy commands" in result
