"""Клиент модели. Два формата API, выбор через LLM_PROVIDER в .env:

- openai    — OpenAI-совместимый API (OpenRouter, DeepSeek, vLLM и т. п.);
- anthropic — Anthropic Messages API (в том числе шлюзы с этим форматом).

Агент и защиты работают с нейтральным форматом сообщений:
  {"role": "user", "content": str}
  {"role": "assistant", "content": str, "tool_calls": [ToolCall, ...]}
  {"role": "tool", "tool_call_id": str, "name": str, "content": str}
"""

import json
import os
import random
import time
from collections import deque
from dataclasses import dataclass, field

from dotenv import load_dotenv

RETRY_STATUS = {408, 409, 429, 500, 502, 503, 504, 529}


@dataclass
class ToolCall:
    id: str
    name: str
    args: dict


@dataclass
class Reply:
    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)


@dataclass
class Usage:
    requests: int = 0
    input_tokens: int = 0
    output_tokens: int = 0


class LLMError(RuntimeError):
    pass


class LLM:
    """Общая часть: повторы, лимит запросов в минуту, учёт токенов."""

    def __init__(self, model: str, temperature: float = 0.3, max_tokens: int = 2048,
                 rpm: int = 0, extra_body: dict | None = None):
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.rpm = rpm
        self.extra_body = extra_body or {}
        self.usage = Usage()
        self._sent = deque()

    def chat(self, system: str, messages: list[dict], tools: list[dict] | None = None) -> Reply:
        delays = [2, 5, 10, 20, 40]
        for attempt in range(len(delays) + 1):
            self._wait_rpm()
            try:
                return self._chat(system, messages, tools or [])
            except Exception as error:  # noqa: BLE001 — разбираем ниже
                status = getattr(error, "status_code", None)
                retryable = status in RETRY_STATUS or status is None and _is_network(error)
                if not retryable or attempt == len(delays):
                    raise LLMError(f"Запрос к модели не удался: {error}") from error
                delay = _retry_after(error) or delays[attempt] + random.random()
                print(f"  [модель] {status or type(error).__name__}, повтор через {delay:.0f} с")
                time.sleep(delay)
        raise AssertionError("unreachable")

    def _wait_rpm(self):
        if not self.rpm:
            return
        now = time.monotonic()
        while self._sent and now - self._sent[0] > 61:
            self._sent.popleft()
        if len(self._sent) >= self.rpm:
            pause = 61 - (now - self._sent[0])
            print(f"  [модель] лимит {self.rpm} запросов в минуту, пауза {pause:.0f} с")
            time.sleep(max(pause, 0))
        self._sent.append(time.monotonic())

    def _chat(self, system, messages, tools) -> Reply:
        raise NotImplementedError


class OpenAILLM(LLM):
    def __init__(self, base_url: str, api_key: str, **kwargs):
        super().__init__(**kwargs)
        from openai import OpenAI
        self.client = OpenAI(base_url=base_url or None, api_key=api_key, max_retries=0, timeout=120)

    def _chat(self, system, messages, tools) -> Reply:
        request = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}] + [_to_openai(m) for m in messages],
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            request["tools"] = [{"type": "function", "function": {
                "name": t["name"], "description": t["description"], "parameters": t["parameters"]}} for t in tools]
        if self.extra_body:
            request["extra_body"] = self.extra_body
        response = self.client.chat.completions.create(**request)
        if not response.choices:
            # OpenRouter иногда отвечает 200 без ответа модели, а ошибку кладёт в тело.
            error = LLMError(f"пустой ответ: {getattr(response, 'model_extra', {}).get('error')}")
            error.status_code = 503
            raise error
        self.usage.requests += 1
        if response.usage:
            self.usage.input_tokens += response.usage.prompt_tokens or 0
            self.usage.output_tokens += response.usage.completion_tokens or 0
        message = response.choices[0].message
        calls = []
        for call in message.tool_calls or []:
            calls.append(ToolCall(call.id, call.function.name, _parse_args(call.function.arguments)))
        return Reply(message.content or "", calls)


class AnthropicLLM(LLM):
    def __init__(self, base_url: str, api_key: str, auth_scheme: str = "x-api-key", **kwargs):
        super().__init__(**kwargs)
        from anthropic import Anthropic
        auth = {"auth_token": api_key} if auth_scheme == "bearer" else {"api_key": api_key}
        self.client = Anthropic(base_url=base_url or None, max_retries=0, timeout=120, **auth)

    def _chat(self, system, messages, tools) -> Reply:
        request = {
            "model": self.model,
            "system": system,
            "messages": _to_anthropic(messages),
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if tools:
            request["tools"] = [{"name": t["name"], "description": t["description"],
                                 "input_schema": t["parameters"]} for t in tools]
        if self.extra_body:
            request["extra_body"] = self.extra_body
        response = self.client.messages.create(**request)
        self.usage.requests += 1
        self.usage.input_tokens += response.usage.input_tokens or 0
        self.usage.output_tokens += response.usage.output_tokens or 0
        text, calls = [], []
        for block in response.content:
            if block.type == "text":
                text.append(block.text)
            elif block.type == "tool_use":
                calls.append(ToolCall(block.id, block.name, dict(block.input or {})))
        return Reply("\n".join(text), calls)


def from_env() -> LLM:
    load_dotenv()
    provider = os.getenv("LLM_PROVIDER", "openai").strip().lower()
    api_key = os.getenv("LLM_API_KEY", "").strip()
    if not api_key:
        raise LLMError("Не задан LLM_API_KEY. Скопируйте .env.example в .env и впишите ключ.")
    common = dict(
        model=os.getenv("LLM_MODEL", "deepseek/deepseek-v4-flash"),
        temperature=float(os.getenv("LLM_TEMPERATURE", "0.3")),
        max_tokens=int(os.getenv("LLM_MAX_TOKENS", "2048")),
        rpm=int(os.getenv("LLM_RPM", "0") or 0),
        extra_body=json.loads(os.getenv("LLM_EXTRA_BODY", "") or "{}"),
    )
    base_url = os.getenv("LLM_BASE_URL", "").strip()
    if provider == "anthropic":
        return AnthropicLLM(base_url, api_key, os.getenv("LLM_AUTH_SCHEME", "x-api-key"), **common)
    if provider == "openai":
        return OpenAILLM(base_url or "https://openrouter.ai/api/v1", api_key, **common)
    raise LLMError(f"LLM_PROVIDER должен быть openai или anthropic, а не {provider!r}")


def _to_openai(m: dict) -> dict:
    if m["role"] == "assistant":
        out = {"role": "assistant", "content": m.get("content") or None}
        if m.get("tool_calls"):
            out["tool_calls"] = [{"id": c.id, "type": "function", "function": {
                "name": c.name, "arguments": json.dumps(c.args, ensure_ascii=False)}} for c in m["tool_calls"]]
        return out
    if m["role"] == "tool":
        return {"role": "tool", "tool_call_id": m["tool_call_id"], "content": m["content"]}
    return {"role": "user", "content": m["content"]}


def _to_anthropic(messages: list[dict]) -> list[dict]:
    """Anthropic требует чередования user/assistant, поэтому соседние блоки одной роли склеиваются."""
    out = []
    for m in messages:
        if m["role"] == "assistant":
            role, blocks = "assistant", []
            if m.get("content"):
                blocks.append({"type": "text", "text": m["content"]})
            for c in m.get("tool_calls") or []:
                blocks.append({"type": "tool_use", "id": c.id, "name": c.name, "input": c.args})
        elif m["role"] == "tool":
            role = "user"
            blocks = [{"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}]
        else:
            role, blocks = "user", [{"type": "text", "text": m["content"]}]
        if out and out[-1]["role"] == role:
            out[-1]["content"].extend(blocks)
        else:
            out.append({"role": role, "content": blocks})
    return out


def _parse_args(raw: str | None) -> dict:
    try:
        args = json.loads(raw or "{}")
    except json.JSONDecodeError:
        return {"_raw": raw}
    return args if isinstance(args, dict) else {"_raw": args}


def _is_network(error: Exception) -> bool:
    name = type(error).__name__
    return "Connection" in name or "Timeout" in name


def _retry_after(error: Exception) -> float | None:
    response = getattr(error, "response", None)
    value = getattr(response, "headers", {}).get("retry-after") if response is not None else None
    try:
        return float(value) if value else None
    except ValueError:
        return None
