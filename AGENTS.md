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
- `lore-extractor resolve --wiki <domain>` — review/resolve saved decisions **without** re-crawling.
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
Ambiguous or low-confidence relationships are **not silently guessed**. They are logged to `{output}/{wiki}/decisions/ambiguous_links.json` for manual review.

Resolution workflows (see `resolvers.py`, `cli.py`):
- `--resolve-decisions` on a crawl run — prompts interactively *after* inference, then re-runs inference to apply the choices.
- `lore-extractor resolve` — load/`--decisions` or locate by `--wiki`/`--output`, review without re-crawling.
- `--decisions PATH` — point inference at a decisions file (default: `<output>/<wiki>/decisions/ambiguous_links.json`). **Previously resolved decisions are auto-applied** on every run; only new ambiguities are logged.
- `InteractiveResolver` prompts: `[1-N]` pick, `[a]` auto (highest confidence), `[s]` skip, `[q]` quit.
- `DecisionLog.update_resolution` / `try_resolve` / `unresolved_entries` drive the flow; inference re-runs are idempotent because `_add_link` guards list duplicates.

## LLM resolution (`--use-llm`)
Resolves ambiguities via an OpenAI-compatible endpoint (`llm_resolver.py`) instead of prompting; works on both a crawl run and `lore-extractor resolve`.
- Flags: `--use-llm`, `--llm-url`, `--llm-model`, `--llm-key`, `--llm-single-prompt`, `--llm-temperature` (default `0.0`).
- Precedence: explicit CLI flags > env vars (`OPENAI_BASE_URL`, `OPENAI_API_KEY`) > SDK defaults.
- Model selection: if `--llm-model` is omitted, the endpoint's model list is consulted — a single model auto-selected; multiple models raise an error listing them.
- Prompt strategy: **batched** by default (all unresolved entries in one call); `--llm-single-prompt` sends one call per ambiguity.
- Invalid/unknown candidate picks are re-prompted up to **3 times**; if it still fails, the entry is skipped and logged as an error.
- Reasoning: each choice's `reasoning` string (and any failures) is written to `{output}/{wiki}/decisions/llm_reasoning.json`.
- LLM tests mock the client (`tests/test_llm_resolver.py`); no live API calls.

## Tooling
No linting, formatting, or type-checking is currently enforced.
