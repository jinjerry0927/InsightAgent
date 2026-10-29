"""Exercise the installed SDK through its in-memory HTTP transport; no API key/network."""

import json
import traceback

import httpx2
import pytest
from openai import DefaultHttpxClient

from scripts import check_nvidia
from scripts.llm_client import (
    DEFAULT_BASE_URL, DEFAULT_MODEL, LLMError, MAX_INPUT_CHARS,
    NvidiaClient, NvidiaSettings, load_settings,
)

DUMMY_KEY = "offline-key-DO-NOT-SEND"
PRIVATE_BODY = "provider-private-body-MUST-NOT-LOG"


def completion(*, content="OK", reason="stop", usage=True):
    body = {
        "id": "offline-completion", "object": "chat.completion", "created": 1,
        "model": DEFAULT_MODEL,
        "choices": [{"index": 0, "finish_reason": reason,
                     "message": {"role": "assistant", "content": content}}],
    }
    if usage:
        body["usage"] = {"prompt_tokens": 9, "completion_tokens": 1, "total_tokens": 10}
    return body


def mocked_client(handler, **config):
    http = DefaultHttpxClient(transport=httpx2.MockTransport(handler), follow_redirects=False)
    return NvidiaClient(NvidiaSettings(api_key=DUMMY_KEY, **config), http_client=http)


def test_env_is_explicit_process_wins_no_interpolation_or_mutation(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("\ufeffNVIDIA_API_KEY=file-key\nNVIDIA_MODEL=file/model\n", encoding="utf-8")
    monkeypatch.delenv("NVIDIA_MODEL", raising=False)
    settings = load_settings(env_file, environ={"NVIDIA_API_KEY": DUMMY_KEY})
    assert settings.api_key == DUMMY_KEY
    assert settings.model == "file/model"
    assert DUMMY_KEY not in repr(settings)
    import os
    assert "NVIDIA_MODEL" not in os.environ
    env_file.write_text("NVIDIA_API_KEY=${MISSING_VARIABLE}\n", encoding="utf-8")
    assert load_settings(env_file, environ={}).api_key == "${MISSING_VARIABLE}"


def test_missing_key_and_blank_process_override_fail_before_network(tmp_path):
    for env_file, environ in ((tmp_path / "absent", {}),
                              (tmp_path / ".env", {"NVIDIA_API_KEY": ""})):
        (tmp_path / ".env").write_text("NVIDIA_API_KEY=file-key\n", encoding="utf-8")
        with pytest.raises(LLMError) as error:
            load_settings(env_file, environ=environ)
        assert error.value.code == "configuration"
        assert error.value.attempts == 0


@pytest.mark.parametrize("config", [
    {"base_url": "http://example.test/v1"},
    {"base_url": "https://user:password@example.test/v1"},
    {"base_url": "https://example.test/v1?key=private"},
    {"base_url": "https://example.test/v1#private"},
    {"base_url": "https://example.test:bad/v1"},
    {"base_url": "https://example.test\\other/v1"},
    {"model": ""}, {"model": "model with spaces"},
    {"timeout_seconds": 0}, {"timeout_seconds": float("nan")},
    {"timeout_seconds": 121}, {"max_tokens": 0}, {"max_tokens": 4097},
    {"max_tokens": True}, {"api_key": "key\nprivate"},
])
def test_invalid_settings_are_safe(config):
    with pytest.raises(LLMError) as error:
        NvidiaSettings(**{"api_key": DUMMY_KEY, **config})
    assert error.value.code == "configuration"
    assert "password" not in str(error.value)
    assert DUMMY_KEY not in str(error.value)


@pytest.mark.parametrize("name,value", [
    ("NVIDIA_MAX_TOKENS", "1.5"), ("NVIDIA_TIMEOUT_SECONDS", "private-invalid-number"),
])
def test_bad_env_numbers_do_not_echo_values(tmp_path, name, value):
    with pytest.raises(LLMError) as error:
        load_settings(tmp_path / "absent", environ={"NVIDIA_API_KEY": DUMMY_KEY, name: value})
    assert error.value.attempts == 0
    assert value not in str(error.value)


def test_real_sdk_request_and_result_contract(monkeypatch):
    monkeypatch.setenv("OPENAI_ORG_ID", "unrelated-private-organization")
    monkeypatch.setenv("OPENAI_PROJECT_ID", "unrelated-private-project")
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(200, json=completion(content=" SELECT 1; "))

    with mocked_client(handler, base_url="https://custom.example/v1", model="custom/model") as client:
        result = client.complete("question", system_prompt="limited schema", max_tokens=64)
        assert client._client.max_retries == 0
        assert client._client.timeout == 30
    assert len(requests) == 1
    request = requests[0]
    assert str(request.url) == "https://custom.example/v1/chat/completions"
    assert request.headers["authorization"] == f"Bearer {DUMMY_KEY}"
    assert "unrelated-private" not in str(request.headers)
    body = json.loads(request.content)
    assert body["messages"] == [{"role": "system", "content": "limited schema"},
                                {"role": "user", "content": "question"}]
    assert body["model"] == "custom/model"
    assert body["max_tokens"] == 64
    assert body["stream"] is False and body["n"] == 1
    assert body["chat_template_kwargs"] == {"enable_thinking": False}
    assert result.content == "SELECT 1;"
    assert result.model == "custom/model" and result.attempts == 1
    assert (result.prompt_tokens, result.completion_tokens, result.total_tokens) == (9, 1, 10)
    assert result.elapsed_seconds >= 0
    assert "SELECT" not in repr(result)


@pytest.mark.parametrize("status,code", [
    (400, "request"), (401, "authentication"), (403, "authentication"),
    (404, "request"), (408, "timeout"), (429, "quota"), (500, "server"), (503, "server"),
    (307, "request"),
])
def test_http_failures_and_redirect_stop_after_one_request(status, code, caplog):
    requests = []

    def handler(request):
        requests.append(request)
        return httpx2.Response(status, json={"error": {"message": PRIVATE_BODY + DUMMY_KEY}},
                               headers={"Location": "https://other.example/v1", "Retry-After": "0"})

    with mocked_client(handler) as client:
        prompt = "private-prompt"
        with pytest.raises(LLMError) as error:
            client.complete(prompt)
        rendered = "".join(traceback.format_exception(error.value))
    assert error.value.code == code and error.value.status_code == status
    assert error.value.attempts == 1 and len(requests) == 1
    assert PRIVATE_BODY not in rendered + caplog.text
    assert DUMMY_KEY not in rendered + caplog.text
    assert "private-prompt" not in rendered + caplog.text


@pytest.mark.parametrize("failure,code", [
    (httpx2.ReadTimeout, "timeout"), (httpx2.ConnectError, "connection"),
])
def test_network_failures_do_not_retry(failure, code):
    requests = []

    def handler(request):
        requests.append(request)
        raise failure(PRIVATE_BODY, request=request)

    with mocked_client(handler) as client:
        with pytest.raises(LLMError) as error:
            client.complete("question")
    assert error.value.code == code and error.value.attempts == 1
    assert len(requests) == 1
    assert PRIVATE_BODY not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("body,code", [
    ({"choices": []}, "invalid_response"),
    ({"choices": "invalid"}, "invalid_response"),
    (completion(content=""), "empty_response"),
    (completion(content=None), "empty_response"),
    (completion(reason="length"), "output_limit"),
    (completion(reason="content_filter"), "unsupported_response"),
    (completion(reason="tool_calls"), "unsupported_response"),
])
def test_unusable_response_never_becomes_a_success(body, code):
    with mocked_client(lambda request: httpx2.Response(200, json=body)) as client:
        with pytest.raises(LLMError) as error:
            client.complete("question")
    assert error.value.code == code and error.value.attempts == 1
    if body.get("usage"):
        assert error.value.usage["total_tokens"] == 10


def test_invalid_usage_is_not_a_measured_zero():
    body = completion()
    body["usage"]["total_tokens"] = -1
    with mocked_client(lambda request: httpx2.Response(200, json=body)) as client:
        with pytest.raises(LLMError) as error:
            client.complete("question")
    assert error.value.code == "invalid_response" and error.value.usage is None


def test_missing_usage_is_unknown_not_zero_and_bad_json_is_safe():
    with mocked_client(lambda request: httpx2.Response(200, json=completion(usage=False))) as client:
        result = client.complete("question")
    assert result.prompt_tokens is result.completion_tokens is result.total_tokens is None
    with mocked_client(lambda request: httpx2.Response(
            200, content=PRIVATE_BODY, headers={"Content-Type": "application/json"})) as client:
        with pytest.raises(LLMError) as error:
            client.complete("question")
    assert error.value.code == "invalid_response"
    assert PRIVATE_BODY not in "".join(traceback.format_exception(error.value))


@pytest.mark.parametrize("prompt,kwargs", [
    ("", {}), (None, {}), ("q", {"system_prompt": 7}),
    ("q" * (MAX_INPUT_CHARS + 1), {}),
    ("q", {"system_prompt": "s" * MAX_INPUT_CHARS}),
    ("q", {"max_tokens": 0}), ("q", {"max_tokens": 1025}),
])
def test_invalid_input_uses_zero_requests(prompt, kwargs):
    def unexpected(request):
        pytest.fail("Invalid input must not reach the HTTP transport")

    with mocked_client(unexpected) as client:
        with pytest.raises(LLMError) as error:
            client.complete(prompt, **kwargs)
    assert error.value.code == "invalid_input" and error.value.attempts == 0


def test_connection_check_requires_live_and_never_logs_response(monkeypatch):
    monkeypatch.setattr(check_nvidia, "load_settings", lambda: NvidiaSettings(api_key=DUMMY_KEY))
    requests = []

    def factory(settings):
        def handler(request):
            requests.append(json.loads(request.content))
            return httpx2.Response(200, json=completion(content=PRIVATE_BODY))
        return mocked_client(handler)

    monkeypatch.setattr(check_nvidia, "NvidiaClient", factory)
    dry = check_nvidia.check_connection()
    assert dry["status"] == "ready" and dry["attempts"] == 0 and not requests
    live = check_nvidia.check_connection(live=True)
    assert live["status"] == "ok" and live["attempts"] == 1
    assert live["usage"]["total_tokens"] == 10
    assert len(requests) == 1 and requests[0]["max_tokens"] == 64
    assert requests[0]["messages"] == [{"role": "user", "content": check_nvidia.SMOKE_PROMPT}]
    assert PRIVATE_BODY not in json.dumps(live) and DUMMY_KEY not in json.dumps(live)


def test_cli_configuration_failure_has_zero_calls_safe_evidence(tmp_path, monkeypatch, capsys):
    def missing():
        raise LLMError("configuration", "NVIDIA_API_KEY 설정이 필요합니다.")

    monkeypatch.setattr(check_nvidia, "load_settings", missing)
    monkeypatch.setattr(check_nvidia, "PROJECT_ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["check_nvidia", "--live"])
    assert check_nvidia.main() == 2
    report = json.loads(capsys.readouterr().out)
    assert report["attempts"] == 0 and report["error_code"] == "configuration"
    saved = tmp_path / "data/processed/nvidia_connection_check.json"
    assert json.loads(saved.read_text(encoding="utf-8")) == report
