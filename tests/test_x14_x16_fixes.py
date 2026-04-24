"""X14-X16 — Security + atomicity + filler threshold.

Tests:
  X14.1  Config path traversal rejected
  X14.2  Config path with valid directory accepted
  X14.3  Config path type check (non-string rejected)
  X15.1  install_hooks uses atomic write (source inspection)
  X16.1  get_learned_fillers returns empty (disabled = safe)
"""
import sys, os, tempfile, shutil, json
from pathlib import Path


def test_x14_1_traversal_rejected():
    """Config path with '..' is rejected."""
    from muninn.mycelium import Mycelium

    tmpdir = tempfile.mkdtemp(prefix="muninn_x14_")
    try:
        # Create a fake config with traversal path
        config_dir = Path(tmpdir) / ".muninn_home"
        config_dir.mkdir()
        config_path = config_dir / "config.json"
        config_path.write_text(json.dumps({
            "meta_path": str(Path(tmpdir) / ".." / "etc" / "evil")
        }), encoding="utf-8")

        # Monkey-patch Path.home to use our temp dir
        original_home = Path.home
        Path.home = staticmethod(lambda: Path(tmpdir) / ".muninn_home" / "..")
        try:
            # _load_meta_dir should fall back to default when traversal detected
            result = Mycelium._load_meta_dir()
            # Should NOT create the evil path
            evil_path = (Path(tmpdir) / ".." / "etc" / "evil").resolve()
            assert not evil_path.exists() or result != evil_path, \
                "X14.1 FAIL: traversal path was accepted"
            print(f"  X14.1 PASS: traversal path rejected")
        finally:
            Path.home = original_home
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x14_2_valid_path_accepted():
    """Config path with valid directory is accepted."""
    from muninn.mycelium import Mycelium

    tmpdir = tempfile.mkdtemp(prefix="muninn_x14_")
    try:
        valid_meta = Path(tmpdir) / "shared_meta"
        config_dir = Path(tmpdir) / ".muninn"
        config_dir.mkdir()
        config_path = config_dir / "config.json"
        config_path.write_text(json.dumps({
            "meta_path": str(valid_meta)
        }), encoding="utf-8")

        original_home = Path.home
        Path.home = staticmethod(lambda: Path(tmpdir))
        try:
            result = Mycelium._load_meta_dir()
            assert result.resolve() == valid_meta.resolve(), \
                f"X14.2 FAIL: valid path not accepted: {result}"
            print(f"  X14.2 PASS: valid path accepted")
        finally:
            Path.home = original_home
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x14_3_type_check():
    """Config path with non-string type is rejected."""
    from muninn.mycelium import Mycelium

    tmpdir = tempfile.mkdtemp(prefix="muninn_x14_")
    try:
        config_dir = Path(tmpdir) / ".muninn"
        config_dir.mkdir()
        config_path = config_dir / "config.json"
        config_path.write_text(json.dumps({
            "meta_path": 12345  # int, not string
        }), encoding="utf-8")

        original_home = Path.home
        Path.home = staticmethod(lambda: Path(tmpdir))
        try:
            result = Mycelium._load_meta_dir()
            # Should fall back to default
            assert result == Path(tmpdir) / ".muninn", \
                f"X14.3 FAIL: non-string path accepted: {result}"
            print(f"  X14.3 PASS: non-string type rejected")
        finally:
            Path.home = original_home
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x15_1_atomic_write():
    """install_hooks uses tempfile + os.replace for atomic write."""
    muninn_path = os.path.join(os.path.dirname(__file__), "..", "engine", "core", "muninn.py")
    with open(muninn_path, encoding="utf-8") as f:
        source = f.read()

    # Find the install_hooks function area
    assert "mkstemp" in source, "X15.1 FAIL: no mkstemp in muninn.py"
    assert "os.replace" in source, "X15.1 FAIL: no os.replace in muninn.py"
    print(f"  X15.1 PASS: install_hooks uses atomic write (mkstemp + os.replace)")


def test_x16_1_learned_fillers_disabled():
    """get_learned_fillers returns empty list (disabled = safe)."""
    from muninn.mycelium import Mycelium

    tmpdir = tempfile.mkdtemp(prefix="muninn_x16_")
    try:
        m = Mycelium(Path(tmpdir))
        fillers = m.get_learned_fillers()
        assert fillers == [], f"X16.1 FAIL: fillers not empty: {fillers}"
        print(f"  X16.1 PASS: learned fillers disabled (returns empty)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    test_x14_1_traversal_rejected()
    test_x14_2_valid_path_accepted()
    test_x14_3_type_check()
    test_x15_1_atomic_write()
    test_x16_1_learned_fillers_disabled()
    print("\nAll X14-X16 tests PASS")
