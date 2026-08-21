import json
from io import StringIO
from types import SimpleNamespace

import click
import pytest

from lore_extractor.inference import DecisionLog, InferenceResult, run_inference
from lore_extractor.llm_resolver import (
    LLMResolver,
    _extract_json,
    build_client,
    resolve_model,
)
from lore_extractor.models import Character


class _Completions:
    def __init__(self, client):
        self._client = client

    def create(self, **kwargs):
        return self._client._create(kwargs)


class _Models:
    def __init__(self, client):
        self._client = client

    def list(self, **kwargs):
        return [SimpleNamespace(id=mid) for mid in self._client.model_ids]


class FakeClient:
    """Minimal stand-in for the OpenAI SDK client."""

    def __init__(self, *contents, model_ids=None):
        self.contents = list(contents)
        self.model_ids = list(model_ids or [])
        self.create_calls = []
        self.models = _Models(self)
        self.completions = _Completions(self)

    @property
    def chat(self):
        return self

    def list(self, **kwargs):  # noqa: D401
        return []

    def _create(self, kwargs):
        self.create_calls.append(kwargs)
        if not self.contents:
            raise AssertionError("No mocked responses left")
        item = self.contents.pop(0)
        if isinstance(item, Exception):
            raise item
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=item))]
        )


def _build_log(links=None):
    links = links if links is not None else ["Wave", "Mine"]
    a = Character(name="Akame", raw_links=links, confidence=0.9)
    w1 = Character(name="Wave", confidence=0.9)
    w2 = Character(name="Wave (Technique)", confidence=0.5)
    m1 = Character(name="Mine", confidence=0.8)
    m2 = Character(name="Mine (Technique)", confidence=0.4)
    log = DecisionLog()
    run_inference([a, w1, w2, m1, m2], log, InferenceResult())
    return log


def _resolver(log, client, **kwargs):
    stdout = StringIO()
    resolver = LLMResolver(
        log,
        client=client,
        model="test-model",
        stdout=stdout,
        **kwargs,
    )
    return resolver, stdout


def test_extract_json_strips_code_fences():
    raw = '```json\n{"0": {"chosen": "Wave"}}\n```'
    assert _extract_json(raw) == {"0": {"chosen": "Wave"}}
    with pytest.raises(Exception):
        _extract_json("[1, 2]")


def test_resolve_model_explicit_name_wins():
    assert resolve_model(FakeClient(), "my-model") == "my-model"


def test_resolve_model_auto_selects_single_model():
    client = FakeClient(model_ids=["mistral-7b"])
    assert resolve_model(client, None) == "mistral-7b"


def test_resolve_model_multiple_requires_flag():
    client = FakeClient(model_ids=["a", "b", "c"])
    with pytest.raises(click.UsageError) as excinfo:
        resolve_model(client, None)
    assert "--llm-model" in str(excinfo.value)
    assert "a" in str(excinfo.value)
    assert "b" in str(excinfo.value)
    assert "c" in str(excinfo.value)


def test_resolve_model_list_fails_requires_flag():
    client = FakeClient()

    class Boom:
        def list(self, **kwargs):
            raise RuntimeError("endpoint error")

    setattr(client, "models", Boom())
    with pytest.raises(click.UsageError) as excinfo:
        resolve_model(client, None)
    assert "--llm-model" in str(excinfo.value)


def test_resolve_model_empty_requires_flag():
    client = FakeClient(model_ids=[])
    with pytest.raises(click.UsageError) as excinfo:
        resolve_model(client, None)
    assert "--llm-model" in str(excinfo.value)


def test_batched_resolution_applies_to_log(tmp_path):
    log = _build_log()
    payload = json.dumps({
        "0": {"chosen": "Wave", "reasoning": "Main protagonist"},
        "1": {"chosen": "Mine (Technique)", "reasoning": "Refers to the technique"},
    })
    resolver, stdout = _resolver(log, FakeClient(payload))
    assert resolver.run() == 2
    out = stdout.getvalue()
    assert "Wave" in out
    assert "Main protagonist" in out
    texts = {e["link_text"]: e["resolution"] for e in log.entries}
    assert texts == {"Wave": "Wave", "Mine": "Mine (Technique)"}
    assert log.unresolved_entries() == []


def test_single_prompt_mode():
    log = _build_log()
    client = FakeClient(
        '{"chosen": "Wave", "reasoning": "First pick"}',
        '{"chosen": "Mine", "reasoning": "Second pick"}',
    )
    resolver, stdout = _resolver(log, client, single_prompt=True)
    assert resolver.run() == 2
    texts = {e["link_text"]: e["resolution"] for e in log.entries}
    assert texts == {"Wave": "Wave", "Mine": "Mine"}


def test_single_prompt_uses_one_call_per_entry():
    log = _build_log()
    client = FakeClient(
        '{"chosen": "Wave", "reasoning": "one"}',
        '{"chosen": "Mine", "reasoning": "two"}',
    )
    resolver, _ = _resolver(log, client, single_prompt=True)
    resolver.run()
    assert len(client.create_calls) == 2
    for kwargs in client.create_calls:
        assert kwargs["model"] == "test-model"
        assert kwargs["temperature"] == 0.0


def test_batched_uses_single_call():
    log = _build_log()
    client = FakeClient(
        '{"0": {"chosen": "Wave", "reasoning": "a"}, '
        '"1": {"chosen": "Mine", "reasoning": "b"}}'
    )
    resolver, _ = _resolver(log, client)
    resolver.run()
    assert len(client.create_calls) == 1


def test_invalid_candidate_retries_then_succeeds():
    log = _build_log(links=["Wave"])
    client = FakeClient(
        '{"0": {"chosen": "Not A Candidate", "reasoning": "wrong"}}',
        '{"0": {"chosen": "Wave", "reasoning": "fixed"}}',
    )
    resolver, _ = _resolver(log, client)
    assert resolver.run() == 1
    assert log.entries[0]["resolution"] == "Wave"
    assert len(client.create_calls) == 2


def test_failure_after_max_attempts_logs_error(tmp_path):
    log = _build_log(links=["Wave"])
    client = FakeClient(
        '{"0": {"chosen": "Nope", "reasoning": "bad"}}',
        '{"0": {"chosen": "Nope", "reasoning": "bad"}}',
        '{"0": {"chosen": "Nope", "reasoning": "bad"}}',
    )
    resolver, stdout = _resolver(log, client)
    assert resolver.run() == 0
    assert len(log.unresolved_entries()) == 1
    assert "failed" in stdout.getvalue()
    assert len(resolver.reasoning_records) == 1
    record = resolver.reasoning_records[0]
    assert record["link_text"] == "Wave"
    assert "error" in record


def test_api_error_retries_then_logs_error():
    log = _build_log(links=["Wave"])
    client = FakeClient(
        RuntimeError("connection refused"),
        RuntimeError("connection refused"),
        RuntimeError("connection refused"),
    )
    resolver, _ = _resolver(log, client)
    assert resolver.run() == 0
    assert len(resolver.reasoning_records) == 1
    assert "error" in resolver.reasoning_records[0]


def test_batched_unexpected_shape_retries():
    log = _build_log(links=["Wave"])
    client = FakeClient(
        "not json at all",
        '[1, 2, 3]',
        '{"0": {"chosen": "Wave", "reasoning": "ok"}}',
    )
    resolver, _ = _resolver(log, client)
    assert resolver.run() == 1
    assert log.entries[0]["resolution"] == "Wave"


def test_write_reasoning(tmp_path):
    log = _build_log(links=["Wave"])
    client = FakeClient(
        '{"0": {"chosen": "Wave", "reasoning": "clearest character"}}'
    )
    resolver, _ = _resolver(log, client)
    resolver.run()
    path = tmp_path / "decisions" / "llm_reasoning.json"
    resolver.write_reasoning(path)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["chosen"] == "Wave"
    assert data[0]["reasoning"] == "clearest character"
    assert "key" in data[0]
    assert "resolved_at" in data[0]


def test_no_unresolved_entries():
    log = DecisionLog()
    resolver, stdout = _resolver(log, FakeClient())
    assert resolver.run() == 0
    assert "No unresolved decisions" in stdout.getvalue()


def test_build_client_passes_through(monkeypatch):
    captured = {}

    class FakeSDKClient:
        def __init__(self, base_url=None, api_key=None):
            captured["base_url"] = base_url
            captured["api_key"] = api_key

    monkeypatch.setattr("openai.OpenAI", FakeSDKClient)
    build_client(base_url="http://local:11434/v1", api_key="sk-test")
    assert captured == {"base_url": "http://local:11434/v1", "api_key": "sk-test"}


def test_build_client_local_server_injects_dummy_key(monkeypatch):
    captured = {}

    class FakeSDKClient:
        def __init__(self, base_url=None, api_key=None):
            captured["base_url"] = base_url
            captured["api_key"] = api_key

    monkeypatch.setattr("openai.OpenAI", FakeSDKClient)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    build_client(base_url="http://localhost:1234/v1", api_key=None)
    assert captured == {"base_url": "http://localhost:1234/v1", "api_key": "NO-KEY-PROVIDED"}


def test_build_client_openai_no_key_does_not_inject(monkeypatch):
    captured = {}

    class FakeSDKClient:
        def __init__(self, base_url=None, api_key=None):
            captured["base_url"] = base_url
            captured["api_key"] = api_key

    monkeypatch.setattr("openai.OpenAI", FakeSDKClient)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    build_client(base_url=None, api_key=None)
    assert captured == {"base_url": None, "api_key": None}


def test_build_client_env_key_not_overridden(monkeypatch):
    captured = {}

    class FakeSDKClient:
        def __init__(self, base_url=None, api_key=None):
            captured["base_url"] = base_url
            captured["api_key"] = api_key

    monkeypatch.setattr("openai.OpenAI", FakeSDKClient)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-env")
    build_client(base_url="http://localhost:1234/v1", api_key=None)
    assert captured == {"base_url": "http://localhost:1234/v1", "api_key": None}