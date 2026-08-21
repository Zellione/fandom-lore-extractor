"""Output writers: JSON and Markdown."""

# Map entity type -> directory name used when organizing output by type.
ENTITY_DIRS: dict = {
    "character": "characters",
    "location": "locations",
    "item": "items",
    "organization": "organizations",
    "creature": "creatures",
    "lore": "lore",
    "generic": "generic",
}