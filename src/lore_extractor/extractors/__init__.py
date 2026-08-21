"""Entity extractors: turn a parsed page + classification into a typed model.

The extractors populate prose sections and raw links. Typed relationships
(equipment, members, faction, etc.) are populated later by the inference engine.
"""
from __future__ import annotations

from typing import Any, Dict, Optional

from lore_extractor.extractors.base import (
    clean_infobox_value,
    main_infobox,
    section_text,
)
from lore_extractor.models import (
    Character,
    Creature,
    EntityModel,
    GenericPage,
    Item,
    Location,
    LoreEntry,
    Organization,
)
from lore_extractor.parser import ParsedPage


def _build_base(
    parsed: ParsedPage,
    title: str,
    classification,
    source_url: str,
    raw_links: list,
) -> Dict[str, Any]:
    alts: list = []
    if parsed.lead:
        # Use lead as a summary-ish alias can be too noisy; keep aliases empty.
        pass
    fields: Dict[str, Any] = {
        "name": title,
        "title": title,
        "aliases": alts,
        "infobox": {},
        "categories": list(parsed.categories),
        "source_url": source_url,
        "raw_links": list(raw_links),
        "section_links": {
            s.title: list(s.links) for s in parsed.flat_sections() if s.links
        },
        "sections": {s.title: s.content for s in parsed.flat_sections() if s.content.strip()},
        "confidence": classification.confidence,
    }
    ib = main_infobox(parsed)
    if ib is not None:
        for key, value in ib.fields.items():
            fields["infobox"][key] = clean_infobox_value(value)
    return fields


def extract_character(
    parsed: ParsedPage, title: str, classification, source_url: str, raw_links: list
) -> Character:
    f = _build_base(parsed, title, classification, source_url, raw_links)
    f["appearance"] = section_text(parsed, "Appearance")
    f["personality"] = section_text(parsed, "Personality", "Character")
    f["history"] = section_text(parsed, "History", "Biography", "Background")
    f["abilities"] = section_text(parsed, "Abilities", "Powers", "Skills", "Equipment and Skills")
    f["trivia"] = section_text(parsed, "Trivia")
    return Character(**f)


def extract_location(
    parsed: ParsedPage, title: str, classification, source_url: str, raw_links: list
) -> Location:
    f = _build_base(parsed, title, classification, source_url, raw_links)
    f["geography"] = section_text(parsed, "Geography", "Layout", "Description")
    f["history"] = section_text(parsed, "History", "Background")
    return Location(**f)


def extract_item(
    parsed: ParsedPage, title: str, classification, source_url: str, raw_links: list
) -> Item:
    f = _build_base(parsed, title, classification, source_url, raw_links)
    f["description"] = section_text(parsed, "Description", "Overview")
    f["history"] = section_text(parsed, "History", "Background")
    f["abilities"] = section_text(parsed, "Abilities", "Powers", "Powers and Abilities", "Effects")
    return Item(**f)


def extract_organization(
    parsed: ParsedPage, title: str, classification, source_url: str, raw_links: list
) -> Organization:
    f = _build_base(parsed, title, classification, source_url, raw_links)
    f["overview"] = section_text(parsed, "Overview", "Summary", "About")
    f["history"] = section_text(parsed, "History", "Background", "Early History")
    return Organization(**f)


def extract_creature(
    parsed: ParsedPage, title: str, classification, source_url: str, raw_links: list
) -> Creature:
    f = _build_base(parsed, title, classification, source_url, raw_links)
    f["biology"] = section_text(parsed, "Biology", "Physiology", "Appearance", "Description")
    f["behavior"] = section_text(parsed, "Behavior", "Personality", "Behaviour")
    f["habitat"] = section_text(parsed, "Habitat", "Distribution")
    f["abilities"] = section_text(parsed, "Abilities", "Powers", "Skills")
    return Creature(**f)


def extract_lore(
    parsed: ParsedPage, title: str, classification, source_url: str, raw_links: list
) -> LoreEntry:
    f = _build_base(parsed, title, classification, source_url, raw_links)
    f["summary"] = parsed.lead or section_text(parsed, "Summary", "Overview", "Plot", "Synopsis")
    # Events from narrative sections.
    for title_key in ("Events", "Timeline", "Plot", "Story", "History"):
        events = []
        for title_tok in parsed.flat_sections():
            if title_tok.title.lower().startswith(title_key.lower()):
                if title_tok.content.strip():
                    events.append(title_tok.content)
        if events:
            f["events"] = events
            break
    return LoreEntry(**f)


def extract_generic(
    parsed: ParsedPage, title: str, classification, source_url: str, raw_links: list
) -> GenericPage:
    f = _build_base(parsed, title, classification, source_url, raw_links)
    f["content"] = parsed.lead or next(
        (s.content for s in parsed.flat_sections() if s.content.strip()), None
    )
    return GenericPage(**f)


EXTRACTORS = {
    "character": extract_character,
    "location": extract_location,
    "item": extract_item,
    "organization": extract_organization,
    "creature": extract_creature,
    "lore": extract_lore,
    "generic": extract_generic,
}


def extract_entity(
    parsed: ParsedPage,
    title: str,
    classification,
    source_url: str,
    raw_links: Optional[list] = None,
) -> EntityModel:
    fn = EXTRACTORS.get(classification.entity_type, extract_generic)
    return fn(parsed, title, classification, source_url, raw_links or [])
