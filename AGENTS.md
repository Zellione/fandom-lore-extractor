# Agent Notes — lore-extractor

## Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

## Running tests
```bash
pytest
# focused:
pytest tests/test_parser.py -k infobox
```
- `pyproject.toml` sets `pythonpath = ["src"]`; `tests/conftest.py` also injects `src/` into `sys.path`.
- HTTP calls are mocked with `responses`. Real wikitext fixtures live in `tests/fixtures/`.
- **Avoid live crawls in routine tests.** If an edge case needs real data, create a new fixture in `tests/fixtures/` rather than hitting a wiki endpoint.

## Entrypoints
- CLI script: `lore-extractor --wiki <domain> --entrypoint <page>`
- Module: `python -m lore_extractor` (same CLI)

## Architecture (src/lore_extractor/)
Pipeline order matters:
1. `api.py` — MediaWiki client (rate-limited, retries via `tenacity`)
2. `parser.py` — wikitext → infoboxes/sections/links (`mwparserfromhell`)
3. `classifier.py` — entity type from infobox/category signals
4. `extractors/` — type-specific extraction into Pydantic models (`models.py`)
5. `discovery.py` — BFS crawl from entrypoint/category
6. `inference.py` — **two-pass** relationship inference (full entity index first, then resolve links)
7. `formatters/json.py` & `formatters/markdown.py` — output writers

## CLI gotchas
- `--rate` defaults to **1 req/sec**.
- `--confidence` (default 0.6) controls auto-accept of inferred relationships.
- `--flat-output` / `--no-organize` disables per-entity-type subdirectories in `pages/`.
- `--resume` expects a saved crawl state file.
- `--entities` filters **output only**; discovery still crawls every linked page for accurate inference.
- Without `--keep-links`, raw internal links are stripped from output.

## Decisions / ambiguity
Ambiguous or low-confidence relationships are **not silently guessed**. They are logged to `{output}/decisions/ambiguous_links.json` for manual review.

## Tooling
No linting, formatting, or type-checking is currently enforced.
