# Fandom Wiki Lore Extractor — Plan

A command-line tool that extracts character, lore, location, item, organization, and creature
information from any Fandom wiki via the MediaWiki API.

Example wiki: <https://akamegakill.fandom.com/wiki/>

---

## Architecture

```
lore-extractor/
├── pyproject.toml
├── README.md
├── PLAN.md
├── src/
│   └── lore_extractor/
│       ├── __init__.py
│       ├── __main__.py          # python -m lore_extractor
│       ├── cli.py               # Click CLI interface
│       ├── api.py               # MediaWiki API client (rate-limited, retry logic)
│       ├── parser.py            # Wikitext → structured data (mwparserfromhell)
│       ├── classifier.py        # Entity type classifier
│       ├── discovery.py         # BFS/DFS crawl from entrypoint
│       ├── models.py            # Pydantic models
│       ├── inference.py         # Relationship inference engine
│       ├── decision.py          # Ambiguous link decision logging
│       ├── extractors/
│       │   ├── __init__.py
│       │   ├── base.py          # Base extractor interface
│       │   ├── character.py
│       │   ├── location.py
│       │   ├── item.py
│       │   ├── organization.py
│       │   ├── creature.py
│       │   └── lore.py
│       └── formatters/
│           ├── __init__.py
│           ├── json.py          # Structured JSON output
│           └── markdown.py      # Human-readable Markdown
├── tests/
│   ├── test_parser.py
│   ├── test_classifier.py
│   ├── test_extractors.py
│   ├── test_inference.py
│   └── fixtures/
│       └── akame_wikitext.txt
└── .gitignore
```

---

## Core Strategy

Use the **MediaWiki API** (`https://{wiki}/api.php`) to fetch raw **wikitext** rather than
parsing rendered HTML. Wikitext is structured markup (`{{Infobox Character}}`, `==History==`,
`[[Links]]`, `[[Category:...]]`) that can be parsed reliably into data.

### Key API endpoints
- `action=parse&prop=wikitext|sections|categories|links|images|templates`
- `action=query&list=categorymembers`
- `action=query&titles={page}&redirects=1`

### Pipeline flow

```
1. DISCOVER → BFS crawl from entrypoint
     ↓
2. FETCH → Download wikitext via MediaWiki API
     ↓
3. PARSE → Extract infoboxes, sections, links, categories
     ↓
4. CLASSIFY → Detect entity type (character/location/item/org/creature/lore)
     ↓
5. EXTRACT → Run type-specific extractor
     ↓
6. INDEX → Build entity lookup table (name → type)
     ↓
7. INFER → Cross-reference links, populate typed relationships
     ↓
8. LINK → Create bidirectional relationships
     ↓
9. OUTPUT → JSON (structured) + Markdown (human-readable)
     ↓
10. DECISIONS → Write ambiguous-link decisions to a decision file
```

---

## Component Details

### 1. MediaWiki API Client (`api.py`)
- Base URL: `https://{wiki_domain}/api.php`
- **Rate limiting**: 1 req/sec (configurable)
- **Retry logic**: Exponential backoff with `tenacity`
- **Redirect following**: `redirects=1`
- **Error handling**: Network errors, API limits, missing pages
- Uses `requests` and one shared HTTP session.

### 2. Wikitext Parser (`parser.py`)
Uses `mwparserfromhell` to decompose wikitext into:
- **Infobox templates**: `{{Infobox Character|name=...|age=...}}`
- **Sections**: `==Appearance==`, `===History===`
- **Internal links**: `[[Akame]]`, `[[Tatsumi|Tatsumi's page]]`
- **Categories**: `[[Category:Characters]]`
- **Clean text**: Strip markup, refs, templates for plain-text output

### 3. Entity Classifier (`classifier.py`)
Auto-classifies every page using a **confidence-based system** checking multiple signals.
If signals conflict, the most specific match wins (e.g., `Infobox Character` > `Category:Characters`).

| Entity Type | Detected By |
|---|---|
| **Character** | `{{Infobox Character}}`, `{{Infobox Person}}`, `Category:Characters` |
| **Location** | `{{Infobox Location}}`, `{{Infobox Place}}`, `Category:Locations` |
| **Item/Weapon** | `{{Infobox Item}}`, `{{Infobox Weapon}}`, `{{Infobox Teigu}}`, `Category:Weapons`, `Category:Items` |
| **Organization** | `{{Infobox Organization}}`, `{{Infobox Faction}}`, `Category:Organizations`, `Category:Factions` |
| **Creature** | `{{Infobox Creature}}`, `{{Infobox Beast}}`, `Category:Creatures`, `Category:Animals` |
| **Lore** | Pages with `Plot`, `Story`, `Synopsis`, `Events` sections but no entity infobox |

Extractor routing order: **Character** → **Location** → **Item** → **Organization** →
**Creature** → **Lore** → **Generic** (fallback).

### 4. Data Models (`models.py`)
Pydantic models with typed relationship fields (see "Relationship Inference" below).

### 5. Extraction (`extractors/`)
One extractor per entity type. Each reads the parsed wikitext, pulls the infobox fields and
relevant named sections, and produces the typed model. A generic extractor handles any page
that does not match a known entity type.

---

## Relationship Inference (`inference.py`)

After all pages are extracted and classified, a **second pass** resolves raw links into typed
relationships using an entity index: `normalized_name -> {type, canonical_name}`.

### Inference rules (source → target)

| Source | Target | Field(s) populated |
|---|---|---|
| Character → Item | `equipment`, `weapons` |
| Character → Organization | `factions`, `affiliations` |
| Character → Character | `relationships`, `allies`, `enemies`, `family` |
| Character → Creature | `encountered_creatures` |
| Character → Location | `associated_locations` |
| Location → Character | `inhabitants`, `rulers`, `notable_residents` |
| Location → Organization | `controlled_by`, `headquarters_of` |
| Item → Character | `owners`, `creators`, `wielders` |
| Item → Organization | `affiliated_organizations` |
| Organization → Character | `members`, `leaders`, `founders` |
| Organization → Organization | `allies`, `enemies`, `subgroups` |
| Organization → Location | `territories`, `headquarters` |
| Creature → Location | `habitats` |
| Lore → Any | `related_entities` (typed by target) |

### Context-aware inference
Uses **section context** to disambiguate relationship meaning:
- `==Equipment==` → `equipment`
- `==Family==` → `family`
- `==Allies==` → `allies`
- `==Enemies==` → `enemies`

### Bidirectional links
Relationships are symmetric where applicable (e.g., Character.equipment → Item implies
Item.owners → Character).

### Ambiguity handling & decision file (`decision.py`)
When a link is ambiguous (the normalized name matches more than one entity, or the
confidence is unclear), the tool does **not** guess silently. Instead it:

1. Records the ambiguous link and the candidate matches in a **decision file**
   (JSON by default): `{output_dir}/decisions/ambiguous_links.json`.
2. **Skiips** the ambiguous relationship (does not force a wrong match), but keeps a
   record so the user can review and correct later.
3. A `--confidence` threshold can lower/raise how much is auto-accepted.

Decision file schema (per ambiguous occurrence):

```json
{
  "source": "Akame",
  "link_text": "Wave",
  "candidates": [
    {"name": "Wave (Character)", "type": "character", "confidence": 0.7},
    {"name": "Wave (Technique)", "type": "item", "confidence": 0.5}
  ],
  "resolved": false,
  "reason": "multiple_candidates"
}
```

The decision file is also written for pages whose classification fell back to "generic"
or "lore" unexpectedly, so the user can audit the extraction.

---

## Output

### JSON formatter (`formatters/json.py`)
- One JSON file per page: `{output_dir}/pages/{page_title}.json`
- Combined data: `{output_dir}/wiki_data.json`

```json
{
  "wiki": "akamegakill.fandom.com",
  "crawled_at": "2026-08-21T12:00:00Z",
  "pages_crawled": 247,
  "entities": {
    "characters": [...],
    "locations": [...],
    "items": [...],
    "organizations": [...],
    "creatures": [...],
    "lore": [...]
  }
}
```

### Markdown formatter (`formatters/markdown.py`)
- One Markdown file per page with headers and section hierarchy.
- Clean readable text (no wikitext markup).

### Raw links flag
- `--keep-links` (flag): when set, the raw internal `links` list is kept in each page's
  output alongside the inferred typed relationships. Default: raw links removed.

---

## CLI Interface

```bash
# Single entrypoint (discover linked pages)
lore-extractor --wiki akamegakill.fandom.com \
               --entrypoint "Akame" \
               --output ./akamegakill_data \
               --format json,markdown \
               --max-pages 200 \
               --depth 2

# Category-based crawl
lore-extractor --wiki akamegakill.fandom.com \
               --category "Characters" \
               --output ./akamegakill_data \
               --format json

# Combined crawl (entrypoint + category)
lore-extractor --wiki akamegakill.fandom.com \
               --entrypoint "Akame" \
               --category "Teigu" \
               --output ./akamegakill_data \
               --format markdown

# Keep raw links in output
lore-extractor --wiki akamegakill.fandom.com \
               --entrypoint "Akame" \
               --output ./akamegakill_data \
               --keep-links

# Filter by entity type
lore-extractor --wiki akamegakill.fandom.com \
               --category "Teigu" \
               --output ./akamegakill_data \
               --entities item,character

# Confidence threshold for relationship inference
lore-extractor --wiki akamegakill.fandom.com \
               --entrypoint "Akame" \
               --output ./akamegakill_data \
               --confidence 0.8

# Resume an interrupted crawl
lore-extractor --wiki akamegakill.fandom.com \
               --resume ./akamegakill_data/crawl_state.json

# Summary report
lore-extractor --wiki akamegakill.fandom.com \
               --entrypoint "Main_Page" \
               --output ./akamegakill_data \
               --report
```

### CLI flags summary

| Flag | Type | Default | Description |
|---|---|---|---|
| `--wiki` | str | required | Fandom wiki domain (e.g. `akamegakill.fandom.com`) |
| `--entrypoint` | str | — | Starting page to crawl and expand from |
| `--category` | str | — | Category whose members to crawl |
| `--output` | str | `./out` | Output directory |
| `--format` | choices | `json,markdown` | Output formats (comma-separated) |
| `--max-pages` | int | unlimited | Max pages to crawl |
| `--depth` | int | unlimited | Max crawl depth from entrypoint |
| `--entities` | str | all | Comma-separated entity types to keep |
| `--confidence` | float | 0.6 | Min confidence to auto-accept relationship |
| `--keep-links` | flag | off | Keep raw internal links in output |
| `--resume` | path | — | Resume from saved crawl state |
| `--report` | flag | off | Print summary report |
| `--rate` | float | 1.0 | API requests per second |

---

## Dependencies

```toml
[project]
dependencies = [
    "requests>=2.31.0",
    "mwparserfromhell>=0.6.5",
    "pydantic>=2.5.0",
    "click>=8.1.0",
    "tenacity>=8.2.0",
    "tqdm>=4.66.0",
]
```

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| MediaWiki API over HTML scraping | Structured wikitext is far more reliable than rendered HTML (which is heavy with ads/JS). |
| mwparserfromhell | Industry-standard wikitext parser; robust with nested templates/links/sections. |
| Confidence-based entity classification | Handles inconsistent infobox naming across wikis; most-specific signal wins. |
| BFS crawl with depth limit | Prevents runaway crawls while still discovering related entities. |
| Text-only | No image downloads; simpler and faster. |
| Pydantic models | Type safety, validation, easy JSON serialization. |
| Two-pass inference | Full entity index available before resolving links into typed relationships. |
| Decision file for ambiguous links | Never silently guess; record for user review. |

---

## Edge Cases & Handling

- **Redirects**: Automatically resolved via API (`redirects=1`).
- **Disambiguation pages**: Detected by title/content pattern; skipped from extraction.
- **Missing infoboxes**: Fallback to generic extractor (extracts sections + links).
- **Large pages**: API has size limits; handle via continuation parameters if needed.
- **Rate limits**: Built-in 1 req/sec + retry with backoff.
- **Unicode/special chars**: Proper URL encoding for API requests.
- **Ambiguous links**: Recorded in the decision file, not force-resolved.
- **Crawler dedup**: Every page is fetched exactly once (a `queued_set` prevents a link
  from being enqueued twice). With no `--max-pages`/`--depth`, the crawl keeps going
  only as long as it discovers new pages, then terminates when the wiki is exhausted.
- **Domain containment**: Only local article (namespace 0) links are queued. Links with
  interwiki/namespace prefixes (e.g. `w:`, `en:`, `Category:`, `Template:`, `Special:`)
  are never followed, so the crawl never leaves the wiki.
- **Entity filter does not stop discovery**: `--entities` affects which entities are
  kept in output, but every visited page's links are still expanded so the full wiki
  graph is explored (needed for accurate relationship inference).

---

## Testing

Automated tests live in `tests/` (run with `python -m pytest tests/`):

- `tests/test_parser.py` — section tree, infoboxes, links, categories, and text cleaning
  using real wikitext fixtures (`tests/fixtures/`).
- `tests/test_classifier.py` — infobox/category/lore/generic classification and
  signal precedence (infobox beats category).
- `tests/test_extractors.py` — entity extraction into typed models.
- `tests/test_inference.py` — typed + bidirectional relationships, section-context
  disambiguation, and decision-file ambiguity handling.
- `tests/test_api.py` — MediaWiki API client against mocked responses (`responses`).

Verified end-to-end against the real Akame Ga Kill! wiki (small constrained crawls).

---

## Implementation Order

1. Project scaffolding (`pyproject.toml`, structure, `.gitignore`)
2. API client
3. Parser
4. Models
5. Classifier
6. Extractors
7. Discovery/crawl engine
8. Inference engine + decision logging
9. Formatters
10. CLI
11. Tests
