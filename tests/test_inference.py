from lore_extractor.inference import (
    DecisionLog,
    InferenceResult,
    normalize_name,
    run_inference,
)
from lore_extractor.models import Character, Item, Organization


def _c(name, raw_links=None, section_links=None):
    return Character(
        name=name,
        raw_links=raw_links or [],
        section_links=section_links or {},
        confidence=0.9,
    )


def _i(name, raw_links=None):
    return Item(name=name, raw_links=raw_links or [], confidence=0.9)


def _o(name, raw_links=None):
    return Organization(name=name, raw_links=raw_links or [], confidence=0.9)


def test_normalize_name():
    assert normalize_name("Akame") == "akame"
    assert normalize_name("Night Raid") == "nightraid"
    assert normalize_name("  Tatsumi ") == "tatsumi"
    assert normalize_name("Chapter 1 (Zero)") == "chapter1"


def test_character_to_item_equipment_and_reverse():
    akame = _c("Akame", raw_links=["Murasame"])
    murasame = _i("Murasame")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([akame, murasame], log, res, confidence_threshold=0.5)
    assert "Murasame" in akame.equipment
    assert "Akame" in murasame.owners  # reverse link


def test_character_to_organization_faction_and_reverse():
    akame = _c("Akame", raw_links=["Night Raid"])
    nr = _o("Night Raid")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([akame, nr], log, res)
    assert "Night Raid" in akame.factions
    assert "Akame" in nr.members  # reverse


def test_section_context_family():
    kurome = _c("Kurome")
    akame = _c("Akame", section_links={"Family": ["Kurome"]}, raw_links=["Kurome"])
    log = DecisionLog()
    res = InferenceResult()
    run_inference([akame, kurome], log, res)
    assert "Kurome" in akame.family
    # reverse: character--character family maps back to family
    assert "Akame" in kurome.family


def test_ambiguous_links_logged_not_resolved():
    a = _c("Akame", raw_links=["Wave"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([a, w1, w2], log, res)
    assert a.relationships == []  # not resolved
    assert len(log.entries) == 1
    assert log.entries[0]["link_text"] == "Wave"
    assert log.entries[0]["sources"] == ["Akame"]
    assert log.entries[0]["occurrence_count"] == 1
    assert log.entries[0]["resolved"] is False
    assert len(log.entries[0]["candidates"]) == 2


def test_ambiguous_links_grouped_across_sources():
    a = _c("Akame", raw_links=["Wave"])
    k = _c("Kurome", raw_links=["Wave"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([a, k, w1, w2], log, res)
    assert len(log.entries) == 1
    entry = log.entries[0]
    assert entry["link_text"] == "Wave"
    assert set(entry["sources"]) == {"Akame", "Kurome"}
    assert entry["occurrence_count"] == 2


def test_duplicate_raw_links_deduplicated_per_entity():
    a = _c("Akame", raw_links=["Wave", "Wave"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([a, w1, w2], log, res)
    assert len(log.entries) == 1
    assert log.entries[0]["sources"] == ["Akame"]
    assert log.entries[0]["occurrence_count"] == 1


def test_distinct_ambiguities_stay_separate():
    a = _c("Akame", raw_links=["Wave", "Mine"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    m1 = _c("Mine")
    m2 = _c("Mine (Technique)")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([a, w1, w2, m1, m2], log, res)
    assert len(log.entries) == 2
    texts = {e["link_text"] for e in log.entries}
    assert texts == {"Wave", "Mine"}


def test_self_links_skipped():
    a = _c("Akame", raw_links=["Akame", "Murasame"])
    m = _i("Murasame")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([a, m], log, res)
    assert "Akame" not in a.relationships
    assert "Murasame" in a.equipment


def test_unmatched_links_counted():
    a = _c("Akame", raw_links=["Nonexistent Page"])
    log = DecisionLog()
    res = InferenceResult()
    run_inference([a], log, res)
    assert res.unmatched == 1
    assert log.entries == []
