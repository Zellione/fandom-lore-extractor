"""Relationship inference engine.

After all entities are extracted and classified, this pass resolves each
entity's internal links against an entity index and populates its typed
relationship fields. Ambiguous links (matching more than one entity) are
recorded in a decision file rather than force-resolved.

Bidirectional relationships are created where meaningful (e.g. an item listed
as a character's ``equipment`` also gets that character added to its ``owners``).
"""
from __future__ import annotations

import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from lore_extractor.models import EntityModel, GenericPage

# ---------------------------------------------------------------------------
# Name normalization
# ---------------------------------------------------------------------------


def normalize_name(name: str) -> str:
    """Lowercase, strip accents/spacing/parenthetical disambiguators for matching."""
    text = unicodedata.normalize("NFKD", name)
    text = text.encode("ascii", "ignore").decode("ascii")
    text = re.sub(r"\s*\([^)]*\)\s*$", "", text)  # strip trailing "(...)"
    text = re.sub(r"[\s_]+", "", text).lower()
    return text


def name_variants(title: str) -> List[str]:
    """Return normalized keys under which a page title should be indexed."""
    variants = {normalize_name(title)}
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", title).strip()
    if stripped != title:
        variants.add(normalize_name(stripped))
    return list(variants)


# ---------------------------------------------------------------------------
# Inference rules
# ---------------------------------------------------------------------------
# (source_type, target_type) -> field name on source entity (character field)
DEFAULT_RULES: Dict[Tuple[str, str], str] = {
    ("character", "character"): "relationships",
    ("character", "item"): "equipment",
    ("character", "organization"): "factions",
    ("character", "creature"): "encountered_creatures",
    ("character", "location"): "associated_locations",
    ("location", "character"): "inhabitants",
    ("location", "organization"): "controlled_by",
    ("location", "lore"): "related_lore",
    ("item", "character"): "owners",
    ("item", "organization"): "affiliated_organizations",
    ("organization", "character"): "members",
    ("organization", "organization"): "allies",
    ("organization", "location"): "headquarters",
    ("organization", "item"): "items",
    ("creature", "location"): "found_in",
    ("creature", "character"): "preyed_on_by",
}

# Section-title keyword -> (source always) overridden field, applying only when
# the target type is compatible. Maps section keyword to (field, target_types).
SECTION_CONTEXT_RULES: Dict[str, Tuple[str, Tuple[str, ...]]] = {
    "equipment": ("equipment", ("item",)),
    "weapons": ("weapons", ("item",)),
    "family": ("family", ("character",)),
    "allies": ("allies", ("character", "organization")),
    "enemies": ("enemies", ("character", "organization")),
    "members": ("members", ("character",)),
    "leaders": ("leaders", ("character",)),
    "founders": ("founders", ("character",)),
    "inhabitants": ("inhabitants", ("character",)),
    "rulers": ("rulers", ("character",)),
    "owners": ("owners", ("character",)),
    "creators": ("creators", ("character",)),
    "subgroups": ("subgroups", ("organization",)),
    "allies2": ("allies", ("organization",)),
}


def _section_field(section_title: str, target_type: str) -> Optional[str]:
    key = section_title.strip().lower()
    for keyword, (field, target_types) in SECTION_CONTEXT_RULES.items():
        if keyword in key and target_type in target_types:
            return field
    return None


# Compatibility helper: reverse the relationship back onto the target.
# (target_type, target_field) -> (source_is, field_on_target)
REVERSE_RULES: Dict[Tuple[str, str], Tuple[str, str]] = {
    # character -- item
    ("character", "equipment"): ("item", "owners"),
    ("character", "weapons"): ("item", "wielders"),
    # character -- organization
    ("character", "factions"): ("organization", "members"),
    ("character", "affiliations"): ("organization", "members"),
    # character -- character
    ("character", "allies"): ("character", "allies"),
    ("character", "enemies"): ("character", "enemies"),
    ("character", "relationships"): ("character", "relationships"),
    ("character", "family"): ("character", "family"),
    # character -- location
    ("character", "associated_locations"): ("location", "inhabitants"),
    # character -- creature
    ("character", "encountered_creatures"): ("creature", "found_in"),
    # location -- character
    ("location", "inhabitants"): ("character", "associated_locations"),
    ("location", "rulers"): ("character", "associated_locations"),
    # location -- organization
    ("location", "controlled_by"): ("organization", "territories"),
    ("location", "headquarters_of"): ("organization", "headquarters"),
    # item -- character
    ("item", "owners"): ("character", "equipment"),
    ("item", "wielders"): ("character", "weapons"),
    ("item", "creators"): ("character", "relationships"),
    # item -- organization
    ("item", "affiliated_organizations"): ("organization", "items"),
    # organization -- character
    ("organization", "members"): ("character", "factions"),
    ("organization", "leaders"): ("character", "factions"),
    ("organization", "founders"): ("character", "factions"),
    # organization -- organization
    ("organization", "allies"): ("organization", "allies"),
    ("organization", "enemies"): ("organization", "enemies"),
    ("organization", "subgroups"): ("organization", "allies"),
    # organization -- location
    ("organization", "headquarters"): ("location", "headquarters_of"),
    ("organization", "territories"): ("location", "controlled_by"),
    ("organization", "items"): ("item", "affiliated_organizations"),
    # creature -- location
    ("creature", "found_in"): ("location", "inhabitants"),
    # creature -- character
    ("creature", "preyed_on_by"): ("character", "encountered_creatures"),
}


class DecisionLog:
    """Collects ambiguous/unresolved link occurrences for later review.

    Occurrences with the same ambiguity signature (link text + candidate set)
    are grouped into a single entry that tracks every affected source page and
    a running occurrence count, so reviewers decide once per unique ambiguity.
    """

    def __init__(self) -> None:
        self._entries: Dict[str, Dict[str, Any]] = {}

    def _key(self, link_text: str, candidates: List[Dict[str, Any]]) -> str:
        names = sorted(c["name"] for c in candidates)
        return json.dumps({"link_text": link_text, "candidates": names}, sort_keys=True)

    def add(
        self,
        source: str,
        link_text: str,
        candidates: List[Dict[str, Any]],
        reason: str = "multiple_candidates",
    ) -> None:
        key = self._key(link_text, candidates)
        entry = self._entries.get(key)
        if entry is None:
            entry = {
                "link_text": link_text,
                "candidates": candidates,
                "sources": [],
                "occurrence_count": 0,
                "resolved": False,
                "reason": reason,
                "recorded_at": datetime.now(timezone.utc).isoformat(),
            }
            self._entries[key] = entry
        if source not in entry["sources"]:
            entry["sources"].append(source)
        entry["occurrence_count"] += 1

    @property
    def entries(self) -> List[Dict[str, Any]]:
        return list(self._entries.values())

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.entries, indent=2), encoding="utf-8")


class InferenceResult:
    def __init__(self) -> None:
        self.relationships_created = 0
        self.ambiguous_skipped = 0
        self.unmatched = 0


def build_entity_index(entities: List[EntityModel]) -> Dict[str, List[Dict[str, Any]]]:
    """Map normalized names to candidate entities. Multiple candidates => ambiguity."""
    index: Dict[str, List[Dict[str, Any]]] = {}
    for ent in entities:
        entry = {"name": ent.name, "type": ent.entity_type, "entity": ent}
        for key in name_variants(ent.name):
            index.setdefault(key, []).append(entry)
    return index


def _add_link(field: str, entity: EntityModel, target_name: str) -> None:
    current = getattr(entity, field, None)
    if isinstance(current, list) and target_name not in current:
        current.append(target_name)


def resolve_field(source_type: str, source: str, target_type: str, section_title: Optional[str]) -> Optional[str]:
    """Determine the field on the source entity for a link to target_type."""
    if section_title:
        contextual = _section_field(section_title, target_type)
        if contextual:
            return contextual
    return DEFAULT_RULES.get((source_type, target_type))


def apply_reverse(
    target_entity: EntityModel, source_type: str, field: str, source_name: str
) -> None:
    key = (source_type, field)
    if key in REVERSE_RULES:
        _, target_field = REVERSE_RULES[key]
        _add_link(target_field, target_entity, source_name)


def run_inference(
    entities: List[EntityModel],
    decision_log: DecisionLog,
    result: InferenceResult,
    confidence_threshold: float = 0.6,
) -> None:
    """Populate typed relationships across all entities in place."""
    index = build_entity_index(entities)
    for ent in entities:
        if isinstance(ent, GenericPage):
            _run_for_generic(ent, index, decision_log, result)
        else:
            _run_for_entity(ent, index, decision_log, result, confidence_threshold)


def _run_for_entity(
    ent: EntityModel,
    index: Dict[str, List[Dict[str, Any]]],
    decision_log: DecisionLog,
    result: InferenceResult,
    confidence_threshold: float,
) -> None:
    # Determine section context for each link.
    link_to_section: Dict[str, str] = {}
    for section_title, links in ent.section_links.items():
        for link in links:
            link_to_section.setdefault(normalize_name(link), section_title)

    for raw in dict.fromkeys(ent.raw_links):
        key = normalize_name(raw)
        candidates = index.get(key, [])
        # Skip self-links
        candidates = [c for c in candidates if c["name"] != ent.name]
        if not candidates:
            result.unmatched += 1
            continue
        # Prefer candidates above the confidence threshold.
        eligible = [
            c for c in candidates
            if getattr(c["entity"], "confidence", 0.0) >= confidence_threshold
        ]
        if not eligible and candidates:
            eligible = candidates
        if len(eligible) > 1 or len(candidates) > 1:
            decision_log.add(
                ent.name,
                raw,
                [
                    {"name": c["name"], "type": c["type"], "confidence": round(getattr(c["entity"], "confidence", 0.0), 2)}
                    for c in candidates
                ],
                reason="multiple_candidates",
            )
            result.ambiguous_skipped += 1
            continue

        target = eligible[0]
        target_entity = target["entity"]
        section_title = link_to_section.get(key)
        field = resolve_field(ent.entity_type, ent.name, target["type"], section_title)
        if field is None:
            result.unmatched += 1
            continue
        _add_link(field, ent, target["name"])
        apply_reverse(target_entity, ent.entity_type, field, ent.name)
        result.relationships_created += 1


def _run_for_generic(
    ent: GenericPage,
    index: Dict[str, List[Dict[str, Any]]],
    decision_log: DecisionLog,
    result: InferenceResult,
) -> None:
    from lore_extractor.models import EntityModel as E

    for raw in dict.fromkeys(ent.raw_links):
        candidates = [c for c in index.get(normalize_name(raw), []) if c["name"] != ent.name]
        if not candidates:
            result.unmatched += 1
            continue
        if len(candidates) > 1:
            decision_log.add(
                ent.name,
                raw,
                [{"name": c["name"], "type": c["type"], "confidence": round(getattr(c["entity"], "confidence", 0.0), 2)} for c in candidates],
                reason="multiple_candidates",
            )
            result.ambiguous_skipped += 1
            continue
        target = candidates[0]
        bucket = f"related_{target['type']}"
        if bucket not in ent.related:
            ent.related[bucket] = []
        if target["name"] not in ent.related[bucket]:
            ent.related[bucket].append(target["name"])
        result.relationships_created += 1
