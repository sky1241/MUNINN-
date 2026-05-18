"""Tests for B-UI-19 + B-UI-20: Terminal widget."""

import pytest

pytest.importorskip("PyQt6", reason="PyQt6 required for UI tests")
from PyQt6.QtCore import Qt


def test_terminal_creates(qtbot):
    """TerminalWidget creates and shows."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w.show()
    assert w.isVisible()
    assert w.accessibleName() == "Terminal"


def test_terminal_empty_state(qtbot):
    """Terminal starts with empty output."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    assert w._output.toPlainText() == ""


def test_command_history(qtbot, monkeypatch):
    """Command history stores entries.

    BRICK 22 fix: the original test pressed Enter on a free-text input,
    which calls _start_llm() which creates a REAL provider and a real
    QThread that does a network call. The follow-up _stop_llm() tries to
    join the thread but the network read doesn't honor the cancel flag,
    so the test hangs forever (no per-thread timeout fires for C-blocking
    socket reads).

    Fix: stub create_provider() to return a fake provider that returns
    immediately. The history test only cares about the _history list,
    not the LLM behavior.
    """
    import muninn.ui.terminal as term_mod

    class _FakeProvider:
        name = "fake"
        def generate(self, prompt, **kwargs):
            return ""
        def stream(self, prompt, **kwargs):
            return iter([])
        def chat(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(term_mod, "create_provider", lambda *a, **k: _FakeProvider())

    w = term_mod.TerminalWidget()
    qtbot.addWidget(w)
    w._input.setText("hello")
    w._on_enter()
    w._stop_llm()  # Cancel LLM thread (now harmless because fake provider)
    assert len(w._history) == 1
    assert w._history[0] == "hello"


def test_clear_command(qtbot):
    """Ctrl+L or /clear clears output."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._append_text("some text")
    assert w._output.toPlainText().strip() != ""
    w._handle_command("/clear")
    assert w._output.toPlainText() == ""


def test_help_command(qtbot):
    """/help shows commands."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._handle_command("/help")
    text = w._output.toPlainText()
    assert "/clear" in text
    assert "/help" in text


def test_unknown_command(qtbot):
    """Unknown command shows error."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._handle_command("/foobar")
    assert "Unknown command" in w._output.toPlainText()


def test_max_block_count(qtbot):
    """Output is limited to 5000 blocks (bug #61)."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    assert w._output.document().maximumBlockCount() == 5000


def test_breathing_hidden_by_default(qtbot):
    """Breathing indicator is hidden by default."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    assert not w._breathing.isVisible()
    assert not w._stop_btn.isVisible()


def test_stop_button_hides_after_stop(qtbot):
    """Stop cancels LLM and hides indicator."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w._stop_llm()
    assert not w._breathing.isVisible()
    assert not w._stop_btn.isVisible()


def test_set_context(qtbot):
    """set_context stores LLM context."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    w.set_context("You are helping with compression")
    assert w._context == "You are helping with compression"


def test_flash_timer(qtbot):
    """Flash timer exists and is single-shot."""
    from muninn.ui.terminal import TerminalWidget
    w = TerminalWidget()
    qtbot.addWidget(w)
    assert w._flash_timer.isSingleShot()
    assert w._flash_timer.interval() == 150


def test_reco_prereqs_missing_both(tmp_path):
    """Gate flags BOTH missing artifacts when fresh dir has nothing.

    Covers drift #6 (stale legacy tree path) + #7 (wrong /scan advice)
    found by the deep audit on 2026-05-18. CHUNK 4 introduced the gate
    hardcoded to `memory/tree.json`; BUG-091 H.5b migrated to
    `.muninn/tree/tree.json` 8 days later but forgot to update the gate.
    """
    from muninn.ui.terminal import TerminalWidget
    missing = TerminalWidget._reconstruction_prereqs_missing(tmp_path)
    assert len(missing) == 2
    assert any("tree" in m for m in missing)
    assert any("mycelium.db" in m for m in missing)
    # The advice must now say `bootstrap`, not `/scan` (drift #7).
    assert any("bootstrap" in m for m in missing)


def test_reco_prereqs_canonical_tree_satisfies(tmp_path):
    """Gate accepts `.muninn/tree/tree.json` (canonical post-H.5b path)."""
    from muninn.ui.terminal import TerminalWidget
    (tmp_path / ".muninn" / "tree").mkdir(parents=True)
    (tmp_path / ".muninn" / "tree" / "tree.json").write_text("{}")
    (tmp_path / ".muninn" / "mycelium.db").write_bytes(b"")
    missing = TerminalWidget._reconstruction_prereqs_missing(tmp_path)
    assert missing == [], f"Expected empty, got {missing}"


def test_reco_prereqs_legacy_tree_still_accepted(tmp_path):
    """Legacy `memory/tree.json` is still accepted as a fallback.

    Some old repos may still have it before `cleanup_legacy_tree()` runs.
    """
    from muninn.ui.terminal import TerminalWidget
    (tmp_path / "memory").mkdir()
    (tmp_path / "memory" / "tree.json").write_text("{}")
    (tmp_path / ".muninn").mkdir()
    (tmp_path / ".muninn" / "mycelium.db").write_bytes(b"")
    assert TerminalWidget._reconstruction_prereqs_missing(tmp_path) == []


def test_reco_prereqs_mycelium_only_missing(tmp_path):
    """Tree present, mycelium.db absent -> only mycelium reported missing.

    The advice for that single missing item must say `bootstrap`, never
    `scan` (drift #7 — `scan_repo` does not write mycelium.db).
    """
    from muninn.ui.terminal import TerminalWidget
    (tmp_path / ".muninn" / "tree").mkdir(parents=True)
    (tmp_path / ".muninn" / "tree" / "tree.json").write_text("{}")
    missing = TerminalWidget._reconstruction_prereqs_missing(tmp_path)
    assert len(missing) == 1
    assert "mycelium.db" in missing[0]
    assert "bootstrap" in missing[0]
    assert "scan" not in missing[0].lower()


def test_command_signal(qtbot, monkeypatch):
    """command_entered signal emits on Enter.

    BRICK 22 fix: same hang as test_command_history — Enter triggers a
    real LLM call. Stub create_provider() with a fake that returns
    immediately.
    """
    import muninn.ui.terminal as term_mod

    class _FakeProvider:
        name = "fake"
        def generate(self, prompt, **kwargs):
            return ""
        def stream(self, prompt, **kwargs):
            return iter([])
        def chat(self, *args, **kwargs):
            return ""

    monkeypatch.setattr(term_mod, "create_provider", lambda *a, **k: _FakeProvider())

    w = term_mod.TerminalWidget()
    qtbot.addWidget(w)
    received = []
    w.command_entered.connect(lambda t: received.append(t))
    w._input.setText("test command")
    w._on_enter()
    w._stop_llm()
    assert len(received) == 1
    assert received[0] == "test command"
