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


def test_update_resolution_and_rerun_applies_it():
    a = _c("Akame", raw_links=["Wave"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([a, w1, w2], log, res)
    assert a.relationships == []
    assert len(log.unresolved_entries()) == 1

    log.update_resolution(log.unresolved_entries()[0], "Wave (Technique)")
    res2 = InferenceResult()
    run_inference([a, w1, w2], log, res2)
    assert "Wave (Technique)" in a.relationships
    assert "Wave" not in a.relationships
    assert log.unresolved_entries() == []


def test_rerun_inference_after_resolution_is_idempotent():
    a = _c("Akame", raw_links=["Wave"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    log = DecisionLog()
    res = InferenceResult()
    run_inference([a, w1, w2], log, res)
    log.update_resolution(log.unresolved_entries()[0], "Wave")
    res2 = InferenceResult()
    run_inference([a, w1, w2], log, res2)
    run_inference([a, w1, w2], log, InferenceResult())
    assert a.relationships.count("Wave") == 1


def test_pre_resolved_ambiguity_applied_from_file(tmp_path):
    p = tmp_path / "ambiguous_links.json"
    log1 = DecisionLog()
    a = _c("Akame", raw_links=["Wave"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    run_inference([a, w1, w2], log1, InferenceResult())
    assert a.relationships == []
    log1.update_resolution(log1.unresolved_entries()[0], "Wave")
    log1.write(p)

    log2 = DecisionLog(decisions_path=p)
    assert log2.unresolved_entries() == []
    res = InferenceResult()
    run_inference([a, w1, w2], log2, res)
    assert "Wave" in a.relationships
    assert res.ambiguous_skipped == 0


def test_resolved_ambiguity_not_relogged_when_loaded(tmp_path):
    p = tmp_path / "ambiguous_links.json"
    log1 = DecisionLog()
    a = _c("Akame", raw_links=["Wave"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    run_inference([a, w1, w2], log1, InferenceResult())
    log1.update_resolution(log1.unresolved_entries()[0], "Wave (Technique)")
    log1.write(p)

    log2 = DecisionLog(decisions_path=p)
    run_inference([a, w1, w2], log2, InferenceResult())
    assert log2.unresolved_entries() == []


def test_generic_resolution_applied_from_file(tmp_path):
    from lore_extractor.models import GenericPage

    p = tmp_path / "ambiguous_links.json"
    g = GenericPage(name="Timeline", raw_links=["Wave"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    log1 = DecisionLog()
    run_inference([g, w1, w2], log1, InferenceResult())
    log1.update_resolution(log1.unresolved_entries()[0], "Wave (Technique)")
    log1.write(p)

    log2 = DecisionLog(decisions_path=p)
    run_inference([g, w1, w2], log2, InferenceResult())
    assert "Wave (Technique)" in g.related["related_character"]

