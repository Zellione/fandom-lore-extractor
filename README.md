# Lore Extractor

A command-line tool that extracts **character**, **lore**, **location**, **item**,
**organization**, and **creature** information from any Fandom wiki via the MediaWiki API.

See [PLAN.md](PLAN.md) for the full design.

## Install

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Quick start

```bash
lore-extractor --wiki akamegakill.fandom.com \
               --entrypoint "Akame" \
               --output ./out \
               --format json,markdown
```

## CLI

```
Usage: lore-extractor [OPTIONS]

Options:
  --wiki TEXT                Fandom wiki domain (e.g. akamegakill.fandom.com)
  --entrypoint TEXT          Starting page to crawl and expand from
  --category TEXT            Category whose members to crawl
  --output PATH              Output directory  [default: ./out]
  --format TEXT              Output formats, comma-separated (json, markdown)  [default: json,markdown]
  --max-pages INTEGER        Max pages to crawl
  --depth INTEGER            Max crawl depth from entrypoint
  --entities TEXT            Entity types to keep, comma-separated
  --confidence FLOAT         Min confidence to auto-accept a relationship  [default: 0.6]
  --keep-links               Keep raw internal links in each page's output
  --flat-output, --no-organize
                             Write all per-page files flat into pages/ instead of
                             organizing them into entity-type subdirectories
  --resume PATH              Resume from a saved crawl state file
  --report                   Print a summary report
  --rate FLOAT               API requests per second  [default: 1.0]
  --decisions PATH           Path to a saved decisions/ambiguous_links.json file. Loaded
                             automatically when it exists at the default location.
  --resolve-decisions        Interactively resolve ambiguous links after inference instead
                             of only logging them
  --use-llm                  Use an OpenAI-compatible endpoint to resolve ambiguous links
  --llm-url TEXT             Base URL of the OpenAI-compatible endpoint (overrides OPENAI_BASE_URL)
  --llm-model TEXT           Model to use (overrides auto-discovery from the endpoint)
  --llm-key TEXT             API key (overrides OPENAI_API_KEY)
  --llm-single-prompt        Send one prompt per ambiguity instead of one batched prompt
  --llm-temperature FLOAT    Sampling temperature for the LLM  [default: 0.0]
  --help                     Show this message and exit.
```

### `resolve` subcommand

Review and resolve saved decisions **without** re-crawling:

```
Usage: lore-extractor resolve [OPTIONS]

Options:
  --wiki TEXT                Fandom wiki domain (used to locate the default decisions file)
  --output PATH              Output directory (for the default decisions path)  [default: ./out]
  --decisions PATH           Path to a saved decisions/ambiguous_links.json file
                             (default: <output>/<wiki>/decisions/ambiguous_links.json)
  --use-llm                  Use an OpenAI-compatible endpoint to resolve ambiguous links
  --llm-url TEXT             Base URL of the OpenAI-compatible endpoint (overrides OPENAI_BASE_URL)
  --llm-model TEXT           Model to use (overrides auto-discovery from the endpoint)
  --llm-key TEXT             API key (overrides OPENAI_API_KEY)
  --llm-single-prompt        Send one prompt per ambiguity instead of one batched prompt
  --llm-temperature FLOAT    Sampling temperature for the LLM  [default: 0.0]
  --help                     Show this message and exit.
```

## Output

Output is written under a subfolder named after the wiki domain, so multiple
extractions can coexist in the same base directory. With `--output ./out` and
`--wiki akamegakill.fandom.com`:

- `out/akamegakill.fandom.com/wiki_data.json` — combined structured data
- `out/akamegakill.fandom.com/pages/*.json` — one JSON file per page
- `out/akamegakill.fandom.com/pages/*.md` — one Markdown file per page
- `out/akamegakill.fandom.com/decisions/ambiguous_links.json` — ambiguous relationship links for manual review
- `out/akamegakill.fandom.com/decisions/llm_reasoning.json` — LLM reasoning/errors written when using `--use-llm`

By default, per-page files under `pages/` are organized into entity-type
subdirectories (e.g. `pages/character/`, `pages/location/`). Pass
`--flat-output` (or `--no-organize`) to write them all flat into `pages/`.
