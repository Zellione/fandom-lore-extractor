from pathlib import Path

import pytest

from lore_extractor.classifier import classify_page
from lore_extractor.extractors import extract_entity
from lore_extractor.formatters.json import write_json_files
from lore_extractor.formatters.markdown import write_markdown_files
from lore_extractor.parser import parse_wikitext

FIXTURES = Path(__file__).parent / "fixtures"


def _entities():
    out = []
    for filename, title in (("akame_wikitext.txt", "Akame"), ("murasame_wikitext.txt", "Murasame")):
        text = (FIXTURES / filename).read_text(encoding="utf-8")
        parsed = parse_wikitext(text, title=title)
        cl = classify_page(parsed)
        out.append(extract_entity(parsed, title, cl, f"https://wiki/{title}", []))
    return out


def _files_under(root: Path):
    return sorted(p.relative_to(root).as_posix() for p in root.rglob("*.*"))


def test_markdown_organized_by_default(tmp_path):
    write_markdown_files(_entities(), tmp_path)
    files = _files_under(tmp_path)
    assert "pages/characters/Akame.md" in files
    assert "pages/items/Murasame.md" in files


def test_markdown_flat_output(tmp_path):
    write_markdown_files(_entities(), tmp_path, organize=False)
    files = _files_under(tmp_path)
    assert "pages/Akame.md" in files
    assert "pages/Murasame.md" in files


def test_json_organized_by_default(tmp_path):
    write_json_files(_entities(), tmp_path, "wiki", pages_crawled=2)
    files = _files_under(tmp_path)
    assert "pages/characters/Akame.json" in files
    assert "pages/items/Murasame.json" in files
    assert "wiki_data.json" in files


def test_json_flat_output(tmp_path):
    write_json_files(_entities(), tmp_path, "wiki", pages_crawled=2, organize=False)
    files = _files_under(tmp_path)
    assert "pages/Akame.json" in files
    assert "pages/Murasame.json" in files
    assert "wiki_data.json" in files


def test_unknown_entity_type_goes_to_generic(tmp_path):
    from lore_extractor.models import EntityModel

    generic = EntityModel(name="Mystery", entity_type="generic", source_url="u")
    write_markdown_files([generic], tmp_path)
    assert "pages/generic/Mystery.md" in _files_under(tmp_path)