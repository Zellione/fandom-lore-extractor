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
