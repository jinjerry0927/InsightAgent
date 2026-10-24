"""Bounded NVIDIA chat adapter. No database access, logging, or automatic retries."""

from __future__ import annotations

import math
import os
from dataclasses import dataclass, field
from pathlib import Path
from time import perf_counter
from typing import Mapping
from urllib.parse import urlsplit

from dotenv import dotenv_values
from openai import (
    APIConnectionError, APIError, APIStatusError, APITimeoutError,
    DefaultHttpxClient, OpenAI,
)

DEFAULT_BASE_URL = "https://integrate.api.nvidia.com/v1"
DEFAULT_MODEL = "nvidia/nemotron-3.5-lightning-30b-a3b"
MAX_INPUT_CHARS = 24_000
PROJECT_ROOT = Path(__file__).resolve().parents[1]


class LLMError(RuntimeError):
    """Safe public error; never include the provider's body, headers, or prompt."""

    def __init__(self, code: str, message: str, *, attempts: int = 0,
                 elapsed_seconds: float = 0, status_code: int | None = None,
                 usage: dict[str, int | None] | None = None):
        super().__init__(message)
        self.code = code
        self.attempts = attempts
        self.elapsed_seconds = elapsed_seconds
        self.status_code = status_code
        self.usage = usage


def config_error(message: str) -> LLMError:
    return LLMError("configuration", message)


@dataclass(frozen=True)
class NvidiaSettings:
    api_key: str = field(repr=False)
    base_url: str = DEFAULT_BASE_URL
    model: str = DEFAULT_MODEL
    timeout_seconds: float = 30
    max_tokens: int = 1024

    def __post_init__(self) -> None:
        if (not isinstance(self.api_key, str) or not self.api_key
                or not self.api_key.isascii() or not self.api_key.isprintable()
                or any(c.isspace() for c in self.api_key)):
            raise config_error("NVIDIA_API_KEY를 로컬 .env 또는 환경변수에 설정하세요.")
        try:
            url = urlsplit(self.base_url)
            valid_url = (url.scheme == "https" and url.hostname and not url.username
                         and not url.password and not url.query and not url.fragment
                         and not any(c.isspace() for c in self.base_url)
                         and "\\" not in self.base_url and url.port != 0)
        except (ValueError, TypeError, AttributeError):
            valid_url = False
        if not valid_url:
            raise config_error("NVIDIA_BASE_URL에는 인증정보·쿼리 없는 HTTPS 주소를 사용하세요.")
        if (not isinstance(self.model, str) or not self.model or len(self.model) > 200
                or any(c.isspace() for c in self.model)):
            raise config_error("NVIDIA_MODEL을 공백 없는 모델 이름으로 설정하세요.")
        if (isinstance(self.timeout_seconds, bool)
                or not isinstance(self.timeout_seconds, (int, float))
                or not math.isfinite(self.timeout_seconds)
                or not 0 < self.timeout_seconds <= 120):
            raise config_error("NVIDIA_TIMEOUT_SECONDS는 0 초과 120 이하 숫자여야 합니다.")
        if type(self.max_tokens) is not int or not 1 <= self.max_tokens <= 4096:
            raise config_error("NVIDIA_MAX_TOKENS는 1~4096 정수여야 합니다.")


def load_settings(env_file: Path = PROJECT_ROOT / ".env", *,
                  environ: Mapping[str, str] | None = None) -> NvidiaSettings:
    """Read only this project's file; process env wins, no interpolation/mutation."""
    try:
        local = dotenv_values(env_file, interpolate=False, encoding="utf-8-sig")
    except (OSError, UnicodeError):
        raise config_error("로컬 .env 파일을 UTF-8 텍스트로 읽을 수 없습니다.") from None
    values = {**local, **(os.environ if environ is None else environ)}

    def value(name: str, default: str = "") -> str:
        raw = values.get(name)
        return default if raw is None else raw.strip()

    try:
        timeout = float(value("NVIDIA_TIMEOUT_SECONDS", "30"))
        tokens = int(value("NVIDIA_MAX_TOKENS", "1024"))
    except ValueError:
        raise config_error("API 시간 제한과 출력 토큰 설정의 숫자 형식을 확인하세요.") from None
    return NvidiaSettings(
        api_key=value("NVIDIA_API_KEY"),
        base_url=value("NVIDIA_BASE_URL", DEFAULT_BASE_URL).rstrip("/"),
        model=value("NVIDIA_MODEL", DEFAULT_MODEL),
        timeout_seconds=timeout, max_tokens=tokens,
    )


@dataclass(frozen=True)
class CompletionResult:
    content: str = field(repr=False)
    model: str
    elapsed_seconds: float
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    attempts: int = 1


class NvidiaClient:
    def __init__(self, settings: NvidiaSettings, *,
                 http_client: DefaultHttpxClient | None = None):
        self.settings = settings
        if http_client is not None:
            http_client.follow_redirects = False
        self._client = OpenAI(
            api_key=settings.api_key, base_url=settings.base_url,
            organization="", project="",  # Do not forward unrelated OpenAI account metadata.
            timeout=settings.timeout_seconds, max_retries=0,
            # A redirect must not initiate a second request or forward credentials.
            http_client=http_client if http_client is not None else DefaultHttpxClient(
                follow_redirects=False, timeout=settings.timeout_seconds),
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> NvidiaClient:
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()

    def complete(self, prompt: str, *, system_prompt: str | None = None,
                 max_tokens: int | None = None) -> CompletionResult:
        if (not isinstance(prompt, str) or not prompt.strip()
                or system_prompt is not None and not isinstance(system_prompt, str)):
            raise LLMError("invalid_input", "질문과 시스템 문맥은 텍스트여야 합니다.")
        if len(prompt) + len(system_prompt or "") > MAX_INPUT_CHARS:
            raise LLMError("invalid_input", "질문과 문맥이 프로젝트 입력 길이 제한을 초과했습니다.")
        limit = self.settings.max_tokens if max_tokens is None else max_tokens
        if type(limit) is not int or not 1 <= limit <= self.settings.max_tokens:
            raise LLMError("invalid_input", "요청 출력 토큰은 설정 상한 이내의 양수 정수여야 합니다.")
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        started = perf_counter()
        try:
            response = self._client.chat.completions.create(
                model=self.settings.model, messages=messages, n=1,
                max_tokens=limit, temperature=1, top_p=0.95, stream=False,
                extra_body={"chat_template_kwargs": {"enable_thinking": False}},
            )
        except APITimeoutError:
            public_message = "API 응답 시간이 초과되어 종료했습니다."
            raise LLMError("timeout", public_message, attempts=1,
                           elapsed_seconds=perf_counter() - started) from None
        except APIConnectionError:
            public_message = "API 네트워크 연결에 실패했습니다."
            raise LLMError("connection", public_message, attempts=1,
                           elapsed_seconds=perf_counter() - started) from None
        except APIStatusError as exc:
            status = exc.status_code
            code = ("authentication" if status in (401, 403) else
                    "quota" if status == 429 else "timeout" if status == 408 else
                    "server" if status >= 500 else "request")
            public_message = "API 요청이 거부되거나 서버 오류로 종료했습니다."
            raise LLMError(code, public_message, attempts=1,
                           elapsed_seconds=perf_counter() - started, status_code=status) from None
        except (APIError, ValueError, TypeError):
            public_message = "API 응답 형식을 해석할 수 없습니다."
            raise LLMError("invalid_response", public_message, attempts=1,
                           elapsed_seconds=perf_counter() - started) from None

        elapsed = perf_counter() - started
        usage_counts = None

        def invalid(code: str, message: str) -> LLMError:
            return LLMError(code, message, attempts=1, elapsed_seconds=elapsed, usage=usage_counts)

        names = ("prompt_tokens", "completion_tokens", "total_tokens")
        usage = getattr(response, "usage", None)
        counts = [getattr(usage, name, None) for name in names]
        if any(c is not None and (type(c) is not int or c < 0) for c in counts):
            raise invalid("invalid_response", "API 사용량 형식이 올바르지 않습니다.")
        if any(c is not None for c in counts):
            usage_counts = dict(zip(names, counts))

        choices = getattr(response, "choices", None)
        if not isinstance(choices, list) or len(choices) != 1:
            raise invalid("invalid_response", "API 응답에 단일 답변이 없습니다.")
        choice = choices[0]
        reason = getattr(choice, "finish_reason", None)
        if reason == "length":
            raise invalid("output_limit", "출력 토큰 제한에 도달해 불완전한 답변을 폐기했습니다.")
        message = getattr(choice, "message", None)
        if reason != "stop" or getattr(message, "tool_calls", None):
            raise invalid("unsupported_response", "API가 정상 텍스트 답변으로 종료되지 않았습니다.")
        content = getattr(message, "content", None)
        if not isinstance(content, str) or not content.strip():
            raise invalid("empty_response", "API의 텍스트 답변이 비어 있습니다.")
        return CompletionResult(content.strip(), self.settings.model, elapsed, *counts)
