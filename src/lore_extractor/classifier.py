"""Entity type classification.

Determines the entity type (character, location, item, organization, creature,
lore, or generic) of a parsed page based on infobox template names and category
membership, using a most-specific-signal-wins, confidence-based approach.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from lore_extractor.models import EntityTypeName
from lore_extractor.parser import ParsedPage

# Map infobox template sub-name keyword -> entity type, with a confidence score.
# Exact infobox template match takes priority, then category match.
INFOBOX_RULES: List[Tuple[str, EntityTypeName, float]] = [
    ("character", "character", 0.95),
    ("person", "character", 0.9),
    ("human", "character", 0.85),
    ("location", "location", 0.95),
    ("place", "location", 0.9),
    ("area", "location", 0.85),
    ("country", "location", 0.9),
    ("city", "location", 0.9),
    ("region", "location", 0.85),
    ("planet", "location", 0.9),
    ("item", "item", 0.9),
    ("weapon", "item", 0.95),
    ("object", "item", 0.85),
    ("teigu", "item", 0.95),
    ("artifact", "item", 0.9),
    ("tool", "item", 0.85),
    ("organization", "organization", 0.95),
    ("faction", "organization", 0.9),
    ("group", "organization", 0.85),
    ("army", "organization", 0.85),
    ("creature", "creature", 0.95),
    ("beast", "creature", 0.9),
    ("animal", "creature", 0.9),
    ("monster", "creature", 0.9),
    ("species", "creature", 0.9),
    ("dragon", "creature", 0.9),
]

# Category keyword -> entity type + confidence (weaker than infobox).
CATEGORY_RULES: List[Tuple[str, EntityTypeName, float]] = [
    ("character", "character", 0.6),
    ("people", "character", 0.6),
    ("person", "character", 0.55),
    ("location", "location", 0.6),
    ("place", "location", 0.6),
    ("city", "location", 0.55),
    ("country", "location", 0.55),
    ("item", "item", 0.55),
    ("weapon", "item", 0.6),
    ("artifact", "item", 0.55),
    ("teigu", "item", 0.6),
    ("organization", "organization", 0.6),
    ("faction", "organization", 0.6),
    ("group", "organization", 0.55),
    ("creature", "creature", 0.6),
    ("beast", "creature", 0.6),
    ("animal", "creature", 0.55),
    ("monster", "creature", 0.55),
    ("dragon", "creature", 0.55),
]


@dataclass
class Classification:
    entity_type: EntityTypeName
    confidence: float
    source: str  # 'infobox:<name>' or 'category:<name>' or 'lore_default'/'generic'
    matched: Optional[str]  # the input signal that matched


def _best_signal(
    text: str, rules
) -> Optional[Tuple[str, EntityTypeName, float]]:
    lowered = text.lower()
    best: Optional[Tuple[str, EntityTypeName, float]] = None
    for keyword, etype, conf in rules:
        if keyword in lowered:
            if best is None or conf > best[2]:
                best = (keyword, etype, conf)
    return best


def classify_page(parsed: ParsedPage) -> Classification:
    """Classify a parsed page into an entity type with confidence."""
    # 1. Infobox signals (most specific, highest confidence).
    infobox_name: Optional[str] = None
    for infobox in parsed.infoboxes:
        name = infobox.name.strip()
        if name.lower() == "infobox" or not name.lower().startswith("infobox"):
            continue
        stripped = name[len("infobox"):].strip()
        if not stripped:
            continue
        if " " in stripped and len(stripped) > 40:
            continue
        infobox_name = name
        match = _best_signal(stripped, INFOBOX_RULES)
        if match:
            keyword, etype, conf = match
            return Classification(etype, conf, f"infobox:{name}", keyword)
    # If we found an infobox but no keyword match, keep note for generic fallback.

    # 2. Category signals.
    category_hit: Optional[Tuple[str, EntityTypeName, float]] = None
    matched_cat: Optional[str] = None
    for cat in parsed.categories:
        m = _best_signal(cat, CATEGORY_RULES)
        if m and (category_hit is None or m[2] > category_hit[2]):
            category_hit = m
            matched_cat = cat
    if category_hit:
        keyword, etype, conf = category_hit
        return Classification(etype, conf, f"category:{matched_cat}", keyword)

    # 3. Lore heuristic: narrative-section pages without an entity infobox.
    lore_titles = {
        "plot", "story", "synopsis", "events", "history",
        "war", "battle", "conflict", "timeline", "arc",
    }
    section_titles = {s.title.lower() for s in parsed.flat_sections()}
    if not parsed.infoboxes and section_titles:
        has_lore = bool(section_titles & lore_titles)
        if has_lore and len(parsed.infoboxes) == 0:
            return Classification("lore", 0.5, "lore_default", None)

    # 4. Generic fallback.
    return Classification("generic", 0.2, "generic", None)
