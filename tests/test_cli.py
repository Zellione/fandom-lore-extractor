from types import SimpleNamespace

from click.testing import CliRunner

from lore_extractor.cli import main
from lore_extractor.inference import DecisionLog


def _make_decisions(path):
    log = DecisionLog()
    log.add(
        "Akame",
        "Wave",
        [
            {"name": "Wave", "type": "character", "confidence": 0.9},
            {"name": "Wave (Technique)", "type": "character", "confidence": 0.5},
        ],
    )
    log.write(path)
    return path


def test_resolve_subcommand_pick(tmp_path):
    p = _make_decisions(tmp_path / "ambiguous_links.json")
    runner = CliRunner()
    result = runner.invoke(main, ["resolve", "--decisions", str(p)], input="1\n")
    assert result.exit_code == 0, result.output
    log = DecisionLog(decisions_path=p)
    assert log.entries[0]["resolved"] is True
    assert log.entries[0]["resolution"] == "Wave"


def test_resolve_subcommand_auto(tmp_path):
    p = _make_decisions(tmp_path / "ambiguous_links.json")
    runner = CliRunner()
    result = runner.invoke(main, ["resolve", "--decisions", str(p)], input="a\n")
    assert result.exit_code == 0, result.output
    log = DecisionLog(decisions_path=p)
    assert log.entries[0]["resolution"] == "Wave"


def test_resolve_subcommand_locates_default_path(tmp_path):
    p = _make_decisions(tmp_path / "akamegakill.fandom.com" / "decisions" / "ambiguous_links.json")
    runner = CliRunner()
    result = runner.invoke(
        main,
        ["resolve", "--output", str(tmp_path), "--wiki", "akamegakill.fandom.com"],
        input="a\n",
    )
    assert result.exit_code == 0, result.output
    log = DecisionLog(decisions_path=p)
    assert log.entries[0]["resolved"] is True


def test_resolve_subcommand_missing_file(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["resolve", "--decisions", str(tmp_path / "nope.json")])
    assert result.exit_code != 0
    assert "not found" in result.output


def test_extract_requires_wiki(tmp_path):
    runner = CliRunner()
    result = runner.invoke(main, ["--entrypoint", "Akame"])
    assert result.exit_code != 0
    assert "--wiki is required" in result.output


class _FakeCompletions:
    def __init__(self, content):
        self.content = content

    def create(self, **kwargs):
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(
            completions=_FakeCompletions('{"0": {"chosen": "Wave", "reasoning": "best fit"}}')
        )


def _monkeypatch_llm(monkeypatch):
    monkeypatch.setattr(
        "lore_extractor.cli.build_client",
        lambda base_url=None, api_key=None: _FakeClient(),
    )
    monkeypatch.setattr(
        "lore_extractor.cli.resolve_model",
        lambda client, model: "test-model",
    )


def test_resolve_subcommand_with_llm(tmp_path, monkeypatch):
    p = _make_decisions(tmp_path / "akamegakill.fandom.com" / "decisions" / "ambiguous_links.json")
    _monkeypatch_llm(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "resolve",
            "--output", str(tmp_path),
            "--wiki", "akamegakill.fandom.com",
            "--use-llm",
            "--llm-url", "http://local:11434/v1",
            "--llm-key", "sk-test",
            "--llm-model", "test-model",
            "--llm-temperature", "0.2",
        ],
    )
    assert result.exit_code == 0, result.output
    log = DecisionLog(decisions_path=p)
    assert log.entries[0]["resolved"] is True
    assert log.entries[0]["resolution"] == "Wave"
    assert "LLM reasoning log" in result.output


def test_llm_resolve_writes_reasoning_file(tmp_path, monkeypatch):
    p = _make_decisions(tmp_path / "akamegakill.fandom.com" / "decisions" / "ambiguous_links.json")
    _monkeypatch_llm(monkeypatch)
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "resolve",
            "--output", str(tmp_path),
            "--wiki", "akamegakill.fandom.com",
            "--use-llm",
            "--llm-model", "test-model",
        ],
    )
    assert result.exit_code == 0, result.output
    reasoning = tmp_path / "akamegakill.fandom.com" / "decisions" / "llm_reasoning.json"
    assert reasoning.exists()
    import json as _json

    data = _json.loads(reasoning.read_text(encoding="utf-8"))
    assert len(data) == 1
    assert data[0]["chosen"] == "Wave"
    assert data[0]["reasoning"] == "best fit"


def test_resolve_subcommand_without_llm_uses_interactive(tmp_path):
    p = _make_decisions(tmp_path / "ambiguous_links.json")
    runner = CliRunner()
    result = runner.invoke(main, ["resolve", "--decisions", str(p)], input="a\n")
    assert result.exit_code == 0, result.output
    log = DecisionLog(decisions_path=p)
    assert log.entries[0]["resolution"] == "Wave"


def test_main_help_lists_llm_flags():
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    for flag in ("--use-llm", "--llm-url", "--llm-model", "--llm-key",
                 "--llm-single-prompt", "--llm-temperature"):
        assert flag in result.output
