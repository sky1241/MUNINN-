"""Doctor — pre-flight environment check.

Tests:
  D1.1  Returns ok/fail dict with correct keys
  D1.2  Detects missing .muninn/ directory (fail count > 0)
  D1.3  Real repo: all critical checks pass
  D1.4  CLI: command runs without crash
"""
import sys, os, tempfile, subprocess
MUNINN_PY = os.path.join(os.path.dirname(__file__), "..", "engine", "core", "muninn.py")


def test_d1_1_returns_dict():
    """doctor() returns dict with ok and fail keys"""
    from pathlib import Path
    import muninn
    muninn._REPO_PATH = Path(tempfile.mkdtemp())
    result = muninn.doctor()
    assert isinstance(result, dict), f"D1.1 FAIL: expected dict, got {type(result)}"
    assert "ok" in result, "D1.1 FAIL: missing 'ok' key"
    assert "fail" in result, "D1.1 FAIL: missing 'fail' key"
    assert result["ok"] >= 0, "D1.1 FAIL: ok count negative"
    print(f"  D1.1 PASS: returns dict with ok={result['ok']}, fail={result['fail']}")


def test_d1_2_missing_muninn_dir():
    """Missing .muninn/ triggers at least 1 fail"""
    from pathlib import Path
    import muninn
    muninn._REPO_PATH = Path(tempfile.mkdtemp())  # Empty dir, no .muninn/
    result = muninn.doctor()
    assert result["fail"] >= 1, f"D1.2 FAIL: expected fail >= 1, got {result['fail']}"
    print(f"  D1.2 PASS: missing .muninn/ detected (fail={result['fail']})")


def test_d1_3_real_repo():
    """Real MUNINN- repo: all critical checks pass"""
    from pathlib import Path
    import muninn
    repo = Path(__file__).resolve().parent.parent
    if not (repo / ".muninn").exists():
        print("  D1.3 SKIP: not running from MUNINN- repo")
        return
    muninn._REPO_PATH = repo
    muninn._refresh_tree_paths()
    result = muninn.doctor()
    assert result["fail"] == 0, f"D1.3 FAIL: expected 0 fails, got {result['fail']}"
    assert result["ok"] >= 8, f"D1.3 FAIL: expected >= 8 OKs, got {result['ok']}"
    print(f"  D1.3 PASS: real repo all green ({result['ok']} checks)")


def test_d1_4_cli():
    """CLI: muninn doctor runs without crash"""
    result = subprocess.run(
        [sys.executable, MUNINN_PY, "doctor"],
        capture_output=True, text=True, timeout=30,
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    assert result.returncode == 0, f"D1.4 FAIL: exit code {result.returncode}\n{result.stderr}"
    assert "MUNINN DOCTOR" in result.stdout, f"D1.4 FAIL: missing header in output"
    print(f"  D1.4 PASS: CLI runs clean (exit 0)")


if __name__ == "__main__":
    print("=== DOCTOR TESTS ===")
    test_d1_1_returns_dict()
    test_d1_2_missing_muninn_dir()
    test_d1_3_real_repo()
    test_d1_4_cli()
    print("\n  ALL PASS")
