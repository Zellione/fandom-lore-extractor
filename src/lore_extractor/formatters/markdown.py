"""Markdown output formatting.

Produces one human-readable Markdown document per entity with the infobox as a
table, prose sections, and a relationships section.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

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

# Map entity type -> ordered list of (attribute, heading).
PROSE_FIELDS: Dict[str, List[str]] = {
    "character": ["appearance", "personality", "history", "abilities", "trivia"],
    "location": ["geography", "history"],
    "item": ["description", "history", "abilities"],
    "organization": ["overview", "history"],
    "creature": ["biology", "behavior", "habitat", "abilities"],
    "lore": ["summary"],
}

# Map entity type -> ordered list of (attribute, heading) for relationships.
RELATIONSHIP_FIELDS: Dict[str, List[str]] = {
    "character": [
        "equipment", "weapons", "factions", "affiliations", "family",
        "allies", "enemies", "relationships", "associated_locations",
        "encountered_creatures",
    ],
    "location": ["inhabitants", "rulers", "notable_residents", "controlled_by", "headquarters_of", "related_lore"],
    "item": ["owners", "creators", "wielders", "affiliated_organizations"],
    "organization": ["members", "leaders", "founders", "allies", "enemies", "subgroups",
                     "territories", "headquarters", "items"],
    "creature": ["found_in", "preyed_on_by"],
    "lore": ["related_characters", "related_locations", "related_items",
             "related_organizations", "related_creatures"],
}


def _md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render_markdown(entity: EntityModel) -> str:
    etype = entity.entity_type
    lines: List[str] = []
    lines.append(f"# {entity.name}")
    lines.append("")
    if entity.aliases:
        lines.append(f"**Aliases:** {', '.join(entity.aliases)}")
        lines.append("")
    lines.append(f"*Type:* {etype}  ")
    if entity.source_url:
        lines.append(f"*Source:* {entity.source_url}  ")
    lines.append("")

    # Infobox table
    if entity.infobox:
        lines.append("## Infobox")
        lines.append("")
        lines.append("| Field | Value |")
        lines.append("|-------|-------|")
        for key, value in entity.infobox.items():
            lines.append(f"| {_md_escape(str(key))} | {_md_escape(str(value))} |")
        lines.append("")

    # Prose sections
    for field in PROSE_FIELDS.get(etype, []):
        value = getattr(entity, field, None)
        if isinstance(value, str) and value.strip():
            heading = field.replace("_", " ").title()
            lines.append(f"## {heading}")
            lines.append("")
            lines.append(value.strip())
            lines.append("")

    # Lore events
    if isinstance(entity, LoreEntry) and entity.events:
        lines.append("## Events")
        lines.append("")
        for ev in entity.events:
            lines.append(f"- {ev.strip()}")
        lines.append("")

    # Relationships
    rel_lines: List[str] = []
    for field in RELATIONSHIP_FIELDS.get(etype, []):
        value = getattr(entity, field, None)
        if isinstance(value, list) and value:
            heading = field.replace("_", " ").title()
            rel_lines.append(f"- **{heading}:** {', '.join(value)}")
    # Generic pages: free-form related buckets
    if isinstance(entity, GenericPage) and entity.related:
        for bucket, names in entity.related.items():
            rel_lines.append(f"- **{bucket.replace('related_', '').title()}:** {', '.join(names)}")
    if rel_lines:
        lines.append("## Relationships")
        lines.append("")
        lines.extend(rel_lines)
        lines.append("")

    # Categories
    if entity.categories:
        lines.append("## Categories")
        lines.append("")
        lines.append(", ".join(entity.categories))
        lines.append("")

    return "\n".join(lines)


def write_markdown_files(entities: List[EntityModel], output_dir: Path) -> None:
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for ent in entities:
        safe = _safe_filename(ent.name)
        (pages_dir / f"{safe}.md").write_text(
            render_markdown(ent) + "\n", encoding="utf-8"
        )


def _safe_filename(name: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip() or "page"
