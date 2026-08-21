from io import StringIO

from lore_extractor.inference import DecisionLog, InferenceResult, run_inference
from lore_extractor.models import Character
from lore_extractor.resolvers import InteractiveResolver


def _c(name, raw_links=None, confidence=0.9):
    return Character(name=name, raw_links=raw_links or [], confidence=confidence)


def _build_log():
    a = _c("Akame", raw_links=["Wave"])
    w1 = _c("Wave", confidence=0.9)
    w2 = _c("Wave (Technique)", confidence=0.5)
    log = DecisionLog()
    run_inference([a, w1, w2], log, InferenceResult())
    return log, a, w1, w2


def _run(answers, log):
    stdin = StringIO(answers)
    stdout = StringIO()
    resolver = InteractiveResolver(log, stdin=stdin, stdout=stdout)
    resolved = resolver.run()
    return resolved, stdout.getvalue()


def test_pick_by_number():
    log, a, w1, w2 = _build_log()
    n, out = _run("2\n", log)
    assert n == 1
    entry = log.entries[0]
    assert entry["resolved"] is True
    assert entry["resolution"] == "Wave (Technique)"
    assert "Ambiguity:" in out


def test_auto_picks_highest_confidence():
    log, a, w1, w2 = _build_log()
    n, out = _run("a\n", log)
    assert n == 1
    assert log.entries[0]["resolution"] == "Wave"


def test_skip_leaves_unresolved():
    log, a, w1, w2 = _build_log()
    n, out = _run("s\n", log)
    assert n == 0
    assert log.entries[0]["resolved"] is False


def test_quit_leaves_unresolved():
    log, a, w1, w2 = _build_log()
    n, out = _run("q\n", log)
    assert n == 0
    assert log.entries[0]["resolved"] is False


def test_invalid_then_valid_choice():
    log, a, w1, w2 = _build_log()
    n, out = _run("9\n1\n", log)
    assert n == 1
    assert log.entries[0]["resolution"] == "Wave"
    assert "Invalid choice." in out


def test_eof_stops_session():
    log, a, w1, w2 = _build_log()
    n, out = _run("", log)
    assert n == 0


def test_multiple_entries_prompted_sequentially():
    a = _c("Akame", raw_links=["Wave", "Mine"])
    w1 = _c("Wave")
    w2 = _c("Wave (Technique)")
    m1 = _c("Mine")
    m2 = _c("Mine (Technique)")
    log = DecisionLog()
    run_inference([a, w1, w2, m1, m2], log, InferenceResult())
    assert len(log.unresolved_entries()) == 2
    n, out = _run("1\n2\n", log)
    assert n == 2
    texts = {e["link_text"]: e["resolution"] for e in log.entries}
    assert texts == {"Wave": "Wave", "Mine": "Mine (Technique)"}


def test_no_unresolved_entries():
    log = DecisionLog()
    n, out = _run("", log)
    assert n == 0
    assert "No unresolved decisions" in out
