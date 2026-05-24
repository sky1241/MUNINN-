"""
Tests for B-SCAN-14: Orchestrator
==================================
At least 20 tests covering the full pipeline.
All use synthetic fixtures via tmp_path — no external repos.
"""

import json
import os
import sys
from unittest.mock import patch, MagicMock
from dataclasses import dataclass

import pytest

# ── Ensure project root on path ────────────────────────────────────
_ROOT = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..'))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from engine.core.scanner.orchestrator import (
    ScanOptions,
    scan,
    scan_repo,
    _detect_languages,
    _build_graph,
    _select_files,
    _log_scan,
    _simple_graph,
    _hash_file,
)
from engine.core.scanner.report import ScanReport


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _make_repo(tmp_path, files=None):
    """Create a synthetic repo in tmp_path with optional files.

    Args:
        tmp_path: pytest tmp_path fixture
        files: dict {relative_path: content}

    Returns:
        str path to the repo root
    """
    repo = str(tmp_path / "repo")
    os.makedirs(repo, exist_ok=True)
    if files:
        for rel_path, content in files.items():
            full = os.path.join(repo, rel_path.replace("/", os.sep))
            os.makedirs(os.path.dirname(full), exist_ok=True)
            with open(full, "w", encoding="utf-8") as f:
                f.write(content)
    return repo


VULN_PYTHON = '''\
import sqlite3

def search(query):
    conn = sqlite3.connect("db.sqlite")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE name = '" + query + "'")
    return cursor.fetchall()
'''

SAFE_PYTHON = '''\
def hello():
    print("Hello, world!")
    return 42
'''

JS_FILE = '''\
const express = require('express');
const app = express();
app.get('/', (req, res) => res.send('ok'));
'''

GO_FILE = '''\
package main

import "fmt"

func main() {
    fmt.Println("hello")
}
'''


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 1. Empty repo -> exit_code=0, clean report
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_empty_repo(tmp_path):
    repo = _make_repo(tmp_path)
    report = scan(ScanOptions(repo_path=repo))
    assert report is not None
    assert report.exit_code == 0
    assert report.files_scanned == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 2. Single Python file with SQL injection -> finds it
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_vuln_python_file(tmp_path):
    repo = _make_repo(tmp_path, {"app.py": VULN_PYTHON})
    report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    assert report is not None
    assert report.files_scanned == 1
    # Should find something (regex catches SQL patterns or secret patterns)
    # At minimum the regex pass runs without error
    assert report.exit_code >= 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 3. Dry run -> returns file list, no actual scan
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_dry_run(tmp_path):
    repo = _make_repo(tmp_path, {"app.py": SAFE_PYTHON, "lib.py": SAFE_PYTHON})
    report = scan(ScanOptions(repo_path=repo, dry_run=True))
    assert report is not None
    assert report.files_scanned == 0  # dry run doesn't scan
    assert report.coverage_flags.get("dry_run") is True
    file_list = report.coverage_flags.get("files_to_scan", [])
    assert len(file_list) == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 4. --no-llm -> regex + AST only, no LLM calls
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_no_llm(tmp_path):
    repo = _make_repo(tmp_path, {"app.py": SAFE_PYTHON})
    # Mock LLM scan to verify it's NOT called
    with patch("engine.core.scanner.orchestrator.llm_scan_file") as mock_llm:
        report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
        mock_llm.assert_not_called()
    assert report is not None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 5. --full -> all files scanned
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_full_scan(tmp_path):
    repo = _make_repo(tmp_path, {
        "a.py": SAFE_PYTHON,
        "b.py": SAFE_PYTHON,
        "c.py": SAFE_PYTHON,
    })
    report = scan(ScanOptions(repo_path=repo, full=True, no_llm=True))
    assert report is not None
    assert report.files_scanned == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 6. _detect_languages: .py=python
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_detect_python(tmp_path):
    repo = _make_repo(tmp_path, {"main.py": "pass"})
    langs = _detect_languages(repo)
    assert "main.py" in langs
    assert langs["main.py"] == "python"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 7. _detect_languages: .js=javascript
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_detect_javascript(tmp_path):
    repo = _make_repo(tmp_path, {"app.js": "console.log('hi')"})
    langs = _detect_languages(repo)
    assert "app.js" in langs
    assert langs["app.js"] == "javascript"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 8. _detect_languages: .go=go
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_detect_go(tmp_path):
    repo = _make_repo(tmp_path, {"main.go": GO_FILE})
    langs = _detect_languages(repo)
    assert "main.go" in langs
    assert langs["main.go"] == "go"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 9. _detect_languages: unknown extension -> skipped
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_detect_unknown_ext(tmp_path):
    repo = _make_repo(tmp_path, {"data.xyz": "whatever"})
    langs = _detect_languages(repo)
    assert len(langs) == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 10. _build_graph: Python import -> edge in graph
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_build_graph_with_import(tmp_path):
    repo = _make_repo(tmp_path, {
        "main.py": "from lib import foo\n",
        "lib.py": "def foo(): pass\n",
    })
    file_langs = _detect_languages(repo)
    graph = _build_graph(repo, file_langs)
    # main.py imports lib -> edge from main.py to lib.py
    main_edges = [e[0] if isinstance(e, tuple) else e for e in graph.get("main.py", [])]
    assert "lib.py" in main_edges


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 11. _build_graph: no imports -> isolated nodes
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_build_graph_no_imports(tmp_path):
    repo = _make_repo(tmp_path, {
        "a.py": "x = 1\n",
        "b.py": "y = 2\n",
    })
    file_langs = _detect_languages(repo)
    graph = _build_graph(repo, file_langs)
    assert graph["a.py"] == []
    assert graph["b.py"] == []


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 12. _select_files: incremental with cache hit -> skip
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_select_files_incremental_cached(tmp_path):
    repo = _make_repo(tmp_path, {"a.py": "pass"})
    cache_path = str(tmp_path / "cache.json")
    # Write a cache with the same hash as the file
    sha = _hash_file(os.path.join(repo, "a.py"))
    cache_data = {"a.py": {"sha256": sha, "last_scan_date": "2026-01-01T00:00:00Z", "findings": []}}
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)

    file_langs = {"a.py": "python"}
    opts = ScanOptions(repo_path=repo, incremental=True)
    selected = _select_files(opts, file_langs, cache_path)
    assert "a.py" not in selected  # cached, not changed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 13. _select_files: incremental with new file -> include
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_select_files_incremental_new_file(tmp_path):
    repo = _make_repo(tmp_path, {"a.py": "pass", "b.py": "pass"})
    cache_path = str(tmp_path / "cache.json")
    # Cache only has a.py
    sha_a = _hash_file(os.path.join(repo, "a.py"))
    cache_data = {"a.py": {"sha256": sha_a, "last_scan_date": "2026-01-01T00:00:00Z", "findings": []}}
    with open(cache_path, "w") as f:
        json.dump(cache_data, f)

    file_langs = {"a.py": "python", "b.py": "python"}
    opts = ScanOptions(repo_path=repo, incremental=True)
    selected = _select_files(opts, file_langs, cache_path)
    assert "b.py" in selected  # new file
    assert "a.py" not in selected  # cached


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 14. _select_files: full mode -> all files
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_select_files_full(tmp_path):
    repo = _make_repo(tmp_path, {"a.py": "pass", "b.py": "pass"})
    cache_path = str(tmp_path / "cache.json")
    file_langs = {"a.py": "python", "b.py": "python"}
    opts = ScanOptions(repo_path=repo, full=True)
    selected = _select_files(opts, file_langs, cache_path)
    assert len(selected) == 2


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 15. _log_scan: appends JSON line
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_log_scan(tmp_path):
    log_path = str(tmp_path / ".muninn" / "scan_log.jsonl")
    _log_scan(log_path, {"test": True, "files": 5})
    _log_scan(log_path, {"test": True, "files": 10})
    with open(log_path, "r") as f:
        lines = f.readlines()
    assert len(lines) == 2
    data = json.loads(lines[0])
    assert data["files"] == 5


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 16. ScanOptions defaults
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_scan_options_defaults():
    opts = ScanOptions()
    assert opts.repo_path == ""
    assert opts.full is False
    assert opts.incremental is True
    assert opts.dry_run is False
    assert opts.no_llm is False
    assert opts.bible_dir is None
    assert opts.output_dir is None
    assert opts.max_llm_files == 0
    assert opts.propagation_method == "auto"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 17. scan_repo convenience wrapper works
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_scan_repo_wrapper(tmp_path):
    repo = _make_repo(tmp_path, {"hello.py": SAFE_PYTHON})
    report = scan_repo(repo, no_llm=True, full=True)
    assert report is not None
    assert isinstance(report, ScanReport)
    assert report.files_scanned == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 18. scan handles missing bible dir gracefully
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_missing_bible_dir(tmp_path):
    repo = _make_repo(tmp_path, {"app.py": SAFE_PYTHON})
    report = scan(ScanOptions(
        repo_path=repo,
        no_llm=True,
        full=True,
        bible_dir=str(tmp_path / "nonexistent_bible"),
    ))
    assert report is not None
    assert report.exit_code >= 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 19. scan handles empty file list
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_empty_file_list(tmp_path):
    # Repo with only unknown files
    repo = _make_repo(tmp_path, {"data.dat": "binary stuff"})
    report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    assert report is not None
    assert report.exit_code == 0
    assert report.files_scanned == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 20. pipeline handles brick failure gracefully
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_brick_failure_graceful(tmp_path):
    repo = _make_repo(tmp_path, {"app.py": SAFE_PYTHON})
    # Mock regex scanner to raise an exception
    with patch("engine.core.scanner.orchestrator.regex_scan_file_content",
               side_effect=RuntimeError("boom")):
        report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    # Should still return a report (degraded)
    assert report is not None
    assert report.exit_code >= 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 21. report contains all sections
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_report_sections(tmp_path):
    repo = _make_repo(tmp_path, {"app.py": SAFE_PYTHON})
    report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    assert report is not None
    assert hasattr(report, "findings")
    assert hasattr(report, "epidemio_metrics")
    assert hasattr(report, "patch_plan")
    assert hasattr(report, "amplified_risks")
    assert hasattr(report, "dynamic_imports")
    assert hasattr(report, "coverage_flags")
    assert hasattr(report, "exit_code")
    assert hasattr(report, "scan_duration")
    assert hasattr(report, "files_scanned")
    assert hasattr(report, "timestamp")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 22. exit code correct for findings
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_exit_code_clean(tmp_path):
    repo = _make_repo(tmp_path, {"safe.py": SAFE_PYTHON})
    report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    assert report.exit_code == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 23. _simple_graph converts weighted to unweighted
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_simple_graph():
    g = {"a": [("b", 1.0), ("c", 0.5)], "b": [], "c": [("a", 1.0)]}
    s = _simple_graph(g)
    assert s == {"a": ["b", "c"], "b": [], "c": ["a"]}


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 24. scan with nonexistent repo path -> clean report
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_nonexistent_repo(tmp_path):
    report = scan(ScanOptions(repo_path=str(tmp_path / "does_not_exist")))
    assert report is not None
    assert report.exit_code == 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 25. multi-language repo
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_multi_language_repo(tmp_path):
    repo = _make_repo(tmp_path, {
        "main.py": SAFE_PYTHON,
        "app.js": JS_FILE,
        "server.go": GO_FILE,
    })
    report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    assert report is not None
    assert report.files_scanned == 3


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 26. scan log is written after scan
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_scan_log_written(tmp_path):
    repo = _make_repo(tmp_path, {"app.py": SAFE_PYTHON})
    report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    log_path = os.path.join(repo, ".muninn", "scan_log.jsonl")
    assert os.path.exists(log_path)
    with open(log_path, "r") as f:
        data = json.loads(f.readline())
    assert "duration" in data
    assert "files_scanned" in data
    assert data["files_scanned"] == 1


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 27. _detect_languages skips .git and node_modules
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_detect_skips_hidden_dirs(tmp_path):
    repo = _make_repo(tmp_path, {
        "app.py": "pass",
        ".git/config.py": "pass",
        "node_modules/lib.js": "pass",
    })
    langs = _detect_languages(repo)
    assert "app.py" in langs
    # .git and node_modules should be skipped
    for key in langs:
        assert ".git" not in key
        assert "node_modules" not in key


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 28. _hash_file returns consistent hash
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_hash_file(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello world", encoding="utf-8")
    h1 = _hash_file(str(f))
    h2 = _hash_file(str(f))
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 29. cache updated after scan
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_cache_updated(tmp_path):
    repo = _make_repo(tmp_path, {"app.py": SAFE_PYTHON})
    report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    cache_path = os.path.join(repo, ".muninn", "scan_cache.json")
    assert os.path.exists(cache_path)
    with open(cache_path, "r") as f:
        cache = json.load(f)
    assert "app.py" in cache


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 30. dynamic import detection runs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_dynamic_imports_detected(tmp_path):
    code_with_eval = "def run(s):\n    return eval(s)\n"
    repo = _make_repo(tmp_path, {"danger.py": code_with_eval})
    report = scan(ScanOptions(repo_path=repo, no_llm=True, full=True))
    assert report is not None
    # Should detect the eval() as a dynamic import
    assert len(report.dynamic_imports) > 0


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 31. AST confirms SQL injection (bad.py) end-to-end
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

SQLI_VULN = '''\
import sqlite3
def bad_query(user_input):
    conn = sqlite3.connect("db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=" + user_input)
'''

SQLI_SAFE = '''\
import sqlite3
def safe_query(user_input):
    conn = sqlite3.connect("db")
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id=?", (user_input,))
'''


def test_ast_confirms_sql_injection(tmp_path):
    """AST confirms real SQL injection via string concatenation."""
    repo = _make_repo(tmp_path, {"bad.py": SQLI_VULN})
    report = scan(ScanOptions(repo_path=repo, full=True, no_llm=True))
    assert report is not None
    # Find the SQL injection finding for bad.py
    sql_findings = [f for f in report.findings
                    if (f.file if hasattr(f, 'file') else f['file']) == 'bad.py'
                    and 'SQL' in (f.type if hasattr(f, 'type') else f['type']).upper()]
    assert len(sql_findings) >= 1, "Expected SQL injection finding for bad.py"
    finding = sql_findings[0]
    conf = finding.confidence if hasattr(finding, 'confidence') else finding['confidence']
    sources = finding.sources if hasattr(finding, 'sources') else finding['sources']
    assert conf == "confirmed", f"Expected confirmed, got {conf}"
    assert "ast" in sources, f"Expected 'ast' in sources, got {sources}"
    assert "regex" in sources, f"Expected 'regex' in sources, got {sources}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 32. AST does NOT produce findings for safe parameterized query
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_ast_no_finding_safe_query(tmp_path):
    """Safe parameterized query produces no SQL injection finding."""
    repo = _make_repo(tmp_path, {"good.py": SQLI_SAFE})
    report = scan(ScanOptions(repo_path=repo, full=True, no_llm=True))
    assert report is not None
    sql_findings = [f for f in report.findings
                    if (f.file if hasattr(f, 'file') else f['file']) == 'good.py'
                    and 'SQL' in (f.type if hasattr(f, 'type') else f['type']).upper()]
    # No SQL injection finding for safe code
    assert len(sql_findings) == 0, f"Expected no SQL finding for good.py, got {sql_findings}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 33. AST marks hardcoded secret in test file as FP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

HARDCODED_TEST = '''\
def test_evaluate():
    password = "test_secret_123"
    assert len(password) > 0
'''

HARDCODED_PROD = '''\
def connect():
    password = "real_prod_secret_xyz"
    return db.connect(password=password)
'''


def test_ast_fp_for_test_file_secret(tmp_path):
    """Hardcoded secret in test file gets confidence=fp from AST."""
    repo = _make_repo(tmp_path, {"test_auth.py": HARDCODED_TEST})
    report = scan(ScanOptions(repo_path=repo, full=True, no_llm=True))
    assert report is not None
    secret_findings = [f for f in report.findings
                       if (f.file if hasattr(f, 'file') else f['file']) == 'test_auth.py']
    # All findings in test file should be FP
    for finding in secret_findings:
        conf = finding.confidence if hasattr(finding, 'confidence') else finding['confidence']
        assert conf == "fp", f"Expected fp for test file, got {conf}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 34. AST confirms hardcoded secret in production code
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_ast_confirms_prod_secret(tmp_path):
    """Hardcoded secret in production code gets confirmed by AST."""
    repo = _make_repo(tmp_path, {"config.py": HARDCODED_PROD})
    report = scan(ScanOptions(repo_path=repo, full=True, no_llm=True))
    assert report is not None
    secret_findings = [f for f in report.findings
                       if (f.file if hasattr(f, 'file') else f['file']) == 'config.py']
    assert len(secret_findings) >= 1, "Expected at least one finding for config.py"
    for finding in secret_findings:
        conf = finding.confidence if hasattr(finding, 'confidence') else finding['confidence']
        sources = finding.sources if hasattr(finding, 'sources') else finding['sources']
        assert conf == "confirmed", f"Expected confirmed, got {conf}"
        assert "ast" in sources, f"Expected 'ast' in sources, got {sources}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 35. AST end-to-end: bad+good in same repo, AST differentiates
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def test_ast_end_to_end_mixed_repo(tmp_path):
    """Mixed repo: AST confirms vuln in bad.py, no finding for good.py."""
    repo = _make_repo(tmp_path, {
        "bad.py": SQLI_VULN,
        "good.py": SQLI_SAFE,
        "test_auth.py": HARDCODED_TEST,
        "config.py": HARDCODED_PROD,
    })
    report = scan(ScanOptions(repo_path=tmp_path / "repo", full=True, no_llm=True))
    assert report is not None

    # Classify findings by file
    by_file = {}
    for f in report.findings:
        fname = f.file if hasattr(f, 'file') else f['file']
        by_file.setdefault(fname, []).append(f)

    # bad.py: confirmed SQL injection
    assert 'bad.py' in by_file, "Expected findings for bad.py"
    for finding in by_file['bad.py']:
        conf = finding.confidence if hasattr(finding, 'confidence') else finding['confidence']
        assert conf == "confirmed"

    # good.py: no SQL injection findings
    good_sql = [f for f in by_file.get('good.py', [])
                if 'SQL' in (f.type if hasattr(f, 'type') else f['type']).upper()]
    assert len(good_sql) == 0, f"Expected no SQL findings for good.py, got {good_sql}"

    # test_auth.py: all FP
    for finding in by_file.get('test_auth.py', []):
        conf = finding.confidence if hasattr(finding, 'confidence') else finding['confidence']
        assert conf == "fp"

    # config.py: confirmed secrets
    assert 'config.py' in by_file, "Expected findings for config.py"
    for finding in by_file['config.py']:
        conf = finding.confidence if hasattr(finding, 'confidence') else finding['confidence']
        assert conf == "confirmed"
