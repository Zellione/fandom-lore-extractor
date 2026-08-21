"""Command-line interface for lore-extractor."""
from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import List, Optional, Tuple

import click

from lore_extractor.api import WikiClient
from lore_extractor.discovery import Crawler
from lore_extractor.formatters.json import write_json_files
from lore_extractor.formatters.markdown import write_markdown_files
from lore_extractor.inference import DecisionLog, InferenceResult, run_inference

VALID_ENTITY_TYPES = ["character", "location", "item", "organization", "creature", "lore", "generic"]


def _parse_entity_types(raw: Optional[str]) -> Optional[List[str]]:
    if not raw:
        return None
    types = [t.strip().lower() for t in raw.split(",") if t.strip()]
    invalid = [t for t in types if t not in VALID_ENTITY_TYPES]
    if invalid:
        raise click.BadParameter(
            f"Unknown entity type(s): {', '.join(invalid)}. "
            f"Valid: {', '.join(VALID_ENTITY_TYPES)}"
        )
    return types


def _parse_formats(raw: str) -> List[str]:
    formats = [f.strip().lower() for f in raw.split(",") if f.strip()]
    for f in formats:
        if f not in ("json", "markdown"):
            raise click.BadParameter(f"Unknown output format: {f}. Use 'json' or 'markdown'.")
    return formats


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--wiki", required=True, help="Fandom wiki domain, e.g. akamegakill.fandom.com")
@click.option("--entrypoint", help="Starting page to crawl and expand from")
@click.option("--category", help="Category whose members to crawl")
@click.option("--output", "output", default="./out", show_default=True, type=click.Path(path_type=Path),
              help="Output directory")
@click.option("--format", "fmt", default="json,markdown", show_default=True,
              help="Output formats, comma-separated (json, markdown)")
@click.option("--max-pages", type=int, default=None, help="Max pages to crawl")
@click.option("--depth", type=int, default=None, help="Max crawl depth from entrypoint")
@click.option("--entities", "entity_filter", type=str, default=None,
              help="Entity types to keep, comma-separated "
                   "(character, location, item, organization, creature, lore, generic)")
@click.option("--confidence", type=float, default=0.6, show_default=True,
              help="Min confidence to auto-accept a relationship")
@click.option("--keep-links", is_flag=True, default=False,
              help="Keep raw internal links in each page's output")
@click.option("--flat-output", "--no-organize", "flat_output", is_flag=True, default=False,
              help="Write all per-page files flat into pages/ instead of "
                   "organizing them into entity-type subdirectories")
@click.option("--resume", type=click.Path(path_type=Path), default=None,
              help="Resume from a saved crawl state file")
@click.option("--report", is_flag=True, default=False, help="Print a summary report")
@click.option("--rate", "rate", type=float, default=1.0, show_default=True,
              help="API requests per second")
def main(
    wiki: str,
    entrypoint: Optional[str],
    category: Optional[str],
    output: Path,
    fmt: str,
    max_pages: Optional[int],
    depth: Optional[int],
    entity_filter: Optional[str],
    confidence: float,
    keep_links: bool,
    flat_output: bool,
    resume: Optional[Path],
    report: bool,
    rate: float,
) -> None:
    """Extract character, lore, location, item, organization and creature data
    from a Fandom wiki via the MediaWiki API."""
    if not entrypoint and not category and not resume:
        raise click.UsageError(
            "Provide at least one of --entrypoint, --category, or --resume."
        )

    formats = _parse_formats(fmt)
    entity_types = _parse_entity_types(entity_filter)

    client = WikiClient(wiki, rate_per_sec=rate)
    crawler = Crawler(
        client=client,
        entrypoint=entrypoint,
        category=category,
        max_pages=max_pages,
        max_depth=depth,
        entities_filter=entity_types,
        resume_file=resume,
    )

    click.echo(f"Crawling {wiki} ...")
    crawl_result = crawler.crawl()
    entities = crawl_result.entities

    # Relationship inference
    decision_log = DecisionLog()
    result = InferenceResult()
    run_inference(entities, decision_log, result, confidence_threshold=confidence)

    # Write output
    output.mkdir(parents=True, exist_ok=True)
    organize = not flat_output
    if "json" in formats:
        write_json_files(
            entities, output, wiki, len(crawl_result.visited),
            keep_links=keep_links, organize=organize,
        )
    if "markdown" in formats:
        write_markdown_files(entities, output, organize=organize)

    # Decision file (ambiguous links + unknown classifications)
    decision_path = output / "decisions" / "ambiguous_links.json"
    decision_log.write(decision_path)

    if report:
        _print_report(crawl_result, entities, result, decision_log, decision_path, wiki)

    click.echo(
        f"Done. {len(crawl_result.visited)} pages crawled, "
        f"{len(entities)} entities extracted -> {output}"
    )


def _print_report(
    crawl_result, entities, result: InferenceResult, decision_log: DecisionLog,
    decision_path: Path, wiki: str,
) -> None:
    counts = Counter(e.entity_type for e in entities)
    click.echo("\n=== Report ===")
    click.echo(f"Wiki: {wiki}")
    click.echo(f"Pages crawled: {len(crawl_result.visited)}")
    click.echo(f"   skipped:   {len(crawl_result.skipped)}")
    click.echo(f"   not found: {len(crawl_result.not_found)}")
    click.echo(f"   errors:    {len(crawl_result.errors)}")
    click.echo(f"Entities extracted: {len(entities)}")
    for etype in ("character", "location", "item", "organization", "creature", "lore", "generic"):
        n = counts.get(etype, 0)
        if n:
            click.echo(f"   {etype:15} {n}")
    click.echo(f"Relationships inferred: {result.relationships_created}")
    click.echo(f"   ambiguous skipped:   {result.ambiguous_skipped}")
    click.echo(f"   unmatched links:     {result.unmatched}")
    click.echo(f"Decision file: {decision_path} "
               f"({len(decision_log.entries)} entries)")
    click.echo("")


if __name__ == "__main__":
    main()
