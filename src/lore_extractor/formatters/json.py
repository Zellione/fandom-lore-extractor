"""JSON output formatting."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

from lore_extractor.models import EntityModel


def build_combined(
    entities: List[EntityModel],
    wiki: str,
    pages_crawled: int,
    keep_links: bool = False,
) -> Dict:
    buckets: Dict[str, List[dict]] = {
        "characters": [], "locations": [], "items": [],
        "organizations": [], "creatures": [], "lore": [], "generic": [],
    }
    for ent in entities:
        buckets.setdefault(ent.entity_type, []).append(ent.to_dict(keep_links=keep_links))
    order = ["characters", "locations", "items", "organizations", "creatures", "lore", "generic"]
    entities_out = {k: buckets[k] for k in order}
    return {
        "wiki": wiki,
        "crawled_at": datetime.now(timezone.utc).isoformat(),
        "pages_crawled": pages_crawled,
        "entities": entities_out,
    }


def write_json_files(
    entities: List[EntityModel],
    output_dir: Path,
    wiki: str,
    pages_crawled: int,
    keep_links: bool = False,
) -> None:
    """Write per-page JSON files and a combined wiki_data.json."""
    pages_dir = output_dir / "pages"
    pages_dir.mkdir(parents=True, exist_ok=True)
    for ent in entities:
        safe = _safe_filename(ent.name)
        (pages_dir / f"{safe}.json").write_text(
            json.dumps(ent.to_dict(keep_links=keep_links), indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    combined = build_combined(entities, wiki, pages_crawled, keep_links)
    (output_dir / "wiki_data.json").write_text(
        json.dumps(combined, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def _safe_filename(name: str) -> str:
    import re

    return re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip() or "page"
