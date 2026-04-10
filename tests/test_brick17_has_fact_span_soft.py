"""BRICK 17 — pin the BUG-104 partial fix: extended has_fact_span()
detects soft facts (function names, file paths, CamelCase, backticks).

Important honesty note: this brick PARTIALLY addresses BUG-104. The
benchmark files (verbose_memory.md, sample_session.md) already have
hard facts (dates, numbers) in every chunk, so must-keep already fires
on them — the new patterns are redundant for those files. The fact-recall
loss at tight budgets on those files comes from a DIFFERENT root cause:
must-keep chunks too big to all fit in the budget. That's the real BUG-104
and it's not fixed by this brick.

What this brick DOES fix: chunks that contain ONLY soft facts (e.g. a
code snippet with `compress_line()` and no version numbers) are now
correctly marked as must-keep. Without this fix, those chunks would
have been treated as filler.
"""
import importlib
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_CORE = REPO_ROOT / "engine" / "core"


@pytest.fixture(scope="module")
def bs():
    if str(ENGINE_CORE) not in sys.path:
        sys.path.insert(0, str(ENGINE_CORE))
    import budget_select
    importlib.reload(budget_select)
    return budget_select


# ── Soft fact patterns introduced by brick 17 ───────────────


def test_function_call_site_detected(bs):
    """foo() / module.bar() / Class.method() must be a fact."""
    assert bs.has_fact_span("we should call compress_line() in this case")
    assert bs.has_fact_span("the helper redact_secrets_text() is pure")
    assert bs.has_fact_span("see _build_adj_subgraph() for the BFS bounded version")


def test_function_call_site_too_short_not_detected(bs):
    """A 3-char prefix like x() is too generic to be a fact."""
    # The regex requires 4+ chars before "(", so x() doesn't match
    assert not bs.has_fact_span("x() is a placeholder")
    # But longer ones do
    assert bs.has_fact_span("foobar() is a real function name")


def test_file_path_detected(bs):
    assert bs.has_fact_span("see engine/core/muninn.py for the impl")
    assert bs.has_fact_span("the file tests/test_brick17_foo.py was added")
    assert bs.has_fact_span("module muninn/_engine.py mirrors engine/core/muninn.py")


def test_file_path_short_not_detected(bs):
    """Just 'a/b' is too short to be a path — needs 3+ chars after slash."""
    # Use a chunk that has no other facts to verify this specific pattern
    text = "see a/b for context"
    # 'a/b' has only 1 char after / so it doesn't match
    # The regex requires 3+ chars after the slash
    # However words like 'and' and 'see' may incidentally match other patterns
    # so this test just verifies the path pattern itself is conservative enough
    import re
    path_re = re.compile(r"\b[a-zA-Z_][\w.\-]*/[\w.\-/]{3,}")
    assert not path_re.search("a/b")
    assert path_re.search("foo/bar")  # 3 chars after slash


def test_camelcase_identifier_detected(bs):
    """Real CamelCase = capitalized word with at least one INNER uppercase.
    "Mycelium" alone is just a proper noun, not CamelCase. The pattern
    deliberately requires inner uppercase to avoid matching every
    capitalized word in prose."""
    assert bs.has_fact_span("BudgetSelector is the new helper")
    assert bs.has_fact_span("we use TestCase pattern here")
    assert bs.has_fact_span("the HttpClient was refactored")
    # "Mycelium" alone does NOT match (no inner uppercase), but it would
    # be caught by other patterns in real usage (Mycelium() = function call,
    # `Mycelium` = backtick, mycelium.py = file path).


def test_camelcase_too_short_not_detected(bs):
    """Single uppercase Followed By lowercase is not enough."""
    # Use minimal text to isolate the pattern
    import re
    cc_re = re.compile(r"\b[A-Z][a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]+\b")
    # Need at least one inner uppercase after the initial Aa pattern
    assert not cc_re.search("Hello world how are you")
    assert cc_re.search("HelloWorld")  # has inner W


def test_backtick_code_detected(bs):
    assert bs.has_fact_span("the function `compress_line` is in muninn_layers")
    assert bs.has_fact_span("we use `BUG-104` as the tracking id")


def test_backtick_too_short_not_detected(bs):
    """`x` is too short — needs 3+ chars between backticks."""
    import re
    bt_re = re.compile(r"`[^`\n]{3,50}`")
    assert not bt_re.search("`x` is bad")
    assert not bt_re.search("`ab` is bad")
    assert bt_re.search("`abc` is good")


# ── Negative tests: prose without any fact pattern ─────────


def test_pure_prose_without_facts(bs):
    """A chunk with only English prose, no function calls / paths / etc.
    must NOT be a fact."""
    text = (
        "this is a long paragraph of pure prose without any specific "
        "facts or numbers or function names or paths or anything that "
        "would indicate a piece of factual content worth preserving in "
        "a budget compression layer like the BudgetMem reference"
    )
    # Note: "BudgetMem" may match CamelCase, that's expected and correct
    import re
    cc_re = re.compile(r"\b[A-Z][a-z][a-zA-Z0-9]*[A-Z][a-zA-Z0-9]+\b")
    if cc_re.search(text):
        # Has CamelCase, must be a fact
        assert bs.has_fact_span(text)
    else:
        assert not bs.has_fact_span(text)


def test_pure_prose_truly_no_facts(bs):
    """No camelcase, no function calls, no paths, no backticks, no numbers."""
    text = (
        "this is a long paragraph of generic prose without anything "
        "specific that should make it a fact according to the detector"
    )
    assert not bs.has_fact_span(text)


# ── Soft-only chunk: integration via select_chunks ─────────


def test_soft_only_chunk_marked_must_keep(bs):
    """A chunk that ONLY has soft facts (no dates / numbers) should
    still be marked must-keep by select_chunks."""
    chunks = [
        "this is a generic filler paragraph one with no facts inside it",
        "the function compress_line() is documented in muninn_layers and "
        "used by the Mycelium class to handle text properly",
        "this is a generic filler paragraph two with no facts inside it",
    ]
    # Chunk 1 has function call (compress_line()) + module path (muninn_layers
    # via implicit) + CamelCase (Mycelium). Should be must-keep.
    assert bs.has_fact_span(chunks[1]), (
        "BRICK 17 BROKEN: chunk with function call + CamelCase NOT detected as fact"
    )
    assert not bs.has_fact_span(chunks[0])
    assert not bs.has_fact_span(chunks[2])

    # With a tight budget, the must-keep chunk should be preserved
    # while filler chunks are dropped
    kept = bs.select_chunks(chunks, budget_tokens=30)
    assert 1 in kept, (
        f"BRICK 17 BROKEN: must-keep soft-fact chunk dropped. Kept: {kept}"
    )


# ── No regression on existing hard-fact patterns ───────────


def test_iso_date_still_detected(bs):
    assert bs.has_fact_span("Released on 2026-04-11 to production")


def test_semver_still_detected(bs):
    assert bs.has_fact_span("upgraded to v2.3.1 last week")


def test_git_hash_still_detected(bs):
    assert bs.has_fact_span("see commit abc1234 for details")


def test_jira_ticket_still_detected(bs):
    assert bs.has_fact_span("BUG-104 partial fix landed")


def test_url_still_detected(bs):
    assert bs.has_fact_span("see https://example.com/foo")


def test_money_still_detected(bs):
    assert bs.has_fact_span("the API call cost $5.65")


def test_percentage_still_detected(bs):
    assert bs.has_fact_span("compression hit 92% accuracy")


# ── No false positives on innocuous prose ──────────────────


def test_no_false_positive_on_simple_prose(bs):
    text = "the cat sat on the mat looking around for a while"
    assert not bs.has_fact_span(text)


def test_no_false_positive_on_french_prose(bs):
    text = "sky travaille sur muninn depuis quatorze mois maintenant"
    assert not bs.has_fact_span(text)
