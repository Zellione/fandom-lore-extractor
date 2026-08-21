"""Wikitext parsing utilities built on mwparserfromhell.

Produces a structured representation of a page: infobox templates, a section
tree with clean text, and per-section internal links.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import mwparserfromhell as mwp

# Templates that are never meaningful infoboxes (navigation, layout, tabs, etc.)
INFOBOK_NON_INFOBOTEMPLATES = {
    "tabs", "tab", "tabber", "toc", "navbox", "navigation",
    "stub", "infobox", "ambox", "defaultsort",
}

# Common "box-like" templates that should be ignored when classifying,
# since they are layout helpers rather than entity definitions.
LAYOUT_TEMPLATE_HINTS = ("tab", "clear", "col", "sidebar")


def normalize_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _clean_fragment(text: str) -> str:
    """Clean a fragment of wikitext into plain text, stripping markup."""
    code = mwp.parse(str(text))
    # Remove references and comments
    for ref in list(code.filter_tags(matches=lambda n: str(n.tag).lower() == "ref")):
        try:
            code.remove(ref)
        except ValueError:
            pass
    for c in list(code.filter_comments()):
        try:
            code.remove(c)
        except ValueError:
            pass
    # Strip HTML tags (keep inner content) - iterate safely.
    for tag in list(code.filter_tags()):
        try:
            code.replace(tag, "".join(str(n) for n in tag.contents))
        except ValueError:
            pass
    # Strip templates repeatedly until none remain (handles nesting/staleness).
    while True:
        tmpls = list(code.filter_templates(recursive=True))
        if not tmpls:
            break
        changed = False
        for t in tmpls:
            try:
                code.replace(t, "")
                changed = True
            except ValueError:
                continue
        if not changed:
            break
    # Unwrap wikilinks preserving display text; drop file/category links.
    for link in list(code.filter_wikilinks()):
        try:
            raw = str(link.title).strip()
            if raw.lower().startswith(("file:", "image:", "category:")):
                code.remove(link)
                continue
            text_part = link.text if link.text is not None else link.title
            code.replace(link, str(text_part))
        except ValueError:
            pass
    return normalize_whitespace(str(code))


@dataclass
class Section:
    """A section of a page, possibly with nested subsections."""

    title: str
    level: int
    content: str = ""
    links: List[str] = field(default_factory=list)
    subsections: List["Section"] = field(default_factory=list)


@dataclass
class Infobox:
    """A single extracted infobox template."""

    name: str
    fields: Dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedPage:
    """Structured representation of a parsed page."""

    title: str
    lead: str = ""
    lead_links: List[str] = field(default_factory=list)
    sections: List[Section] = field(default_factory=list)
    infoboxes: List[Infobox] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)

    def flat_sections(self) -> List[Section]:
        """All sections (including subsections) in document order, without lead."""

        def walk(sections: List[Section]) -> List[Section]:
            out: List[Section] = []
            for s in sections:
                out.append(s)
                out.extend(walk(s.subsections))
            return out

        return walk(self.sections)

    def find_sections(self, title: str) -> List[Section]:
        """Find top-level (or folded) sections matching a title (case-insensitive)."""
        text = title.strip().lower()
        return [s for s in self.flat_sections() if s.title.strip().lower() == text]


def _parse_infobox(template) -> Optional[Infobox]:
    name = str(template.name).strip()
    if not name.lower().startswith("infobox"):
        return None
    infobox = Infobox(name=name)
    for param in template.params:
        key = str(param.name).strip()
        value = str(param.value).strip()
        if not key:
            continue
        infobox.fields[key] = value
    return infobox


def _iter_sections(code) -> List[Section]:
    """Build a section tree from ``get_sections(flat=True)`` using heading levels.

    ``flat=True`` returns one Wikicode per heading, each containing only its own
    content (subsections are separate entries), which lets us reconstruct the
    hierarchy from heading levels without recursion.
    """
    flat_sections = code.get_sections(include_lead=False, flat=True)
    root: List[Section] = []
    stack: List[Section] = []  # stack of open sections by nesting depth

    for section in flat_sections:
        headings = section.filter_headings()
        if not headings:
            continue
        heading = headings[0]
        level = heading.level
        title = str(heading.title).strip()
        cleaned = _strip_heading_lines(str(section))
        node = Section(
            title=title,
            level=level,
            content=_clean_fragment(cleaned),
            links=_extract_links(cleaned),
        )
        # Pop stack entries deeper than current level.
        while stack and stack[-1].level >= level:
            stack.pop()
        if stack:
            stack[-1].subsections.append(node)
        else:
            root.append(node)
        stack.append(node)
    return root


def _strip_heading_lines(text: str) -> str:
    """Remove ``==Heading==`` lines from a section's wikitext string."""
    out: List[str] = []
    for line in text.splitlines(keepends=True):
        if mwp.parse(line).filter_headings():
            continue
        out.append(line)
    return "".join(out)


def _extract_links(code) -> List[str]:
    """Extract the titles of internal wikilinks, excluding categories/files."""
    parsed = code if isinstance(code, mwp.wikicode.Wikicode) else mwp.parse(str(code))
    titles: List[str] = []
    for link in parsed.filter_wikilinks():
        raw = str(link.title).strip()
        if raw.lower().startswith("category:") or raw.lower().startswith("file:"):
            continue
        if ":" in raw and raw.split(":", 1)[0] in ("special", "wikipedia", "w", "help", "template", "wikt"):
            continue
        titles.append(raw)
    return titles


def parse_wikitext(wikitext: str, title: str = "") -> ParsedPage:
    """Parse raw wikitext into a :class:`ParsedPage`."""
    code = mwp.parse(wikitext)

    infoboxes: List[Infobox] = []
    for template in code.filter_templates(recursive=True):
        ib = _parse_infobox(template)
        if ib is not None:
            infoboxes.append(ib)

    # Lead (before first heading)
    lead_code = code.get_sections(include_lead=True, include_headings=False)[:1]
    lead = ""
    lead_links: List[str] = []
    if lead_code:
        lead_wikicode = lead_code[0]
        lead = _clean_fragment(lead_wikicode)
        lead_links = _extract_links(lead_wikicode)

    sections = _iter_sections(code)

    categories = [
        str(link.title).replace("Category:", "").strip()
        for link in code.filter_wikilinks()
        if str(link.title).strip().lower().startswith("category:")
    ]

    return ParsedPage(
        title=title,
        lead=lead,
        lead_links=lead_links,
        sections=sections,
        infoboxes=infoboxes,
        categories=categories,
    )
