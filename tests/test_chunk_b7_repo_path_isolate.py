"""CHUNK B7 — autouse fixture _repo_path_isolate.

Tests modify `muninn._REPO_PATH` (a module global) to point at tmp_path.
If a test crashes before its `finally:` restore, OR if pytest runs
parallel workers, the next test inherits a stale _REPO_PATH and
operates on someone else's tmp directory — silent cross-pollution.

Fix: add an autouse fixture in conftest.py that snapshots and restores
`_REPO_PATH` (and the dependent TREE_DIR / TREE_META resolved by
`_refresh_tree_paths`) around every test. Tests can still set the
global; the fixture guarantees cleanup.

Source: docs/CHUNKS_AUDIT2_FIX_LIST_2026-05-08.md §B7
"""
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parent.parent


def test_repo_path_isolation_a(tmp_path):
    """Test A pollutes _REPO_PATH; fixture must restore it before test B."""
    import muninn
    muninn._REPO_PATH = tmp_path / "test_a_dir"
    # Do NOT manually restore — rely on the autouse fixture.


def test_repo_path_isolation_b(tmp_path):
    """Test B must NOT see test A's _REPO_PATH.

    Pre-fix: this test sees /tmp/.../test_a_dir, contaminating its
    operations. After the autouse fixture, _REPO_PATH is restored to
    its pre-test-A value (None or the conftest baseline).
    """
    import muninn
    # The autouse fixture should have reset _REPO_PATH between tests.
    # We can't predict the exact value (depends on conftest state) but
    # it must NOT be the leftover test_a_dir.
    leaked = (tmp_path.parent / "test_repo_path_isolation_a0" / "test_a_dir")
    assert muninn._REPO_PATH != leaked, (
        f"_REPO_PATH leaked from previous test: {muninn._REPO_PATH}"
    )


def test_repo_path_after_explicit_set_inside_test(tmp_path):
    """A test that DELIBERATELY sets _REPO_PATH must observe its own value."""
    import muninn
    target = tmp_path / "explicit"
    muninn._REPO_PATH = target
    assert muninn._REPO_PATH == target


def test_repo_path_does_not_leak_across_tests_explicit(tmp_path, request):
    """Final isolation check: after all the tests above, _REPO_PATH is
    not pointing at any of their tmp_paths."""
    import muninn
    # We expect the fixture restores to None (or to whatever conftest
    # set originally). What we CAN check is that it's not equal to any
    # specific tmp_path from previous tests.
    forbidden_substrings = [
        "test_repo_path_isolation_a",
        "test_repo_path_after_explicit_set",
    ]
    val = str(muninn._REPO_PATH) if muninn._REPO_PATH else ""
    for sub in forbidden_substrings:
        assert sub not in val, f"leaked path detected: {val}"
