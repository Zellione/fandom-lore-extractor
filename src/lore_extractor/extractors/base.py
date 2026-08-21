"""Base extractor interface and shared helpers."""
from __future__ import annotations

from typing import Any, Dict, Optional

from lore_extractor.models import EntityModel
from lore_extractor.parser import Infobox, ParsedPage, Section

# Map normalized section titles to field names by entity type.
SECTION_ALIASES = {
    "appearance": "appearance",
    "personality": "personality",
    "history": "history",
    "background": "history",
    "biography": "history",
    "abilities": "abilities",
    "powers": "abilities",
    "skills": "abilities",
    "equipment": "equipment",
    "trivia": "trivia",
}


def first_section(parsed: ParsedPage, *titles: str) -> Optional[Section]:
    """Return the first section matching any of the given titles."""
    wanted = {t.strip().lower() for t in titles}
    for s in parsed.flat_sections():
        if s.title.lower() in wanted:
            return s
    return None


def section_text(parsed: ParsedPage, *titles: str) -> Optional[str]:
    sec = first_section(parsed, *titles)
    if sec is None:
        return None
    text = (sec.content + "\n" + "\n".join(ch.content for ch in sec.subsections)).strip()
    return text or None


def main_infobox(parsed: ParsedPage) -> Optional[Infobox]:
    """Return the first reasonably-sized infobox (most specific match)."""
    for ib in parsed.infoboxes:
        name = ib.name.strip().lower()
        if name == "infobox":
            continue
        return ib
    return None


def clean_infobox_value(value: str) -> str:
    """Remove markdown-adjacent wiki markup artifacts from an infobox value."""
    import re

    from lore_extractor.parser import _clean_fragment

    # Preserve line-break separators as a readable delimiter.
    value = re.sub(r"<br\s*/?>", "; ", value, flags=re.IGNORECASE)
    cleaned = _clean_fragment(value)
    cleaned = re.sub(r"\s*;\s*", "; ", cleaned)
    return cleaned


def normalize_categories(parsed: ParsedPage) -> list:
    return list(parsed.categories)


class BaseExtractor:
    """Base class; subclasses map parsed sections/categories to model fields."""

    def extract(self, parsed: ParsedPage, title: str, classification: Any) -> EntityModel:
        raise NotImplementedError
