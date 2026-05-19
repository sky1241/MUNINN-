"""
CHUNK MCP A.5 (post-A.4 hotfix) — init_tree() guard against source-repo clobber.

Bug history (2026-05-11 PM) :
  Le test E2E A.4 (`tests/test_e2e_pip_install_from_scratch.py`) a déclenché
  `muninn init` dans un tmp_path. Le subprocess Python a chargé `muninn._engine`
  qui, en mode pip-install-e, voit `MUNINN_ROOT = <source_repo>`. Les globals
  `TREE_DIR`/`TREE_META` au top du module pointaient vers `<source_repo>/.muninn/tree`
  au lieu du tmp_path. Le check `TREE_META.exists()` regardait le source repo,
  et `init_tree()` ecrasait root.mn / b01.mn du repo source de Sky.

Fix double :
  1. CLI handler `init` utilise `_m.TREE_META.exists()` au lieu de `TREE_META.exists()`
     (dynamique via _refresh_tree_paths()).
  2. `init_tree()` a un garde-fou : refuse d'ecrire si `_m.TREE_DIR` est en dehors
     du `_m._REPO_PATH` courant.

Tests :
1. init_tree() refuse d'ecrire dans un dir non-aligne avec _REPO_PATH
2. init_tree() OK quand TREE_DIR est bien sous _REPO_PATH
3. CLI init utilise _m.TREE_META (pas TREE_META global)
"""
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "engine" / "core"))


def test_init_tree_refuses_path_outside_repo(tmp_path, monkeypatch):
    """init_tree() must refuse to write if TREE_DIR is outside _REPO_PATH."""
    import muninn as core_muninn
    import muninn_tree

    fake_repo = tmp_path / "fake_repo"
    fake_repo.mkdir()
    # _REPO_PATH points to fake_repo, but TREE_DIR points to ELSEWHERE.
    monkeypatch.setattr(core_muninn, "_REPO_PATH", fake_repo, raising=False)
    bogus_dir = tmp_path / "elsewhere" / ".muninn" / "tree"
    bogus_dir.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(core_muninn, "TREE_DIR", bogus_dir, raising=False)
    monkeypatch.setattr(core_muninn, "TREE_META", bogus_dir / "tree.json", raising=False)

    with pytest.raises(RuntimeError) as exc:
        muninn_tree.init_tree()
    assert "REFUSING init_tree" in str(exc.value) or "outside" in str(exc.value).lower()


def test_init_tree_ok_when_aligned(tmp_path, monkeypatch):
    """init_tree() proceeds normally when TREE_DIR is under _REPO_PATH."""
    import muninn as core_muninn
    import muninn_tree

    fake_repo = tmp_path / "ok_repo"
    fake_repo.mkdir()
    (fake_repo / ".muninn").mkdir()
    monkeypatch.setattr(core_muninn, "_REPO_PATH", fake_repo, raising=False)
    aligned_dir = fake_repo / ".muninn" / "tree"
    monkeypatch.setattr(core_muninn, "TREE_DIR", aligned_dir, raising=False)
    monkeypatch.setattr(core_muninn, "TREE_META", aligned_dir / "tree.json", raising=False)

    tree = muninn_tree.init_tree()
    assert isinstance(tree, dict)
    assert "nodes" in tree
    assert (aligned_dir / "tree.json").exists()


def test_cli_init_computes_tree_meta_from_repo_directly(tmp_path):
    """The `muninn init` CLI handler must compute tree_meta DIRECTLY from
    the `repo` argument (not from module-level globals nor from _m), so
    pip-install-e + cwd-mismatch cannot clobber the source repo.

    Specifically the bare `TREE_META.exists()` symbol must NOT appear in the
    init handler — it's the RULE-1-violating legacy global that caused the
    test_e2e_pip_install_from_scratch leak.
    """
    muninn_py = REPO_ROOT / "engine" / "core" / "muninn.py"
    text = muninn_py.read_text(encoding="utf-8")
    idx = text.find('args.command == "init"')
    assert idx >= 0, "init command handler not found"
    init_section = text[idx:idx + 2000]
    # The init handler must compute tree_meta from the repo argument.
    assert 'tree_meta = repo /' in init_section, (
        f"init handler must compute tree_meta directly from repo argument.\n"
        f"Snippet: {init_section[:600]}"
    )
    # The bare legacy reference must be gone.
    bare = init_section.count("TREE_META.exists()")
    assert bare == 0, (
        f"unqualified TREE_META.exists() still present in init handler ({bare} times). "
        f"Compute tree_meta = repo / '.muninn' / 'tree' / 'tree.json' instead."
    )


def test_cli_init_propagates_repo_path_to_package(tmp_path):
    """The init handler must propagate _REPO_PATH to the muninn package
    namespace (`muninn._REPO_PATH = repo`), not only the local module global.
    This ensures _m._REPO_PATH (used downstream by _get_tree_dir / init_tree)
    sees the same value in pip-install-e mode where _engine and the package
    namespaces diverge.
    """
    for path in (REPO_ROOT / "engine" / "core" / "muninn.py",
                 REPO_ROOT / "engine" / "core" / "muninn.py"):
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        idx = text.find('args.command == "init"')
        assert idx >= 0, f"init handler not found in {path.name}"
        section = text[idx:idx + 2500]
        assert "_pkg._REPO_PATH = repo" in section or "muninn._REPO_PATH = repo" in section, (
            f"{path.name}: init handler missing package-level _REPO_PATH propagation. "
            f"In pip-install-e mode this leaks the source repo as the tree target."
        )


def test_mirror_engine_py_also_fixed():
    """The muninn/_engine.py mirror must have the same fix (BUG-091 duplication)."""
    engine_py = REPO_ROOT / "engine" / "core" / "muninn.py"
    if not engine_py.exists():
        pytest.skip("muninn/_engine.py mirror absent")
    text = engine_py.read_text(encoding="utf-8")
    idx = text.find('args.command == "init"')
    assert idx >= 0, "init handler not found in mirror"
    handler = text[idx:idx + 2500]
    assert 'tree_meta = repo /' in handler, (
        "muninn/_engine.py mirror missing the direct tree_meta computation"
    )
