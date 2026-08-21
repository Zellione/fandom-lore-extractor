from pathlib import Path

from lore_extractor.classifier import classify_page
from lore_extractor.parser import parse_wikitext

FIXTURES = Path(__file__).parent / "fixtures"

WIKITEXT_WITH_CATEGORY = """
{{Infobox Location
|name = Capital
|type = City
}}
'''The Capital''' is the seat of [[the Emperor]].
[[Category:Locations]]
"""

WIKITEXT_PLOT_ONLY = """
'''Chapter 1''' recounts the events of the revolution.
==Plot==
Tatsumi arrives in the capital.
==History==
The revolution began.
"""

WIKITEXT_NO_INFOBotemplate_NO_CATEGORY = """
'''Some page''' with only prose and no signals.
==Overview==
Just some content here.
"""


def _classify(text, title="Page"):
    parsed = parse_wikitext(text, title=title)
    return classify_page(parsed)


def test_character_by_infobox():
    parsed = parse_wikitext(
        (FIXTURES / "akame_wikitext.txt").read_text(encoding="utf-8"), title="Akame"
    )
    cl = classify_page(parsed)
    assert cl.entity_type == "character"
    assert cl.confidence == 0.95
    assert cl.source.startswith("infobox:")


def test_item_by_infobox():
    parsed = parse_wikitext(
        (FIXTURES / "murasame_wikitext.txt").read_text(encoding="utf-8"), title="Murasame"
    )
    cl = classify_page(parsed)
    assert cl.entity_type == "item"
    assert cl.confidence == 0.95


def test_location_with_infobox():
    cl = _classify(WIKITEXT_WITH_CATEGORY, "Capital")
    # The Infobox Location signal (conf 0.95) wins over the category signal.
    assert cl.entity_type == "location"
    assert cl.confidence == 0.95
    assert cl.source.startswith("infobox:")


def test_location_by_category_only():
    text = """
'''The Capital''' is a city.
[[Category:Locations]]
"""
    cl = _classify(text, "Capital")
    assert cl.entity_type == "location"
    assert cl.source.startswith("category:")


def test_lore_by_plot_sections():
    cl = _classify(WIKITEXT_PLOT_ONLY, "Chapter 1")
    assert cl.entity_type == "lore"


def test_generic_fallback():
    cl = _classify(WIKITEXT_NO_INFOBotemplate_NO_CATEGORY, "Some page")
    assert cl.entity_type == "generic"


def test_infobox_beats_category():
    # Character infobox should win over a generic category with no signal.
    text = """
{{Infobox Character
|name = Akame
}}
[[Category:Locations]]
"""
    cl = _classify(text, "Akame")
    assert cl.entity_type == "character"
