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
  --wiki TEXT             Fandom wiki domain (e.g. akamegakill.fandom.com)
  --entrypoint TEXT       Starting page to crawl and expand from
  --category TEXT         Category whose members to crawl
  --output PATH           Output directory  [default: ./out]
  --format TEXT           Output formats, comma-separated (json, markdown)  [default: json,markdown]
  --max-pages INTEGER     Max pages to crawl
  --depth INTEGER         Max crawl depth from entrypoint
  --entities TEXT         Entity types to keep, comma-separated
  --confidence FLOAT      Min confidence to auto-accept a relationship  [default: 0.6]
  --keep-links            Keep raw internal links in each page's output
  --resume PATH           Resume from a saved crawl state file
  --report                Print a summary report
  --help                  Show this message and exit.
```

## Output

- `out/wiki_data.json` — combined structured data
- `out/pages/*.json` — one JSON file per page
- `out/pages/*.md` — one Markdown file per page
- `out/decisions/ambiguous_links.json` — ambiguous relationship links for manual review
