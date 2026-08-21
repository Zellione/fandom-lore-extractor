"""Pydantic data models for extracted entities and relationship inference.

Each entity model carries a set of *typed relationship* fields that are
populated during the inference pass (see ``inference.py``). The raw link
list may optionally be retained (``--keep-links``).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

EntityTypeName = Literal[
    "character", "location", "item", "organization", "creature", "lore", "generic"
]


class EntityModel(BaseModel):
    """Base for all extracted entities."""

    name: str
    title: str = ""
    aliases: List[str] = Field(default_factory=list)
    entity_type: EntityTypeName
    infobox: Dict[str, Any] = Field(default_factory=dict)
    categories: List[str] = Field(default_factory=list)
    source_url: str = ""
    raw_links: List[str] = Field(default_factory=list, exclude=True)
    sections: Dict[str, str] = Field(default_factory=dict)
    # Per-section internal links (title -> list of link titles), used for
    # context-aware relationship inference and not serialized.
    section_links: Dict[str, List[str]] = Field(default_factory=dict, exclude=True)
    extracted_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    # Confidence of the classification, 0..1
    confidence: float = 0.0

    def to_dict(self, keep_links: bool = False) -> Dict[str, Any]:
        """Serializable dict. Raw links are included only when ``keep_links``."""
        data = self.model_dump(mode="json", exclude_none=True)
        if keep_links:
            data["raw_links"] = self.raw_links
        return data


class Character(EntityModel):
    entity_type: Literal["character"] = "character"
    # section-derived prose
    appearance: Optional[str] = None
    personality: Optional[str] = None
    history: Optional[str] = None
    abilities: Optional[str] = None
    trivia: Optional[str] = None
    # typed relationships
    equipment: List[str] = Field(default_factory=list)  # items
    weapons: List[str] = Field(default_factory=list)  # items
    factions: List[str] = Field(default_factory=list)  # organizations
    affiliations: List[str] = Field(default_factory=list)  # organizations
    family: List[str] = Field(default_factory=list)  # characters
    allies: List[str] = Field(default_factory=list)  # characters
    enemies: List[str] = Field(default_factory=list)  # characters
    relationships: List[str] = Field(default_factory=list)  # characters
    associated_locations: List[str] = Field(default_factory=list)  # locations
    encountered_creatures: List[str] = Field(default_factory=list)  # creatures


class Location(EntityModel):
    entity_type: Literal["location"] = "location"
    geography: Optional[str] = None
    history: Optional[str] = None
    # typed relationships
    inhabitants: List[str] = Field(default_factory=list)  # characters
    rulers: List[str] = Field(default_factory=list)  # characters
    notable_residents: List[str] = Field(default_factory=list)  # characters
    controlled_by: List[str] = Field(default_factory=list)  # organizations
    headquarters_of: List[str] = Field(default_factory=list)  # organizations
    related_lore: List[str] = Field(default_factory=list)  # lore


class Item(EntityModel):
    entity_type: Literal["item"] = "item"
    description: Optional[str] = None
    history: Optional[str] = None
    abilities: Optional[str] = None
    # typed relationships
    owners: List[str] = Field(default_factory=list)  # characters
    creators: List[str] = Field(default_factory=list)  # characters
    wielders: List[str] = Field(default_factory=list)  # characters
    affiliated_organizations: List[str] = Field(default_factory=list)  # org


class Organization(EntityModel):
    entity_type: Literal["organization"] = "organization"
    overview: Optional[str] = None
    history: Optional[str] = None
    # typed relationships
    members: List[str] = Field(default_factory=list)  # characters
    leaders: List[str] = Field(default_factory=list)  # characters
    founders: List[str] = Field(default_factory=list)  # characters
    allies: List[str] = Field(default_factory=list)  # organizations
    enemies: List[str] = Field(default_factory=list)  # organizations
    subgroups: List[str] = Field(default_factory=list)  # organizations
    territories: List[str] = Field(default_factory=list)  # locations
    headquarters: List[str] = Field(default_factory=list)  # locations
    items: List[str] = Field(default_factory=list)  # items


class Creature(EntityModel):
    entity_type: Literal["creature"] = "creature"
    biology: Optional[str] = None
    behavior: Optional[str] = None
    habitat: Optional[str] = None
    abilities: Optional[str] = None
    # typed relationships
    found_in: List[str] = Field(default_factory=list)  # locations
    preyed_on_by: List[str] = Field(default_factory=list)  # characters


class LoreEntry(EntityModel):
    entity_type: Literal["lore"] = "lore"
    summary: Optional[str] = None
    events: List[str] = Field(default_factory=list)
    # typed relationships (mixed, by target type)
    related_characters: List[str] = Field(default_factory=list)
    related_locations: List[str] = Field(default_factory=list)
    related_items: List[str] = Field(default_factory=list)
    related_organizations: List[str] = Field(default_factory=list)
    related_creatures: List[str] = Field(default_factory=list)


class GenericPage(EntityModel):
    entity_type: Literal["generic"] = "generic"
    content: Optional[str] = None
    # free-form: inferred typed relationships grouped by type
    related: Dict[str, List[str]] = Field(default_factory=dict)


ENTITY_MODEL_MAP: Dict[str, Any] = {
    "character": Character,
    "location": Location,
    "item": Item,
    "organization": Organization,
    "creature": Creature,
    "lore": LoreEntry,
    "generic": GenericPage,
}
