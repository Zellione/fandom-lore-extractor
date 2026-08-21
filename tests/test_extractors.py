from pathlib import Path

from lore_extractor.classifier import classify_page
from lore_extractor.extractors import extract_entity
from lore_extractor.models import Character, Item
from lore_extractor.parser import parse_wikitext

FIXTURES = Path(__file__).parent / "fixtures"


def _extract(filename, title, links=None):
    text = (FIXTURES / filename).read_text(encoding="utf-8")
    parsed = parse_wikitext(text, title=title)
    cl = classify_page(parsed)
    return extract_entity(parsed, title, cl, f"https://wiki/{title}", links or [])


def test_extract_character():
    ent = _extract("akame_wikitext.txt", "Akame")
    assert isinstance(ent, Character)
    assert ent.entity_type == "character"
    assert ent.name == "Akame"
    assert "Appearance" in ent.sections
    assert "Murasame" in ent.infobox.get("teigu", "")
    assert "Night Raid" in ent.infobox.get("faction", "")
    assert ent.appearance and "Akame is an attractive" in ent.appearance
    assert ent.personality and "serious and cold-hearted" in ent.personality
    assert ent.history and "sold her" in ent.history


def test_extract_character_sets_raw_links():
    ent = _extract("akame_wikitext.txt", "Akame", links=["Murasame", "Kurome", "Night Raid"])
    assert ent.raw_links == ["Murasame", "Kurome", "Night Raid"]
    assert "Equipment" in ent.section_links


def test_extract_item():
    ent = _extract("murasame_wikitext.txt", "Murasame")
    assert isinstance(ent, Item)
    assert ent.entity_type == "item"
    assert ent.name == "Murasame"
    assert ent.infobox.get("title") == "One-Cut Killer"
    assert "Akame" in ent.infobox.get("user", "")
    assert ent.description and "curse" in ent.description
    assert ent.history and "Night Raid" in ent.history


def test_extract_character_includes_categories():
    ent = _extract("akame_wikitext.txt", "Akame")
    assert "Characters" in ent.categories
    assert "Teigu User" in ent.categories


def test_to_dict_keep_links_exclusion():
    ent = _extract("akame_wikitext.txt", "Akame", links=["Murasame"])
    assert "raw_links" not in ent.to_dict(keep_links=False)
    assert "raw_links" in ent.to_dict(keep_links=True)
