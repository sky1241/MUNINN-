"""
AUDIT 2026-04-10 — Hypothesis-based property tests for hook detector functions.

After Sky's "you didn't use forge correctly" feedback, this file uses
Hypothesis (the same lib forge --gen-props uses) to fuzz the deterministic
detector functions inside the hooks. The hook scripts themselves are
imported via importlib (because they're in .claude/hooks/, not a Python
package path).

What we're testing:
- check_destructive(command) - never crashes on any string input
- check_secret_exposure(command) - never crashes on any string input
- find_hardcode_in_content(content) - never crashes on any string
- is_protected_path(file_path) - never crashes on any string
- _safe_summary(tool_name, error) [post_tool_failure] - never crashes
- _truncate_with_marker(text, max_chars) [subagent_start] - never crashes
- count_chained_commands(text) [_secrets] - never crashes
- clamp_chained_commands(text, max_chains) [_secrets] - never crashes

Each test:
- 200 random inputs (more aggressive than forge default)
- Includes degenerate cases: empty string, single char, very long, control
  chars, mixed unicode, null bytes, binary garbage decoded as latin-1
- Expects: no crash. The function may return False/empty/(False, "") but
  must NEVER raise an unhandled exception.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

try:
    from hypothesis import given, strategies as st, settings, HealthCheck
except ImportError:
    pytest.skip("hypothesis not installed", allow_module_level=True)

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOKS_DIR = REPO_ROOT / ".claude" / "hooks"
ENGINE_CORE = REPO_ROOT / "engine" / "core"

if str(ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(ENGINE_CORE))


def _load_hook(name: str):
    """Load a hook script as a module via importlib."""
    path = HOOKS_DIR / name
    spec = importlib.util.spec_from_file_location(f"hook_{name[:-3]}", str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ── Aggressive text strategy ──────────────────────────────────


# Mix of regular text + unicode + control chars + null + very long
text_strategy = st.one_of(
    st.text(max_size=200),
    st.text(alphabet=st.characters(blacklist_categories=()), max_size=100),
    st.binary(max_size=100).map(lambda b: b.decode("latin-1", errors="replace")),
    st.just(""),
    st.just(" "),
    st.just("\x00"),
    st.just("\n" * 50),
    st.text(min_size=500, max_size=2000),
)

settings_aggressive = settings(
    max_examples=200,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow],
)


# ── _secrets.py functions (already covered, but we add aggressive cases) ──


@given(text=text_strategy)
@settings_aggressive
def test_count_chained_commands_no_crash(text):
    from _secrets import count_chained_commands
    count_chained_commands(text)  # must not raise


@given(text=text_strategy, max_chains=st.integers(-1000, 1000))
@settings_aggressive
def test_clamp_chained_commands_no_crash(text, max_chains):
    from _secrets import clamp_chained_commands
    result, was_clamped = clamp_chained_commands(text, max_chains)
    assert isinstance(was_clamped, bool)


@given(text=text_strategy)
@settings_aggressive
def test_redact_secrets_text_no_crash(text):
    from _secrets import redact_secrets_text
    result = redact_secrets_text(text)
    assert isinstance(result, str) or result is None


# ── pre_tool_use_bash_destructive.check_destructive ──


@pytest.fixture(scope="module")
def hook_destructive():
    return _load_hook("pre_tool_use_bash_destructive.py")


@given(command=text_strategy)
@settings_aggressive
def test_check_destructive_no_crash(command):
    mod = _load_hook("pre_tool_use_bash_destructive.py")
    is_dest, label = mod.check_destructive(command)
    assert isinstance(is_dest, bool)
    assert isinstance(label, str)


# ── pre_tool_use_bash_secrets.check_secret_exposure ──


@given(command=text_strategy)
@settings_aggressive
def test_check_secret_exposure_no_crash(command):
    mod = _load_hook("pre_tool_use_bash_secrets.py")
    would, reason = mod.check_secret_exposure(command)
    assert isinstance(would, bool)
    assert isinstance(reason, str)


# ── pre_tool_use_edit_hardcode functions ──


@given(content=text_strategy)
@settings_aggressive
def test_find_hardcode_in_content_no_crash(content):
    mod = _load_hook("pre_tool_use_edit_hardcode.py")
    found, sample = mod.find_hardcode_in_content(content)
    assert isinstance(found, bool)
    assert isinstance(sample, str)


@given(file_path=text_strategy)
@settings_aggressive
def test_is_protected_path_no_crash(file_path):
    mod = _load_hook("pre_tool_use_edit_hardcode.py")
    result = mod.is_protected_path(file_path)
    assert isinstance(result, bool)


# ── post_tool_failure_hook._safe_summary ──


@given(
    tool_name=st.one_of(st.text(max_size=50), st.just(""), st.just("Bash")),
    error=text_strategy,
)
@settings_aggressive
def test_safe_summary_no_crash(tool_name, error):
    mod = _load_hook("post_tool_failure_hook.py")
    summary = mod._safe_summary(tool_name, error)
    assert isinstance(summary, str)
    assert len(summary) <= 250  # max_len + " | " + tool_name overhead


# ── subagent_start_hook._truncate_with_marker ──


@given(
    text=text_strategy,
    max_chars=st.integers(50, 100000),
)
@settings_aggressive
def test_truncate_with_marker_no_crash(text, max_chars):
    mod = _load_hook("subagent_start_hook.py")
    result = mod._truncate_with_marker(text, max_chars)
    assert isinstance(result, str)
    # If text was longer than max_chars, result must be <= max_chars
    if len(text) > max_chars:
        assert len(result) <= max_chars


# ── feed_errors_json edge cases (post_tool_failure) ──


@given(
    payload=st.one_of(
        st.dictionaries(
            keys=st.text(max_size=20),
            values=st.one_of(
                st.text(max_size=100),
                st.integers(),
                st.none(),
                st.lists(st.text(max_size=50), max_size=5),
            ),
            max_size=10,
        ),
        st.none(),
        st.lists(st.integers(), max_size=5),
        st.text(max_size=50),
    )
)
@settings(max_examples=100, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.function_scoped_fixture])
def test_feed_errors_json_no_crash(payload, tmp_path_factory):
    """feed_errors_json must NEVER raise on any payload type."""
    mod = _load_hook("post_tool_failure_hook.py")
    repo = tmp_path_factory.mktemp("test_feed")
    (repo / ".muninn").mkdir()
    try:
        result = mod.feed_errors_json(payload, repo)
        assert isinstance(result, bool)
    except Exception as e:
        pytest.fail(f"feed_errors_json raised on payload {type(payload).__name__}: {e}")
