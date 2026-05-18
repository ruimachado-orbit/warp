import json
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import llm_gateway


class FakeOpenAI:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))
        self.requests = []
        FakeOpenAI.instances.append(self)

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = SimpleNamespace(content="provider response")
        choice = SimpleNamespace(message=message)
        return SimpleNamespace(model=kwargs["model"], choices=[choice])


def install_fake_openai(monkeypatch):
    FakeOpenAI.instances = []
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))


class FakeStdin:
    def __init__(self):
        self.writes = []
        self.closed = False

    def write(self, value):
        self.writes.append(value)

    def flush(self):
        pass

    def close(self):
        self.closed = True

    @property
    def messages(self):
        return [json.loads(value) for value in self.writes if value.strip()]


class FakeStdout:
    def __init__(self, lines):
        self.lines = list(lines)

    def readline(self):
        if self.lines:
            return self.lines.pop(0)
        return ""


class FakeProcess:
    def __init__(self, cmd, kwargs, stdout_lines):
        self.cmd = cmd
        self.kwargs = kwargs
        self.stdin = FakeStdin()
        self.stdout = FakeStdout(stdout_lines)
        self.stderr = FakeStdout([])
        self.returncode = None
        self.terminated = False
        self.killed = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True
        self.returncode = -15

    def kill(self):
        self.killed = True
        self.returncode = -9

    def wait(self, timeout=None):
        if self.returncode is None:
            self.returncode = 0
        return self.returncode


def codex_success_lines(text_parts=("hello ", "world")):
    lines = [
        {"jsonrpc": "2.0", "id": 1, "result": {}},
        {"jsonrpc": "2.0", "id": 2, "result": {"threadId": "thread-1"}},
        {"jsonrpc": "2.0", "id": 3, "result": {}},
    ]
    lines.extend(
        {"jsonrpc": "2.0", "method": "item/agentMessage/delta", "params": {"delta": part}}
        for part in text_parts
    )
    lines.append(
        {"jsonrpc": "2.0", "method": "turn/completed", "params": {"threadId": "thread-1", "status": "completed"}}
    )
    return [json.dumps(line) + "\n" for line in lines]


def install_fake_codex_process(monkeypatch, stdout_lines=None):
    processes = []
    lines = codex_success_lines() if stdout_lines is None else stdout_lines

    def fake_popen(cmd, **kwargs):
        process = FakeProcess(cmd, kwargs, list(lines))
        processes.append(process)
        return process

    monkeypatch.setattr(llm_gateway.subprocess, "Popen", fake_popen)
    return processes


def test_openrouter_uses_openai_compatible_client(monkeypatch):
    install_fake_openai(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "anthropic/claude-3.5-sonnet")
    monkeypatch.setenv("OPENROUTER_HTTP_REFERER", "https://warp.example")

    result = llm_gateway._call_provider("openrouter", "hello", "system", 50, 0.1, True)

    assert result == {
        "ok": True,
        "text": "provider response",
        "provider": "openrouter",
        "model": "anthropic/claude-3.5-sonnet",
        "error": None,
    }
    client = FakeOpenAI.instances[0]
    assert client.kwargs["api_key"] == "or-key"
    assert client.kwargs["base_url"] == "https://openrouter.ai/api/v1"
    assert client.kwargs["default_headers"]["HTTP-Referer"] == "https://warp.example"
    assert client.requests[0]["response_format"] == {"type": "json_object"}


def test_openrouter_accepts_explicit_model_override(monkeypatch):
    install_fake_openai(monkeypatch)
    monkeypatch.setenv("OPENROUTER_API_KEY", "or-key")
    monkeypatch.setenv("OPENROUTER_MODEL", "ignored/model")

    result = llm_gateway.call_with_fallback(
        "hello",
        providers=["openrouter"],
        system="system",
        max_tokens=50,
        temperature=0.1,
        json_output=True,
        model="deepseek/deepseek-v4-flash",
    )

    assert result["ok"] is True
    assert result["model"] == "deepseek/deepseek-v4-flash"
    assert FakeOpenAI.instances[0].requests[0]["model"] == "deepseek/deepseek-v4-flash"


def test_openai_uses_configurable_model(monkeypatch):
    install_fake_openai(monkeypatch)
    monkeypatch.setenv("OPENAI_API_KEY", "oa-key")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-pr0")

    result = llm_gateway._call_provider("openai", "hello", "system", 75, 0.3, False)

    assert result["ok"] is True
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-pr0"
    client = FakeOpenAI.instances[0]
    assert client.kwargs["api_key"] == "oa-key"
    assert "base_url" not in client.kwargs
    assert client.requests[0]["model"] == "gpt-pr0"
    assert "response_format" not in client.requests[0]


def test_codex_alias_dispatch_uses_app_server_stdio(monkeypatch):
    monkeypatch.delenv("CODEX_APP_SERVER_URL", raising=False)
    processes = install_fake_codex_process(monkeypatch, codex_success_lines(("alias response",)))

    result = llm_gateway._call_provider("codex-app-server", "hello", "system", 100, 0.2, False)

    assert result == {
        "ok": True,
        "text": "alias response",
        "provider": "codex_app_server",
        "model": "gpt-5.5",
        "error": None,
    }
    assert processes[0].cmd == ["codex", "app-server", "--listen", "stdio://"]


def test_codex_app_server_stdio_protocol(monkeypatch):
    monkeypatch.delenv("CODEX_APP_SERVER_URL", raising=False)
    processes = install_fake_codex_process(monkeypatch)

    result = llm_gateway._call_provider("codex", "hello", "system", 100, 0.2, True)

    assert result == {
        "ok": True,
        "text": "hello world",
        "provider": "codex_app_server",
        "model": "gpt-5.5",
        "error": None,
    }
    sent = processes[0].stdin.messages
    assert [message["method"] for message in sent] == ["initialize", "initialized", "thread/start", "turn/start"]

    thread_start = sent[2]
    assert thread_start["params"]["ephemeral"] is True
    assert thread_start["params"]["model"] == "gpt-5.5"
    assert thread_start["params"]["approvalPolicy"] == "never"
    assert thread_start["params"]["sandbox"] == "read-only"

    turn_start = sent[3]
    assert turn_start["params"]["threadId"] == "thread-1"
    input_text = turn_start["params"]["input"][0]["text"]
    assert "system" in input_text
    assert "hello" in input_text
    assert "Return valid JSON only." in input_text
    assert "Do not run shell commands or edit files." not in input_text
    assert processes[0].terminated is True


def test_codex_app_server_stdio_uses_env_overrides(monkeypatch):
    monkeypatch.setenv("CODEX_APP_SERVER_URL", "stdio://")
    monkeypatch.setenv("CODEX_APP_SERVER_COMMAND", "/custom/codex")
    monkeypatch.setenv("CODEX_APP_SERVER_MODEL", "gpt-custom")
    monkeypatch.setenv("CODEX_APP_SERVER_TIMEOUT", "12")
    monkeypatch.setenv("CODEX_APP_SERVER_CWD", "/tmp/project")
    monkeypatch.setenv("CODEX_APP_SERVER_SANDBOX", "workspace-write")
    monkeypatch.setenv("CODEX_APP_SERVER_APPROVAL_POLICY", "on-request")
    processes = install_fake_codex_process(monkeypatch, codex_success_lines(("custom",)))

    result = llm_gateway._call_provider("codex_app_server", "hello", None, 100, 0.2, False)

    assert result["ok"] is True
    assert result["model"] == "gpt-custom"
    assert processes[0].cmd == ["/custom/codex", "app-server", "--listen", "stdio://"]
    thread_start = processes[0].stdin.messages[2]
    assert thread_start["params"]["cwd"] == "/tmp/project"
    assert thread_start["params"]["model"] == "gpt-custom"
    assert thread_start["params"]["sandbox"] == "workspace-write"
    assert thread_start["params"]["approvalPolicy"] == "on-request"


def test_codex_app_server_early_exit_fails_promptly(monkeypatch):
    monkeypatch.delenv("CODEX_APP_SERVER_URL", raising=False)
    monkeypatch.setenv("CODEX_APP_SERVER_TIMEOUT", "0.5")
    install_fake_codex_process(monkeypatch, stdout_lines=[])

    result = llm_gateway._call_provider("codex_app_server", "hello", None, 100, 0.2, False)

    assert result["ok"] is False
    assert "closed stdout before sending a response" in result["error"]


def test_codex_app_server_unsupported_transport_fails_provider_locally(monkeypatch):
    monkeypatch.setenv("CODEX_APP_SERVER_URL", "ws://127.0.0.1:3030")

    result = llm_gateway._call_provider("codex_app_server", "hello", None, 100, 0.2, False)

    assert result["ok"] is False
    assert result["provider"] == "codex_app_server"
    assert "Unsupported Codex app-server transport" in result["error"]


def test_provider_local_failure_allows_fallback_with_visible_warning(monkeypatch):
    def fake_call_provider(provider, prompt, system, max_tokens, temperature, json_output, model=None, json_schema=None):
        if provider == "codex_app_server":
            return {"ok": False, "provider": "codex_app_server", "error": "nope"}
        if provider == "openai":
            return {"ok": True, "provider": "openai", "text": "fallback", "model": "gpt-test", "error": None}
        raise AssertionError(f"unexpected provider {provider}")

    monkeypatch.setattr(llm_gateway, "_call_provider", fake_call_provider)

    result = llm_gateway.call_with_fallback("hello", providers=["codex_app_server", "openai"])

    assert result["ok"] is True
    assert result["provider"] == "openai"
    assert result["text"] == "fallback"
    assert result["warnings"] == [{"provider": "codex_app_server", "error": "nope"}]


def test_all_provider_failures_include_provider_errors(monkeypatch):
    def fake_call_provider(provider, prompt, system, max_tokens, temperature, json_output, model=None, json_schema=None):
        return {"ok": False, "provider": provider, "error": f"{provider} failed visibly"}

    monkeypatch.setattr(llm_gateway, "_call_provider", fake_call_provider)

    result = llm_gateway.call_with_fallback("hello", providers=["codex_app_server", "openai"])

    assert result["ok"] is False
    assert "codex_app_server: codex_app_server failed visibly" in result["error"]
    assert "openai: openai failed visibly" in result["error"]
    assert len(result["warnings"]) == 2


def test_status_includes_openrouter_and_codex_app_server(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("CODEX_APP_SERVER_URL", raising=False)

    result = llm_gateway.status()

    assert result["default_order"] == ["anthropic", "openai", "openrouter", "codex_app_server"]
    assert result["providers"]["openrouter"]["configured"] is False
    assert result["providers"]["codex_app_server"]["configured"] is True
    assert result["providers"]["codex_app_server"]["transport"] == "stdio://"
    assert result["providers"]["codex_app_server"]["supported"] is True
