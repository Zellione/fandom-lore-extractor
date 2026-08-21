from pathlib import Path

import pytest

from lore_extractor.parser import parse_wikitext

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def akame_wikitext() -> str:
    return (FIXTURES / "akame_wikitext.txt").read_text(encoding="utf-8")


@pytest.fixture
def murasame_wikitext() -> str:
    return (FIXTURES / "murasame_wikitext.txt").read_text(encoding="utf-8")


def test_parse_infoboxes(akame_wikitext):
    parsed = parse_wikitext(akame_wikitext, title="Akame")
    assert len(parsed.infoboxes) == 1
    ib = parsed.infoboxes[0]
    assert ib.name.strip() == "Infobox Character"
    assert ib.fields["age"] == "Teens"
    assert ib.fields["height"] == "164 cm (5'4\")"
    assert "Murasame" in ib.fields["teigu"]


def test_parse_sections_hierarchy(akame_wikitext):
    parsed = parse_wikitext(akame_wikitext, title="Akame")
    titles = [s.title for s in parsed.flat_sections()]
    assert "Appearance" in titles
    assert "Personality" in titles
    assert "History" in titles
    assert "Equipment" in titles


def test_parse_lead(akame_wikitext):
    parsed = parse_wikitext(akame_wikitext, title="Akame")
    assert "Akame of the Demon Sword Murasame" in parsed.lead
    assert "titular heroine" in parsed.lead


def test_parse_categories(akame_wikitext):
    parsed = parse_wikitext(akame_wikitext, title="Akame")
    assert "Characters" in parsed.categories
    assert "Female Character" in parsed.categories


def test_clean_text_removes_markup(akame_wikitext):
    parsed = parse_wikitext(akame_wikitext, title="Akame")
    appearance = next(s for s in parsed.flat_sections() if s.title == "Appearance")
    assert "[[" not in appearance.content
    assert "{{" not in appearance.content
    assert "Akame is an attractive young woman" in appearance.content


def test_section_links(akame_wikitext):
    parsed = parse_wikitext(akame_wikitext, title="Akame")
    equipment = next(s for s in parsed.flat_sections() if s.title == "Equipment")
    assert any("Murasame" in l for l in equipment.links)


def test_parse_item_infobox(murasame_wikitext):
    parsed = parse_wikitext(murasame_wikitext, title="Murasame")
    ib = parsed.infoboxes[0]
    assert "Teigu" in ib.name
    assert ib.fields["user"] == "Akame" or "Akame" in ib.fields["user"]
