"""Crawl engine: discover and extract entities from a wiki entrypoint.

Performs a breadth-first expansion from a starting page and/or category members,
deduplicating visited pages and applying configurable constraints (max pages,
max depth). Each visited page is fetched, parsed, classified and extracted into
an :class:`~lore_extractor.models.EntityModel`.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from tqdm import tqdm

from lore_extractor.api import WikiClient
from lore_extractor.classifier import Classification, classify_page
from lore_extractor.extractors import extract_entity
from lore_extractor.models import EntityModel
from lore_extractor.parser import parse_wikitext

SPECIAL_TITLE_HINTS = (
    "image gallery",
    "gallery",
    "quotes",
    "trivia",
    "list of",
    "list_of",
    ":",
)


def _is_skippable_title(title: str) -> bool:
    low = title.lower()
    return any(h in low for h in SPECIAL_TITLE_HINTS)


@dataclass
class CrawlResult:
    entities: List[EntityModel] = field(default_factory=list)
    visited: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    not_found: List[str] = field(default_factory=list)
    errors: Dict[str, str] = field(default_factory=dict)

    @property
    def visited_set(self) -> Set[str]:
        return set(self.visited)


class Crawler:
    def __init__(
        self,
        client: WikiClient,
        entrypoint: Optional[str] = None,
        category: Optional[str] = None,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        entities_filter: Optional[List[str]] = None,
        resume_file: Optional[Path] = None,
    ) -> None:
        self.client = client
        self.entrypoint = entrypoint
        self.category = category
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.entities_filter = set(entities_filter) if entities_filter else None
        self.resume_file = resume_file

    # -- state persistence --------------------------------------------
    def _save_state(self, visited: List[str], queue_state: List[str]) -> None:
        if not self.resume_file:
            return
        self.resume_file.parent.mkdir(parents=True, exist_ok=True)
        state = {
            "visited": visited,
            "queue_state": queue_state,
            "entrypoint": self.entrypoint,
            "category": self.category,
        }
        self.resume_file.write_text(json.dumps(state, indent=2), encoding="utf-8")

    def _load_state(self) -> Optional[Tuple[List[str], List[str]]]:
        if self.resume_file and self.resume_file.exists():
            try:
                state = json.loads(self.resume_file.read_text(encoding="utf-8"))
                visited = state.get("visited", [])
                queued = state.get("queue_state", [])
                if visited or queued:
                    return visited, queued
            except (json.JSONDecodeError, OSError):
                pass
        return None

    # -- main crawl ---------------------------------------------------
    def crawl(self) -> CrawlResult:
        result = CrawlResult()
        visited_set: Set[str] = set()

        loaded = self._load_state()
        if loaded is not None:
            visited, queued = loaded
            visited_set = set(visited)
            result.visited = list(visited)
            queue: List[Tuple[str, int]] = [(t, 0) for t in queued]
            depth_of: Dict[str, int] = {t: 0 for t in queued}
            queued_set: Set[str] = set(queued)
        else:
            queue = []
            depth_of = {}
            queued_set = set()

            def seed(title: str, _depth: int = 0) -> None:
                if title not in visited_set and title not in queued_set:
                    queue.append((title, _depth))
                    depth_of[title] = _depth
                    queued_set.add(title)

            if self.category:
                for member in self.client.get_category_members(self.category):
                    seed(member)
            if self.entrypoint:
                seed(self.entrypoint)

        cap = self.max_pages if self.max_pages else float("inf")
        with tqdm(disable=None) as pbar:
            pbar.set_description("Crawling")
            while queue:
                if len(visited_set) >= cap:
                    break
                title, depth = queue.pop(0)
                # Only count truly-unique pages toward the cap / progress.
                if title in visited_set:
                    continue

                if _is_skippable_title(title):
                    result.skipped.append(title)
                    continue
                if self.max_depth is not None and depth > self.max_depth:
                    continue

                page = None
                try:
                    page = self.client.get_page(title)
                except Exception as exc:  # network / transient errors
                    result.errors[title] = str(exc)
                    result.visited.append(title)
                    visited_set.add(title)
                    pbar.update(1)
                    self._save_state(result.visited, [t for t, _ in queue])
                    continue

                result.visited.append(title)
                visited_set.add(title)
                pbar.update(1)

                if page is None:
                    result.not_found.append(title)
                    self._save_state(result.visited, [t for t, _ in queue])
                    continue

                parsed = parse_wikitext(page["wikitext"], title=page["title"])
                classification: Classification = classify_page(parsed)
                source_url = self.client.page_absolute_url(page["title"])
                entity = extract_entity(
                    parsed,
                    page["title"],
                    classification,
                    source_url,
                    page["links"],
                )

                # The entity-type filter only affects OUTPUT, not discovery:
                # links from every page (even filtered-out types) still expand
                # the crawl so the wiki is fully explored.
                if not (self.entities_filter and classification.entity_type not in self.entities_filter):
                    result.entities.append(entity)

                if self.max_depth is None or depth + 1 <= self.max_depth:
                    for link in entity.raw_links:
                        if (
                            link in visited_set
                            or link in queued_set
                            or link in result.skipped
                            or _is_skippable_title(link)
                            or not self._is_local_link(link)
                        ):
                            continue
                        nd = depth_of.get(link)
                        if nd is None or nd > depth + 1:
                            nd = depth + 1
                            depth_of[link] = nd
                            queue.append((link, nd))
                            queued_set.add(link)

                self._save_state(result.visited, [t for t, _ in queue])

        return result

    @staticmethod
    def _is_local_link(title: str) -> bool:
        """Return True if a title is a same-wiki article link.

        MediaWiki namespace-0 links are already local. Any title carrying an
        interwiki/namespace ``:`` prefix (e.g. ``w:``, ``en:``, ``Category:``,
        ``Template:``, ``Special:``) is treated as non-local and skipped so the
        crawl never leaves the wiki domain.
        """
        if ":" in title:
            prefix = title.split(":", 1)[0]
            if prefix and prefix.lower() in {
                "w", "wikipedia", "en", "de", "es", "fr", "ru", "zh", "id",
                "category", "template", "file", "image", "special", "help",
                "talk", "user", "project", "portal",
            }:
                return False
        return True
