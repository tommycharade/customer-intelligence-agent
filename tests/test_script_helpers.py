import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "research_stack_script", Path(__file__).parents[1] / "scripts/research_stack.py"
)
script = importlib.util.module_from_spec(spec)
spec.loader.exec_module(script)


@pytest.mark.parametrize("port", ["8766", "18766"])
def test_helper_uses_running_compose_binding(monkeypatch, port):
    monkeypatch.setenv("CIA_DOCKER_PORT", "9999")

    def output(command, *, text):
        assert command == ["docker", "compose", "port", "intelligence", "8765"]
        assert text
        return f"127.0.0.1:{port}\n"

    monkeypatch.setattr(script.subprocess, "check_output", output)
    assert script.docker_url() == f"http://127.0.0.1:{port}"


@pytest.mark.parametrize("binding", ["", "0.0.0.0:8766", "127.0.0.1:0", "127.0.0.1:70000"])
def test_helper_requires_one_loopback_binding(monkeypatch, binding):
    monkeypatch.setattr(script.subprocess, "check_output", lambda *args, **kwargs: binding)
    with pytest.raises(SystemExit, match="must publish one port on 127.0.0.1"):
        script.docker_url()
