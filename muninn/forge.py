#!/usr/bin/env python3
"""
FORGE — Universal Debug & Regression Shield
Drop into any repo. Run before and after every session.

Usage:
    python forge.py                    # Run all tests + report
    python forge.py --init             # Init BUGS.md + tests/ in current repo
    python forge.py --add "bug desc"   # Add a bug to BUGS.md
    python forge.py --close BUG-003    # Mark a bug as fixed
    python forge.py --watch            # Run tests on file change (loop)
    python forge.py --diff             # Compare current report vs last saved
    python forge.py --baseline         # Save current test results as baseline
    python forge.py --flaky [N]        # Run tests N times (default 5), find flaky ones
    python forge.py --heatmap          # Show failure heat map (Pareto — which tests fail most)
    python forge.py --bisect TEST      # Git bisect to find which commit broke TEST
    python forge.py --fast             # Only run tests for files changed since last commit
    python forge.py --snapshot CMD     # Capture command output as golden file
    python forge.py --snapshot-check   # Verify all snapshots still match
    python forge.py --predict          # Predict defect-prone files from git history
    python forge.py --minimize TEST IN # Delta-debug: find minimal input that fails TEST
    python forge.py --gen-props MOD    # Generate Hypothesis property tests for module
    python forge.py --mutate [FILE]    # Mutation testing via mutmut (test your tests)
    python forge.py --locate           # Ochiai SBFL: locate suspicious lines from failures
    python forge.py --anomaly          # Unified anomaly detection across all metrics
    python forge.py --robustness       # Bio-robustness: Q-modularity of import graph
    python forge.py --full-cycle       # Complete pipeline: predict→anomaly→test→locate→robustness

Works with: pytest, unittest, any test_*.py files.
Zero config. Zero dependencies beyond Python stdlib + pytest.
Optional deps: hypothesis (--gen-props), mutmut (--mutate), coverage+pytest-cov (--locate).
Carmack moves: wavelet churn (Hassan 2009), Kalman adaptive weights (Kalman 1960),
               anomaly detection (Z-score/IQR), bio-robustness (Newman 2006 Q-modularity).
"""

import sys
import os
import re
import json
import time
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime
from collections import Counter
import ast
import math
import textwrap
import shlex

def _safe_path(filepath) -> str:
    """Sanitize path for display — never show absolute paths."""
    p = Path(filepath)
    parts = p.parts
    if len(parts) <= 3:
        return str(p.name)
    return str(Path(*parts[-3:]))


# === CONFIG ===
BUGS_FILE = "BUGS.md"
FORGE_DIR = ".forge"
BASELINE_FILE = f"{FORGE_DIR}/baseline.json"
REPORT_FILE = f"{FORGE_DIR}/last_report.json"
FORGE_LOG = f"{FORGE_DIR}/forge_log.txt"
FLAKY_FILE = f"{FORGE_DIR}/flaky.json"
HEATMAP_FILE = f"{FORGE_DIR}/heatmap.json"
SNAPSHOT_DIR = f"{FORGE_DIR}/snapshots"
MUTATION_THRESHOLD = 80
PREDICT_WEIGHTS = {"churn": 0.20, "freq": 0.20, "wavelet": 0.15,
                   "authors": 0.10, "bugfix": 0.15, "loc": 0.05, "recency": 0.15}
OCHIAI_TOP_N = 10
MINIMIZE_MAX_ITER = 100
KALMAN_STATE_FILE = f"{FORGE_DIR}/kalman_state.json"
ANOMALY_THRESHOLD = 2.0  # Z-score threshold for anomaly detection


def _pytest_has_failures(output):
    """Check if pytest output indicates failures, using the summary line regex.
    Safe against test names containing 'failed' or 'error'."""
    # pytest summary: "1 failed", "3 error" at END of output
    if re.search(r"\d+ failed", output):
        return True
    if re.search(r"\d+ error", output):
        return True
    # Fallback: check exit status markers
    if "FAILURES" in output or "ERRORS" in output:
        return True
    return False


def _check_dep(name, pip_name=None):
    """Try to import optional dependency, return module or None."""
    try:
        return __import__(name)
    except ImportError:
        pip_name = pip_name or name
        print(f"  {name} not installed. Install with: pip install {pip_name}")
        return None


def _run_git(root, *args):
    """Run a git command and return stdout."""
    try:
        r = subprocess.run(["git"] + list(args), capture_output=True, text=True,
                          cwd=str(root), encoding="utf-8", errors="replace", timeout=30)
        return r.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return ""


def find_repo_root():
    """Walk up to find .git directory. Also check script's own location."""
    # First try CWD
    p = Path.cwd()
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    # Fallback: script location
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / ".git").exists():
            return p
        p = p.parent
    return Path.cwd()


def find_tests(root):
    """Find all test files in the repo."""
    tests = []
    for pattern in ["tests/test_*.py", "test_*.py", "tests/**/test_*.py", "**/test_*.py"]:
        tests.extend(root.glob(pattern))
    # Exclude .forge, __pycache__, .git, node_modules
    tests = [t for t in tests if not any(x in str(t) for x in [".forge", "__pycache__", ".git", "node_modules"])]
    return sorted(set(tests))


def run_tests(root, verbose=False):
    """Run pytest and capture structured results."""
    test_files = find_tests(root)
    if not test_files:
        # Fallback: check if CWD has tests
        test_files = find_tests(Path.cwd())
    if not test_files:
        return {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0, "details": [], "duration": 0}

    start = time.time()
    # Pass discovered test files directly to pytest for universal discovery
    test_paths = [str(f) for f in test_files]
    cmd = [
        sys.executable, "-m", "pytest",
    ] + test_paths + [
        "-v", "--tb=short", "-q",
        "--no-header",
    ]

    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(root),
            timeout=300, encoding="utf-8", errors="replace"
        )
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        return {"total": 0, "passed": 0, "failed": 0, "errors": 0, "skipped": 0,
                "details": [{"test": "TIMEOUT", "status": "ERROR", "msg": "Tests exceeded 5min"}],
                "duration": 300}

    duration = time.time() - start

    # Parse results — try summary line first (e.g. "336 passed, 2 failed")
    summary = re.search(r"(\d+) passed", output)
    summary_f = re.search(r"(\d+) failed", output)
    summary_e = re.search(r"(\d+) error", output)
    summary_s = re.search(r"(\d+) skipped", output)

    passed = int(summary.group(1)) if summary else len(re.findall(r" PASSED", output))
    failed = int(summary_f.group(1)) if summary_f else len(re.findall(r" FAILED", output))
    errors = int(summary_e.group(1)) if summary_e else len(re.findall(r" ERROR", output))
    skipped = int(summary_s.group(1)) if summary_s else len(re.findall(r" SKIPPED", output))

    # Extract failure details
    details = []
    for match in re.finditer(r"(FAILED|ERROR)\s+(.*?)(?:\s+-\s+(.*))?$", output, re.MULTILINE):
        details.append({
            "test": match.group(2).strip(),
            "status": match.group(1),
            "msg": (match.group(3) or "").strip()
        })

    return {
        "total": passed + failed + errors + skipped,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "skipped": skipped,
        "details": details,
        "duration": round(duration, 1),
        "raw_output": output if verbose else None
    }


def load_json(path):
    """Load JSON file or return None."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def save_json(path, data):
    """Save JSON file."""
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def print_report(results, baseline=None):
    """Print formatted test report."""
    total = results["total"]
    passed = results["passed"]
    failed = results["failed"]
    errors = results["errors"]
    duration = results["duration"]

    if total == 0:
        print("\n  NO TESTS FOUND. Run: forge.py --init\n")
        return

    # Header
    status = "PASS" if failed == 0 and errors == 0 else "FAIL"
    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  FORGE REPORT — {status}")
    print(f"{bar}")
    print(f"  Tests:    {total}")
    print(f"  Passed:   {passed}")
    print(f"  Failed:   {failed}")
    print(f"  Errors:   {errors}")
    print(f"  Skipped:  {results['skipped']}")
    print(f"  Duration: {duration}s")

    # Comparison with baseline
    if baseline:
        bp = baseline.get("passed", 0)
        bf = baseline.get("failed", 0)
        delta_p = passed - bp
        delta_f = failed - bf
        print(f"\n  vs baseline:")
        print(f"    Passed: {bp} -> {passed} ({'+' if delta_p >= 0 else ''}{delta_p})")
        print(f"    Failed: {bf} -> {failed} ({'+' if delta_f >= 0 else ''}{delta_f})")
        if delta_f > 0:
            print(f"\n  *** REGRESSION: {delta_f} new failure(s) ***")
        elif delta_p > bp and failed == 0:
            print(f"\n  +++ PROGRESS: {delta_p} more passing +++")

    # Failure details
    if results["details"]:
        print(f"\n  FAILURES:")
        for d in results["details"]:
            print(f"    [{d['status']}] {d['test']}")
            if d.get("msg"):
                print(f"            {d['msg']}")

    print(f"{bar}\n")


def init_repo(root):
    """Initialize BUGS.md and .forge/ in a repo."""
    forge_dir = root / FORGE_DIR
    forge_dir.mkdir(exist_ok=True)

    # .gitignore for .forge/
    gitignore = forge_dir / ".gitignore"
    if not gitignore.exists():
        gitignore.write_text("*\n")

    # BUGS.md
    bugs_path = root / BUGS_FILE
    if not bugs_path.exists():
        bugs_path.write_text(f"""# BUGS — {root.name}

> Format: each bug has an ID, status, symptom, root cause, fix, and test.
> This file is READ BY CLAUDE AT BOOT. Keep it accurate.

<!-- TEMPLATE
## BUG-XXX: [short description]
- **Status**: OPEN / FIXED / WONTFIX
- **Symptom**: what happens
- **Root cause**: WHY it happens (not just where)
- **Fix**: what was done (commit hash if fixed)
- **Test**: which test covers this (file:test_name)
- **Regression**: did the fix break anything else?
-->

""", encoding="utf-8")
        print(f"  Created {BUGS_FILE}")

    # tests/ dir
    tests_dir = root / "tests"
    if not tests_dir.exists():
        tests_dir.mkdir()
        (tests_dir / "__init__.py").write_text("")
        print(f"  Created tests/")

    print(f"  Forge initialized in {root.name}")


def add_bug(root, description):
    """Add a new bug to BUGS.md."""
    bugs_path = root / BUGS_FILE
    if not bugs_path.exists():
        init_repo(root)

    content = bugs_path.read_text(encoding="utf-8")

    # Find next bug number
    existing = re.findall(r"BUG-(\d+)", content)
    next_num = max([int(n) for n in existing], default=0) + 1
    bug_id = f"BUG-{next_num:03d}"

    entry = f"""
## {bug_id}: {description}
- **Status**: OPEN
- **Date**: {datetime.now().strftime('%Y-%m-%d %H:%M')}
- **Symptom**: [a remplir]
- **Root cause**: [a remplir]
- **Fix**: [pending]
- **Test**: [a ecrire]
- **Regression**: [a verifier]
"""
    bugs_path.write_text(content + entry, encoding="utf-8")
    print(f"  Added {bug_id}: {description}")
    return bug_id


def close_bug(root, bug_id):
    """Mark a bug as FIXED in BUGS.md."""
    bugs_path = root / BUGS_FILE
    if not bugs_path.exists():
        print(f"  No {BUGS_FILE} found")
        return

    content = bugs_path.read_text(encoding="utf-8")
    pattern = f"(## {bug_id}:.*?\\n- \\*\\*Status\\*\\*: )OPEN"
    new_content = re.sub(pattern, f"\\1FIXED ({datetime.now().strftime('%Y-%m-%d')})", content)

    if new_content == content:
        print(f"  {bug_id} not found or already closed")
    else:
        bugs_path.write_text(new_content, encoding="utf-8")
        print(f"  {bug_id} marked FIXED")


def log_run(root, results):
    """Append to forge log."""
    log_path = root / FORGE_LOG
    os.makedirs(os.path.dirname(str(log_path)) or ".", exist_ok=True)
    entry = {
        "date": datetime.now().isoformat(),
        "passed": results["passed"],
        "failed": results["failed"],
        "errors": results["errors"],
        "total": results["total"],
        "duration": results["duration"]
    }
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")


# === FLAKY TEST DETECTION ===
def detect_flaky(root, runs=5):
    """Run tests N times, find tests that flip between pass/fail.
    Flaky tests are the #1 trust killer in CI — Luo et al. 2014."""
    print(f"  Running tests {runs} times to detect flaky tests...")
    all_failures = []
    for i in range(runs):
        print(f"    Run {i+1}/{runs}...", end=" ", flush=True)
        results = run_tests(root)
        failed_names = {d["test"] for d in results["details"]}
        all_failures.append(failed_names)
        status = f"{results['passed']}P/{results['failed']}F"
        print(status)

    # A test is flaky if it fails in SOME runs but not ALL
    all_tests_that_failed = set()
    for s in all_failures:
        all_tests_that_failed |= s

    flaky = []
    for test in sorted(all_tests_that_failed):
        fail_count = sum(1 for s in all_failures if test in s)
        if 0 < fail_count < runs:
            flaky.append({"test": test, "fail_rate": f"{fail_count}/{runs}",
                          "detected": datetime.now().isoformat()})

    # Save
    flaky_path = str(root / FLAKY_FILE)
    existing = load_json(flaky_path) or []
    known = {f["test"] for f in existing}
    for f in flaky:
        if f["test"] not in known:
            existing.append(f)
    save_json(flaky_path, existing)

    # Report
    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  FLAKY DETECTION — {runs} runs")
    print(f"{bar}")
    if flaky:
        print(f"  Found {len(flaky)} flaky test(s):")
        for f in flaky:
            print(f"    {f['test']}  ({f['fail_rate']} failures)")
        # AXE 6: classify flaky tests
        _print_flaky_classification(flaky, root)
        print(f"\n  Saved to {FLAKY_FILE}")
    else:
        always_fail = [t for t in all_tests_that_failed
                       if all(t in s for s in all_failures)]
        if always_fail:
            print(f"  No flaky tests. {len(always_fail)} consistent failure(s).")
        else:
            print(f"  All tests stable across {runs} runs.")
    print(f"{bar}\n")


# === FAILURE HEAT MAP (Pareto) ===
def show_heatmap(root):
    """Analyze forge log to find which tests fail most often.
    Pareto principle: 20% of tests cause 80% of failures — Kaner 2003."""
    log_path = root / FORGE_LOG
    if not log_path.exists():
        print("  No forge log yet. Run tests first.")
        return

    # Also check all saved reports for detail
    report_dir = root / FORGE_DIR
    failure_counts = Counter()
    total_runs = 0

    # Parse log for run counts
    with open(log_path, "r", encoding="utf-8") as f:
        for line in f:
            try:
                entry = json.loads(line.strip())
                total_runs += 1
            except json.JSONDecodeError:
                continue

    # Parse all saved details (from flaky runs + last report)
    for jfile in report_dir.glob("*.json"):
        data = load_json(str(jfile))
        if not data:
            continue
        if isinstance(data, dict) and "details" in data:
            for d in data["details"]:
                if d.get("status") in ("FAILED", "ERROR"):
                    failure_counts[d["test"]] += 1
        elif isinstance(data, list):
            # flaky.json format
            for entry in data:
                if "test" in entry:
                    failure_counts[entry["test"]] += 1

    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  FAILURE HEAT MAP — {total_runs} runs logged")
    print(f"{bar}")
    if not failure_counts:
        print("  No failures recorded yet.")
    else:
        total_failures = sum(failure_counts.values())
        cumulative = 0
        for i, (test, count) in enumerate(failure_counts.most_common(20)):
            cumulative += count
            pct = cumulative / total_failures * 100
            heat = "#" * min(count, 30)
            print(f"  {count:3d}x  {test[:60]}")
            print(f"       {heat}  ({pct:.0f}% cumulative)")
        if len(failure_counts) > 20:
            print(f"  ... and {len(failure_counts) - 20} more")
        # Pareto check
        top20pct = max(1, len(failure_counts) // 5)
        top_failures = sum(c for _, c in failure_counts.most_common(top20pct))
        if total_failures > 0:
            pareto = top_failures / total_failures * 100
            print(f"\n  Pareto: top {top20pct} test(s) = {pareto:.0f}% of all failures")
    print(f"{bar}\n")


# === GIT BISECT AUTOMATION ===
def bisect_test(root, test_name):
    """Auto git-bisect to find which commit broke a specific test.
    Zeller 1999 — Delta Debugging + binary search on commits."""
    # Verify test exists and currently fails
    print(f"  Verifying {test_name} currently fails...")
    cmd_test = [sys.executable, "-m", "pytest", "-x", "-q", "--tb=line",
                "--no-header", "-k", test_name]
    result = subprocess.run(cmd_test, capture_output=True, text=True,
                           cwd=str(root), encoding="utf-8", errors="replace")
    if not _pytest_has_failures(result.stdout):
        print(f"  {test_name} is not currently failing. Nothing to bisect.")
        return

    # Find last known good (baseline commit or 20 commits back)
    try:
        log = subprocess.run(["git", "log", "--oneline", "-20"],
                            capture_output=True, text=True, cwd=str(root))
        commits = [l.split()[0] for l in log.stdout.strip().split("\n") if l.strip() and l.split()]
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        print(f"  Git not available or not a git repo: {e}")
        return

    if len(commits) < 2:
        print("  Not enough commits to bisect.")
        return

    print(f"  Bisecting across {len(commits)} commits...")
    # Binary search
    good_idx = len(commits) - 1
    bad_idx = 0

    while good_idx - bad_idx > 1:
        mid = (good_idx + bad_idx) // 2
        commit = commits[mid]
        print(f"    Testing commit {commit}...", end=" ", flush=True)

        # Stash, checkout, test, come back
        subprocess.run(["git", "stash", "--quiet"], cwd=str(root),
                       capture_output=True)
        subprocess.run(["git", "checkout", commit, "--quiet"], cwd=str(root),
                       capture_output=True)

        try:
            r = subprocess.run(cmd_test, capture_output=True, text=True,
                              cwd=str(root), encoding="utf-8", errors="replace",
                              timeout=120)
            is_bad = _pytest_has_failures(r.stdout)
        except subprocess.TimeoutExpired:
            print("TIMEOUT (treating as FAIL)")
            is_bad = True
        print("FAIL" if is_bad else "PASS")

        if is_bad:
            bad_idx = mid
        else:
            good_idx = mid

    # Return to original — ALWAYS runs even if loop exits via exception
    checkout_result = subprocess.run(["git", "checkout", "-", "--quiet"], cwd=str(root),
                                    capture_output=True)
    if checkout_result.returncode != 0:
        print(f"  WARNING: git checkout failed (rc={checkout_result.returncode}), working tree may be detached")
    stash_result = subprocess.run(["git", "stash", "pop", "--quiet"], cwd=str(root),
                                 capture_output=True)
    if stash_result.returncode != 0:
        print(f"  WARNING: git stash pop failed — your changes are still in stash. Run 'git stash pop' manually.")

    bad_commit = commits[bad_idx]
    # Get commit details
    detail = subprocess.run(["git", "log", "--oneline", "-1", bad_commit],
                           capture_output=True, text=True, cwd=str(root))

    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  BISECT RESULT")
    print(f"{bar}")
    print(f"  First bad commit: {detail.stdout.strip()}")
    print(f"  Test: {test_name}")
    print(f"  Checked {len(commits)} commits in {int(round(len(commits)**0.5))+1} steps")
    print(f"{bar}\n")


# === TEST IMPACT ANALYSIS (--fast) ===
def get_changed_files(root):
    """Get Python files changed since last commit."""
    try:
        # Staged + unstaged changes
        r1 = subprocess.run(["git", "diff", "--name-only", "HEAD"],
                           capture_output=True, text=True, cwd=str(root))
        r2 = subprocess.run(["git", "diff", "--name-only", "--cached"],
                           capture_output=True, text=True, cwd=str(root))
        r3 = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"],
                           capture_output=True, text=True, cwd=str(root))
        files = set()
        for r in [r1, r2, r3]:
            for f in r.stdout.strip().split("\n"):
                if f.strip().endswith(".py"):
                    files.add(f.strip())
        return files
    except (subprocess.SubprocessError, FileNotFoundError, OSError) as e:
        print(f"  Warning: could not get changed files from git: {e}")
        return set()


def _build_import_graph(root):
    """Build a module dependency graph via AST. Returns {module_name: set(imported_modules)}.
    Reuses the same AST logic as measure_robustness() (Newman 2006)."""
    tracked = _run_git(root, "ls-files", "*.py")
    if not tracked:
        return {}, {}
    files = [f for f in tracked.split("\n") if f.strip()]
    known_modules = {Path(f).stem for f in files}

    # graph: module -> set of modules it imports
    graph = {}
    # reverse: module -> set of modules that import it
    reverse = {}
    for mod in known_modules:
        graph[mod] = set()
        reverse[mod] = set()

    for f in files:
        p = root / f
        if not p.exists():
            continue
        mod_name = Path(f).stem
        try:
            source = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name.split(".")[0]
                    if target in known_modules:
                        graph.setdefault(mod_name, set()).add(target)
                        reverse.setdefault(target, set()).add(mod_name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                target = node.module.split(".")[0]
                if target in known_modules:
                    graph.setdefault(mod_name, set()).add(target)
                    reverse.setdefault(target, set()).add(mod_name)

    return graph, reverse


def _transitive_dependents(reverse, modules):
    """Find all modules that transitively depend on any module in `modules`.
    BFS on the reverse import graph."""
    visited = set()
    queue = list(modules)
    while queue:
        mod = queue.pop(0)
        if mod in visited:
            continue
        visited.add(mod)
        for dependent in reverse.get(mod, set()):
            if dependent not in visited:
                queue.append(dependent)
    return visited


def find_impacted_tests(root, changed_files, deep=False):
    """Find tests that import or reference changed modules.
    Inspired by pytest-testmon (Puha 2015) — dependency graph for test selection.
    If deep=True, uses transitive closure on the import graph (catches indirect deps)."""
    changed_modules = set()
    for f in changed_files:
        name = Path(f).stem
        changed_modules.add(name)

    if deep:
        # Build full import graph and compute transitive closure
        _graph, reverse = _build_import_graph(root)
        all_affected = _transitive_dependents(reverse, changed_modules)
    else:
        all_affected = changed_modules

    impacted = []
    for test_file in find_tests(root):
        content = test_file.read_text(encoding="utf-8", errors="replace")
        for mod in all_affected:
            if mod in content:
                impacted.append(test_file)
                break

    return impacted


def run_fast(root, verbose=False, deep=False):
    """Run only tests impacted by recent changes.
    If deep=True, uses transitive import graph (catches A->B->C deps)."""
    changed = get_changed_files(root)
    if not changed:
        print("  No changes detected. Nothing to test.")
        return

    print(f"  Changed files: {len(changed)}")
    for f in sorted(changed)[:10]:
        print(f"    {f}")
    if len(changed) > 10:
        print(f"    ... and {len(changed) - 10} more")

    # Always run test files that changed themselves
    test_files = [root / f for f in changed if "test_" in f]

    # Find tests impacted by changed source files
    impacted = find_impacted_tests(root, changed, deep=deep)
    test_files.extend(impacted)
    test_files = sorted(set(test_files))

    if not test_files:
        print("  No impacted tests found. Run full suite with: forge.py")
        return

    print(f"  Running {len(test_files)} impacted test file(s)...")
    start = time.time()
    cmd = [sys.executable, "-m", "pytest"] + [str(f) for f in test_files] + \
          ["-v", "--tb=short", "-q", "--no-header"]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True,
                               cwd=str(root), timeout=300,
                               encoding="utf-8", errors="replace")
        output = result.stdout + result.stderr
    except subprocess.TimeoutExpired:
        print("  TIMEOUT after 5min")
        return

    duration = time.time() - start
    summary = re.search(r"(\d+) passed", output)
    summary_f = re.search(r"(\d+) failed", output)
    passed = int(summary.group(1)) if summary else 0
    failed = int(summary_f.group(1)) if summary_f else 0

    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  FAST MODE — {passed + failed} tests in {duration:.1f}s")
    print(f"  Passed: {passed}  Failed: {failed}")
    if failed > 0:
        for match in re.finditer(r"FAILED\s+(.*?)$", output, re.MULTILINE):
            print(f"    [FAIL] {match.group(1).strip()}")
    print(f"{bar}\n")


# === SNAPSHOT / GOLDEN FILE TESTING ===
def snapshot_capture(root, cmd_str):
    """Capture command output as a golden file for regression detection.
    Golden master testing — Feathers 2004, Working Effectively with Legacy Code."""
    snap_dir = root / SNAPSHOT_DIR
    os.makedirs(str(snap_dir), exist_ok=True)

    # Generate snapshot name from command
    name = re.sub(r"[^a-zA-Z0-9_-]", "_", cmd_str)[:80]
    snap_path = snap_dir / f"{name}.golden"
    meta_path = snap_dir / f"{name}.meta.json"

    print(f"  Capturing: {cmd_str[:60]}...")
    try:
        result = subprocess.run(shlex.split(cmd_str, posix=(os.name != "nt")),
                               capture_output=True,
                               text=True, cwd=str(root), timeout=60,
                               encoding="utf-8", errors="replace")
        output = result.stdout
    except subprocess.TimeoutExpired:
        print("  Command timed out (60s)")
        return

    snap_path.write_text(output, encoding="utf-8")
    save_json(str(meta_path), {
        "command": cmd_str,
        "captured": datetime.now().isoformat(),
        "lines": output.count("\n"),
        "size": len(output)
    })
    print(f"  Saved: {snap_path.name} ({output.count(chr(10))} lines)")


def snapshot_check(root):
    """Compare all golden files against current output."""
    snap_dir = root / SNAPSHOT_DIR
    if not snap_dir.exists():
        print("  No snapshots found. Use: forge.py --snapshot \"command\"")
        return

    metas = list(snap_dir.glob("*.meta.json"))
    if not metas:
        print("  No snapshots found.")
        return

    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  SNAPSHOT CHECK — {len(metas)} golden file(s)")
    print(f"{bar}")

    diffs = 0
    for meta_path in sorted(metas):
        meta = load_json(str(meta_path))
        if not meta:
            continue

        golden_path = meta_path.with_suffix("").with_suffix(".golden")
        if not golden_path.exists():
            print(f"  [MISSING] {golden_path.name}")
            diffs += 1
            continue

        expected = golden_path.read_text(encoding="utf-8")

        # Re-run command
        try:
            result = subprocess.run(shlex.split(meta["command"], posix=(os.name != "nt")),
                                   capture_output=True, text=True,
                                   cwd=str(root), timeout=60,
                                   encoding="utf-8", errors="replace")
            actual = result.stdout
        except subprocess.TimeoutExpired:
            print(f"  [TIMEOUT] {meta['command']}")
            diffs += 1
            continue

        if actual == expected:
            print(f"  [OK]   {meta['command'][:60]}")
        else:
            diffs += 1
            # Show diff summary
            exp_lines = expected.split("\n")
            act_lines = actual.split("\n")
            print(f"  [DIFF] {meta['command'][:60]}")
            print(f"         Expected {len(exp_lines)} lines, got {len(act_lines)}")
            # Show first 3 differing lines
            shown = 0
            for i, (e, a) in enumerate(zip(exp_lines, act_lines)):
                if e != a and shown < 3:
                    print(f"         L{i+1}: -{e[:60]}")
                    print(f"         L{i+1}: +{a[:60]}")
                    shown += 1

    status = "PASS" if diffs == 0 else f"FAIL ({diffs} diff(s))"
    print(f"\n  Result: {status}")
    print(f"{bar}\n")
    if diffs > 0:
        sys.exit(1)


# === WAVELET CHURN DECOMPOSITION (Hassan 2009 + Haar wavelet) ===
def _haar_wavelet_energy(signal):
    """Compute multi-scale energy of a time signal using Haar wavelet.
    Returns sum of detail coefficients energy across scales.
    High energy = bursts at multiple timescales = high risk.
    Pure Python, zero deps. Hassan 2009 used entropy; wavelets are the next step."""
    if len(signal) < 2:
        return 0.0
    # Pad to power of 2
    n = 1
    while n < len(signal):
        n *= 2
    padded = list(signal) + [0.0] * (n - len(signal))
    energy = 0.0
    level = 0
    while len(padded) >= 2:
        details = []
        approx = []
        for i in range(0, len(padded), 2):
            if i + 1 < len(padded):
                a = (padded[i] + padded[i + 1]) / 2.0
                d = (padded[i] - padded[i + 1]) / 2.0
                approx.append(a)
                details.append(d)
            else:
                approx.append(padded[i])
        # Weight higher-frequency (lower-level) details more — bursts matter more than trends
        weight = 2.0 ** (-level * 0.5)  # level 0 = x1.0, level 1 = x0.71, level 2 = x0.5
        energy += sum(d * d for d in details) * weight
        padded = approx
        level += 1
    return math.sqrt(energy) if energy > 0 else 0.0


def _build_commit_signal(dates, weeks=8):
    """Build a daily commit-count signal from a list of ISO date strings.
    Returns a list of length (weeks*7) where each entry = commits that day."""
    if not dates:
        return [0.0] * (weeks * 7)
    now = datetime.now()
    days = weeks * 7
    signal = [0.0] * days
    for d in dates:
        try:
            dt = datetime.fromisoformat(d.replace("Z", "+00:00"))
            delta = (now - dt.replace(tzinfo=None)).days
            if 0 <= delta < days:
                signal[days - 1 - delta] += 1.0
        except (ValueError, TypeError):
            continue
    return signal


# === KALMAN FILTER ADAPTIVE WEIGHTS (Kalman 1960) ===
class _KalmanPredictor:
    """1D Kalman filter per metric weight. Learns optimal PREDICT_WEIGHTS from history.
    State = weight value, Measurement = observed correlation with actual bugs.
    Process noise Q=0.01, Measurement noise R=0.1. Pure Python, zero deps."""

    def __init__(self, state_path):
        self._path = state_path
        self._state = self._load()

    def _load(self):
        data = load_json(self._path)
        if data and "weights" in data and "P" in data:
            return data
        # Init: start from default weights, high uncertainty
        keys = list(PREDICT_WEIGHTS.keys())
        return {
            "weights": {k: PREDICT_WEIGHTS[k] for k in keys},
            "P": {k: 0.5 for k in keys},  # initial uncertainty
            "history": [],  # [{file, predicted_risk, had_bug}]
            "runs": 0
        }

    def save(self):
        save_json(self._path, self._state)

    def get_weights(self):
        """Return current adapted weights (normalized to sum=1)."""
        w = self._state["weights"]
        total = sum(w.values())
        if total <= 0:
            return dict(PREDICT_WEIGHTS)
        return {k: v / total for k, v in w.items()}

    def update(self, file_metrics, actual_bugs):
        """Update weights based on observed bug files.
        file_metrics: {filename: {churn_n, freq_n, wavelet_n, ...}}
        actual_bugs: set of filenames that had bugs (from git log bugfix keywords)."""
        if not file_metrics or not actual_bugs:
            return

        Q = 0.01  # process noise
        R = 0.1   # measurement noise

        keys = list(PREDICT_WEIGHTS.keys())
        w = self._state["weights"]
        P = self._state["P"]

        # For each metric, compute correlation with actual bugs
        for k in keys:
            if k not in w:
                continue
            # Metric values for bug files vs non-bug files
            bug_vals = [m.get(k + "_n", 0) for f, m in file_metrics.items() if f in actual_bugs]
            ok_vals = [m.get(k + "_n", 0) for f, m in file_metrics.items() if f not in actual_bugs]

            if not bug_vals or not ok_vals:
                continue

            # Measurement: mean difference (how well this metric separates bugs from non-bugs)
            mean_bug = sum(bug_vals) / len(bug_vals)
            mean_ok = sum(ok_vals) / len(ok_vals)
            measurement = max(0, min(1, (mean_bug - mean_ok + 1) / 2))  # normalize to [0,1]

            # Kalman update
            P_pred = P.get(k, 0.5) + Q
            K = P_pred / (P_pred + R)  # Kalman gain
            w[k] = w[k] + K * (measurement - w[k])
            P[k] = (1 - K) * P_pred

            # Clamp weights to [0.01, 0.5]
            w[k] = max(0.01, min(0.5, w[k]))

        self._state["weights"] = w
        self._state["P"] = P
        self._state["runs"] = self._state.get("runs", 0) + 1
        self.save()


# === AXE 5: DEFECT PREDICTION (Nagappan & Ball 2005, Hassan 2009) ===
def predict_defects(root, weeks=8):
    """Predict which files are most likely to have bugs based on git history.
    Uses: relative churn, change frequency, change bursts, author count,
    bugfix frequency, LOC, recency. Nagappan & Ball ICSE 2005."""
    root = Path(root)
    if not root.is_dir():
        print(f"  Not a directory: {_safe_path(root)}")
        return
    # Get tracked Python files
    tracked = _run_git(root, "ls-files", "*.py")
    if not tracked:
        print("  No tracked .py files found.")
        return
    files = [f for f in tracked.split("\n") if f.strip()]

    # Single git log call for all metrics
    since = f"--since={weeks} weeks ago"
    raw_log = _run_git(root, "log", "--numstat", "--format=COMMIT %H %ae %aI %s", since, "--", "*.py")

    # Parse git log into per-file metrics
    file_stats = {}
    for f in files:
        p = root / f
        loc = len(p.read_text(encoding="utf-8", errors="replace").splitlines()) if p.exists() else 1
        file_stats[f] = {"added": 0, "deleted": 0, "commits": [], "authors": set(),
                         "bugfixes": 0, "loc": max(loc, 1), "dates": []}

    current_author = ""
    current_date = ""
    current_msg = ""
    for line in raw_log.split("\n"):
        if line.startswith("COMMIT "):
            parts = line.split(" ", 4)
            if len(parts) >= 5:
                current_author = parts[2]
                current_date = parts[3]
                current_msg = parts[4].lower()
        elif "\t" in line and current_date:
            parts = line.split("\t")
            if len(parts) == 3:
                added, deleted, fname = parts
                fname = fname.strip()
                if fname in file_stats:
                    s = file_stats[fname]
                    s["added"] += int(added) if added != "-" else 0
                    s["deleted"] += int(deleted) if deleted != "-" else 0
                    s["commits"].append(current_date)
                    s["authors"].add(current_author)
                    s["dates"].append(current_date)
                    if any(w in current_msg for w in ["fix", "bug", "patch", "repair", "crash"]):
                        s["bugfixes"] += 1

    # Compute raw metrics per file
    metrics = {}
    for f, s in file_stats.items():
        if not s["commits"]:
            continue
        churn_rel = (s["added"] + s["deleted"]) / s["loc"]
        freq = len(s["commits"])
        # Wavelet churn: multi-scale energy of commit signal (replaces raw burst)
        commit_signal = _build_commit_signal(s["dates"], weeks)
        wavelet_energy = _haar_wavelet_energy(commit_signal)
        authors = len(s["authors"])
        bugfixes = s["bugfixes"]
        loc = s["loc"]
        # Recency: 1 / (1 + days since last change)
        try:
            last = max(datetime.fromisoformat(d.replace("Z", "+00:00")) for d in s["dates"])
            days_ago = (datetime.now(last.tzinfo) - last).days
            recency = 1.0 / (1.0 + days_ago)
        except (ValueError, TypeError):
            recency = 0.0

        metrics[f] = {"churn": churn_rel, "freq": freq, "wavelet": wavelet_energy,
                      "authors": authors, "bugfix": bugfixes, "loc": loc, "recency": recency}

    if not metrics:
        print(f"  No commits in the last {weeks} weeks.")
        return

    # Normalize min-max per metric
    keys = ["churn", "freq", "wavelet", "authors", "bugfix", "loc", "recency"]
    mins = {k: min(m[k] for m in metrics.values()) for k in keys}
    maxs = {k: max(m[k] for m in metrics.values()) for k in keys}
    for f in metrics:
        for k in keys:
            rng = maxs[k] - mins[k]
            metrics[f][k + "_n"] = (metrics[f][k] - mins[k]) / rng if rng > 0 else 0.0

    # Composite risk score — Kalman-adapted weights if available
    kalman = _KalmanPredictor(str(root / KALMAN_STATE_FILE))
    w = kalman.get_weights()
    for f in metrics:
        m = metrics[f]
        metrics[f]["risk"] = sum(w.get(k, 0) * m.get(k + "_n", 0) for k in keys)

    # Update Kalman with observed bugfix files (feedback loop)
    bugfix_files = {f for f, s in file_stats.items() if s["bugfixes"] > 0}
    if bugfix_files:
        kalman.update(metrics, bugfix_files)

    # Sort and display
    ranked = sorted(metrics.items(), key=lambda x: x[1]["risk"], reverse=True)
    bar = "=" * 50
    print(f"\n{bar}")
    adapted = " (Kalman-adapted)" if kalman._state.get("runs", 0) > 0 else ""
    print(f"  DEFECT PREDICTION{adapted} — {len(metrics)} files, last {weeks} weeks")
    print(f"{bar}")
    if kalman._state.get("runs", 0) > 0:
        print(f"  Weights: {' '.join(f'{k}={v:.2f}' for k,v in w.items())}")
    for i, (f, m) in enumerate(ranked[:15]):
        print(f"  {m['risk']:.2f}  {f}")
        print(f"       churn={m['churn']:.1f} freq={m['freq']} wavelet={m['wavelet']:.2f} "
              f"authors={m['authors']} bugfix={m['bugfix']} loc={m['loc']} recent={m['recency']:.2f}")
    print(f"{bar}\n")


# === AXE 6: FLAKY CLASSIFICATION (Luo et al. 2014, Parry 2021) ===
FLAKY_PATTERNS = {
    "Async Wait": {"patterns": ["time.sleep", "asyncio.sleep", "await ", "async "],
                   "fix": "Use explicit retry/poll or mock time"},
    "Concurrency": {"patterns": ["threading.", "multiprocessing.", "concurrent.", "Lock("],
                    "fix": "Add locks, use mock threading, or isolate state"},
    "Randomness": {"patterns": ["random.", "np.random", "uuid.uuid"],
                   "fix": "Fix seed in test: random.seed(42)"},
    "Resource Leak": {"patterns": ["tempfile.", "socket.", "open(", "requests."],
                      "fix": "Use context managers (with statement)"},
    "Platform": {"patterns": ["os.environ", "sys.platform", "os.name", "platform."],
                 "fix": "Mock os.environ / sys.platform in test"},
    "Floating Point": {"patterns": ["assertAlmostEqual", "pytest.approx", "1e-", "0.0001", "atol="],
                       "fix": "Use pytest.approx() with explicit tolerance"},
    "Unordered": {"patterns": [".keys()", ".values()", ".items()", "set("],
                  "fix": "Sort collections before comparing: sorted()"},
}


def _classify_flaky_test(test_name, root):
    """Scan test source for flaky pattern indicators via AST + text search."""
    # Find the test file
    for test_file in find_tests(root):
        try:
            source = test_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        # Extract just the function name from "file::test_func" or "test_func"
        func_name = test_name.split("::")[-1] if "::" in test_name else test_name
        if func_name not in source:
            continue
        # Check patterns against source text (more robust than AST for attribute chains)
        categories = []
        for cat, info in FLAKY_PATTERNS.items():
            for pat in info["patterns"]:
                if pat in source:
                    categories.append((cat, info["fix"]))
                    break
        return categories
    return []


def _print_flaky_classification(flaky_tests, root):
    """Print classification for detected flaky tests."""
    if not flaky_tests:
        return
    print(f"\n  FLAKY CLASSIFICATION (Luo et al. 2014):")
    for f in flaky_tests:
        cats = _classify_flaky_test(f["test"], root)
        if cats:
            for cat, fix in cats:
                print(f"    {f['test']}")
                print(f"      Category: {cat}")
                print(f"      Fix: {fix}")
                f["category"] = cat  # enrich for saving
        else:
            print(f"    {f['test']}")
            print(f"      Category: Unknown (no pattern detected)")


# === AXE 1: DELTA DEBUGGING / ddmin (Zeller & Hildebrandt 2002) ===
def _split_input(content, ext):
    """Split input into chunks based on file format."""
    if ext == ".json":
        data = json.loads(content)
        if isinstance(data, list):
            return data, "json_list"
        elif isinstance(data, dict):
            return list(data.items()), "json_dict"
    elif ext == ".csv":
        lines = content.strip().split("\n")
        if len(lines) > 1:
            return lines[1:], "csv"  # header kept separately
        return lines, "csv_no_header"
    # Default: split by lines
    return content.strip().split("\n"), "lines"


def _rebuild_input(chunks, fmt, original_content=""):
    """Rebuild input from chunks based on format."""
    if fmt == "json_list":
        return json.dumps(chunks, indent=2, ensure_ascii=False)
    elif fmt == "json_dict":
        return json.dumps(dict(chunks), indent=2, ensure_ascii=False)
    elif fmt == "csv":
        header = original_content.strip().split("\n")[0]
        return header + "\n" + "\n".join(chunks)
    return "\n".join(chunks)


def _test_with_input(root, test_name, input_content, input_ext):
    """Write input to temp file and run test. Returns True if test FAILS."""
    import tempfile
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=input_ext, delete=False,
                                      encoding="utf-8", dir=str(root / FORGE_DIR))
    try:
        tmp.write(input_content)
        tmp.close()
        env = os.environ.copy()
        env["FORGE_MINIMIZE_INPUT"] = tmp.name
        r = subprocess.run([sys.executable, "-m", "pytest", "-x", "-q", "--tb=no",
                           "--no-header", "-k", test_name],
                          capture_output=True, text=True, cwd=str(root),
                          env=env, timeout=30, encoding="utf-8", errors="replace")
        return _pytest_has_failures(r.stdout)
    except subprocess.TimeoutExpired:
        return False  # timeout = can't confirm failure
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


def minimize_input(root, test_name, input_file):
    """Delta debugging: find minimal input that still fails the test.
    Zeller & Hildebrandt 2002, IEEE TSE Vol.28 No.2."""
    input_path = Path(input_file)
    if not input_path.is_absolute():
        input_path = root / input_path
    if not input_path.exists():
        print(f"  File not found: {_safe_path(input_path)}")
        return

    ext = input_path.suffix
    content = input_path.read_text(encoding="utf-8")
    chunks, fmt = _split_input(content, ext)
    original_count = len(chunks)

    if original_count <= 1:
        print(f"  Input has only {original_count} element(s). Nothing to minimize.")
        return

    # Verify test fails with full input first
    print(f"  Verifying {test_name} fails with full input ({original_count} elements)...")
    if not _test_with_input(root, test_name, content, ext):
        print(f"  Test does not fail with this input. Nothing to minimize.")
        return

    print(f"  Running ddmin on {original_count} elements...")
    n = 2
    iteration = 0
    while len(chunks) > 1 and iteration < MINIMIZE_MAX_ITER:
        iteration += 1
        chunk_size = max(1, len(chunks) // n)
        subsets = [chunks[i:i + chunk_size] for i in range(0, len(chunks), chunk_size)]

        found = False
        # Try complements first (remove one subset)
        for i, subset in enumerate(subsets):
            complement = [c for j, s in enumerate(subsets) for c in s if j != i]
            rebuilt = _rebuild_input(complement, fmt, content)
            if _test_with_input(root, test_name, rebuilt, ext):
                chunks = complement
                n = max(n - 1, 2)
                found = True
                print(f"    Step {iteration}: {len(chunks)} elements (complement)")
                break

        if not found:
            # Try subsets alone
            for subset in subsets:
                if len(subset) < len(chunks):
                    rebuilt = _rebuild_input(subset, fmt, content)
                    if _test_with_input(root, test_name, rebuilt, ext):
                        chunks = subset
                        n = 2
                        found = True
                        print(f"    Step {iteration}: {len(chunks)} elements (subset)")
                        break

        if not found:
            if n >= len(chunks):
                break
            n = min(n * 2, len(chunks))

    # Write minimal result
    minimal = _rebuild_input(chunks, fmt, content)
    out_path = input_path.with_suffix(f".minimal{ext}")
    out_path.write_text(minimal, encoding="utf-8")

    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  DDMIN RESULT — {original_count} -> {len(chunks)} elements")
    print(f"{bar}")
    print(f"  Reduction: {(1 - len(chunks)/original_count)*100:.0f}%")
    print(f"  Iterations: {iteration}")
    print(f"  Minimal input saved to: {out_path.name}")
    print(f"{bar}\n")


# === AXE 2: PROPERTY-BASED TEST GENERATION (Claessen & Hughes 2000) ===

# BUG-102 (2026-04-10): destructive functions must NOT be fuzzed without isolation.
# Hypothesis happily generates target_path='.' / dry_run=False and the test then
# scrubs the entire repo in place. We discovered this when test_scrub_secrets
# corrupted 165 files in MUNINN-. See BUGS.md.
#
# Defense: name patterns + AST scan for write operations. If either fires, the
# function is treated as destructive and the generated test is wrapped with
# pytest.skip(). Override with --include-destructive at the CLI level.

_DESTRUCTIVE_NAME_PATTERNS = [
    # filesystem mutations
    r"^scrub_", r"^purge_", r"^install_", r"^uninstall_",
    r"^bootstrap", r"^generate_", r"^create_", r"^delete_", r"^remove_",
    r"^save", r"^write_", r"_write$", r"_save$",
    r"^migrate", r"^upgrade", r"^downgrade",
    r"^rebuild", r"^reset_", r"^cleanup", r"^prune",
    # database / state mutations
    r"^drop_", r"^truncate", r"^insert_", r"^update_",
    r"^observe", r"^feed", r"^ingest", r"^compress_file",
    # network / external side effects
    r"^fetch_", r"^download", r"^upload", r"^send_", r"^post_", r"^put_",
    r"^sync_", r"_sync$", r"^pull_", r"^push_",
    # process / subprocess
    r"^run_", r"^exec_", r"^spawn_", r"^kill_",
    # hooks (anything in hook context is side-effecting by definition)
    r"_hook$", r"^hook_",
    # query bridges and graph traversal (slow on real DBs, BUG-106 family)
    r"^bridge", r"^spread_", r"^find_chain", r"^query_",
    # CLI entry points and full-scan walkers
    r"^cli_", r"^scan_", r"^walk_", r"^assign_", r"^process_",
    r"^analyze_", r"^audit_", r"^report_",
]

_DESTRUCTIVE_CALLS = {
    "write_text", "write_bytes", "writelines", "touch", "mkdir", "makedirs",
    "rename", "replace", "rmtree", "remove", "unlink", "rmdir", "chmod", "chown",
    "system", "popen", "call", "check_call", "check_output", "run",
    "urlopen", "urlretrieve", "post", "put", "patch", "delete",
    "executescript", "executemany",
    "dump", "dumps_to_file",
}

_PATH_LIKE_ARG_NAMES = {
    "path", "repo_path", "target_path", "file_path", "filepath",
    "dir", "dirname", "directory", "root", "output", "out_path", "outfile",
    "src", "dst", "source", "destination", "fp", "filename",
    "tree_path", "db_path", "config_path", "session_path",
}


def _is_destructive_function(node, source_text):
    """Return (is_destructive, reason) for an ast.FunctionDef node.

    Heuristics (any-of):
      1. Name matches a destructive pattern (e.g. scrub_, install_).
      2. Body contains a known-destructive call (write_text, rmtree, run, ...).
      3. Path-like argument + any FS-touching call in the body.
    """
    name = node.name

    for pat in _DESTRUCTIVE_NAME_PATTERNS:
        if re.search(pat, name):
            return True, f"name matches /{pat}/"

    has_path_arg = any(
        a.arg in _PATH_LIKE_ARG_NAMES for a in node.args.args
    )

    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            func = child.func
            if isinstance(func, ast.Attribute) and func.attr in _DESTRUCTIVE_CALLS:
                return True, f"calls .{func.attr}()"
            if isinstance(func, ast.Name) and func.id in _DESTRUCTIVE_CALLS:
                return True, f"calls {func.id}()"
            if isinstance(func, ast.Name) and func.id == "open":
                for arg in list(child.args) + [kw.value for kw in child.keywords]:
                    if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                        if any(m in arg.value for m in ("w", "a", "x", "+")):
                            return True, "calls open() in write mode"

    if has_path_arg:
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                func = child.func
                if isinstance(func, ast.Attribute) and func.attr in (
                    "walk", "iterdir", "glob", "rglob", "scandir", "listdir"
                ):
                    return True, f"path arg + .{func.attr}()"
                if isinstance(func, ast.Attribute) and func.attr in (
                    "read_text", "read_bytes", "open"
                ):
                    return True, f"path arg + .{func.attr}()"

    return False, ""


def gen_props(root, module_path, include_destructive=False):
    """Analyze a Python module and generate Hypothesis property test skeletons.
    Detects: round-trip pairs, idempotent ops, sort/filter invariants.

    BUG-102 fix: destructive functions are skipped by default. Pass
    include_destructive=True to override (NOT recommended without tmp_path).
    """
    mod_path = Path(module_path)
    if not mod_path.is_absolute():
        mod_path = root / mod_path
    if not mod_path.exists():
        print(f"  File not found: {_safe_path(mod_path)}")
        return

    source = mod_path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"  Syntax error in {_safe_path(mod_path)}: {e}")
        return

    # Collect all public functions (top-level only, skip class methods)
    functions = []
    skipped_destructive = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.FunctionDef) and not node.name.startswith("_"):
            # BUG-102: filter destructive functions BEFORE generating any test
            is_destr, reason = _is_destructive_function(node, source)
            if is_destr and not include_destructive:
                skipped_destructive.append((node.name, reason))
                continue
            # Extract arg names and annotations
            args = []
            for arg in node.args.args:
                ann = None
                if arg.annotation:
                    try:
                        ann = ast.literal_eval(arg.annotation) if isinstance(arg.annotation, ast.Constant) else \
                              arg.annotation.id if isinstance(arg.annotation, ast.Name) else None
                    except (ValueError, AttributeError):
                        ann = None
                args.append({"name": arg.arg, "type": ann})
            functions.append({"name": node.name, "args": args, "lineno": node.lineno})

    if not functions:
        print(f"  No public functions found in {mod_path.name}")
        return

    # Detect pairs (encode/decode, compress/decompress, to_X/from_X)
    names = {f["name"] for f in functions}
    PAIRS = [("encode", "decode"), ("compress", "decompress"), ("serialize", "deserialize"),
             ("pack", "unpack"), ("encrypt", "decrypt"), ("dump", "load"),
             ("to_json", "from_json"), ("to_dict", "from_dict")]
    roundtrip_pairs = []
    for a, b in PAIRS:
        if a in names and b in names:
            roundtrip_pairs.append((a, b))
    # Also check to_X/from_X dynamically
    for name in names:
        if name.startswith("to_"):
            inverse = "from_" + name[3:]
            if inverse in names and (name, inverse) not in roundtrip_pairs:
                roundtrip_pairs.append((name, inverse))

    paired_funcs = {f for pair in roundtrip_pairs for f in pair}

    # Type annotation -> Hypothesis strategy
    TYPE_MAP = {"str": "st.text(max_size=100)", "int": "st.integers(-1000, 1000)",
                "float": "st.floats(allow_nan=False, allow_infinity=False)",
                "bool": "st.booleans()", "list": "st.lists(st.integers(), max_size=20)",
                "dict": "st.dictionaries(st.text(max_size=10), st.integers(), max_size=10)",
                "bytes": "st.binary(max_size=100)"}

    def strategy_for(arg):
        if arg["type"] in TYPE_MAP:
            return TYPE_MAP[arg["type"]]
        return "st.text(max_size=50)"

    # Generate module path for import
    try:
        rel = mod_path.relative_to(root)
    except ValueError:
        rel = Path(os.path.relpath(mod_path, root))
    import_path = str(rel).replace(os.sep, ".").replace(".py", "")

    # Build test file — imports are LIVE, not commented
    lines = [
        "#!/usr/bin/env python3",
        f'"""Property-based tests for {mod_path.name} — generated by forge.py --gen-props"""',
        "import sys",
        "import os",
        f"sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))",
        "",
        "from hypothesis import given, strategies as st, settings",
        f"from {import_path} import *",
        "",
    ]

    test_count = 0

    # Round-trip tests
    for enc, dec in roundtrip_pairs:
        lines.append(f"@given(data=st.text(max_size=200))")
        lines.append(f"@settings(max_examples=100, deadline=None)")
        lines.append(f"def test_roundtrip_{enc}_{dec}(data):")
        lines.append(f'    """Round-trip: {dec}({enc}(x)) == x"""')
        lines.append(f"    # Round-trip: {enc} <-> {dec}")
        lines.append(f"    assert {dec}({enc}(data)) == data")
        lines.append("")
        test_count += 1

    # Per-function tests
    for func in functions:
        if func["name"] in paired_funcs:
            continue
        name = func["name"]
        args = [a for a in func["args"] if a["name"] != "self"]
        if not args:
            continue

        strats = ", ".join(f'{a["name"]}={strategy_for(a)}' for a in args)

        if "sort" in name.lower():
            lines.append(f"@given({strats})")
            lines.append(f"@settings(max_examples=100, deadline=None)")
            lines.append(f"def test_{name}_idempotent({', '.join(a['name'] for a in args)}):")
            lines.append(f'    """Idempotent: {name}({name}(x)) == {name}(x)"""')
            lines.append(f"    # Property test for {name}")
            lines.append(f"    result = {name}({args[0]['name']})")
            lines.append(f"    assert {name}(result) == result")
            lines.append(f"    assert len(result) == len({args[0]['name']})")
            lines.append("")
            test_count += 1
        elif "filter" in name.lower():
            lines.append(f"@given({strats})")
            lines.append(f"@settings(max_examples=100, deadline=None)")
            lines.append(f"def test_{name}_subset({', '.join(a['name'] for a in args)}):")
            lines.append(f'    """Subset: len({name}(x)) <= len(x)"""')
            lines.append(f"    # Property test for {name}")
            lines.append(f"    result = {name}({', '.join(a['name'] for a in args)})")
            lines.append(f"    assert len(result) <= len({args[0]['name']})")
            lines.append("")
            test_count += 1
        else:
            # Smoke test: does not crash
            lines.append(f"@given({strats})")
            lines.append(f"@settings(max_examples=50, deadline=None)")
            lines.append(f"def test_{name}_no_crash({', '.join(a['name'] for a in args)}):")
            lines.append(f'    """Smoke: {name}() does not crash on arbitrary input"""')
            lines.append(f"    # Property test for {name}")
            lines.append(f"    try:")
            lines.append(f"        {name}({', '.join(a['name'] for a in args)})")
            lines.append(f"    except (ValueError, TypeError, KeyError, IndexError, OSError, AttributeError, RuntimeError, SystemExit):")
            lines.append(f"        pass  # Expected rejections are OK")
            lines.append("")
            test_count += 1

    if test_count == 0:
        print(f"  No testable functions found in {mod_path.name}")
        if skipped_destructive:
            print(f"  ({len(skipped_destructive)} destructive function(s) skipped — pass --include-destructive to override)")
        return

    # BUG-102: header banner listing skipped destructive functions
    if skipped_destructive:
        banner = [
            "# BUG-102 (forge): the following functions were SKIPPED because",
            "# they have side effects (write to disk, run subprocess, hit",
            "# network). Fuzzing them without isolation would corrupt the repo.",
            "# To test them, write isolated tests by hand using tmp_path.",
        ]
        for fn, reason in skipped_destructive:
            banner.append(f"#   - {fn}  ({reason})")
        banner.append("")
        # Insert after import block
        lines = lines[:9] + banner + lines[9:]

    # Write test file
    tests_dir = root / "tests"
    tests_dir.mkdir(exist_ok=True)
    out_name = f"test_props_{mod_path.stem}.py"
    out_path = tests_dir / out_name
    out_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"  Generated {test_count} property tests -> tests/{out_name}")
    if skipped_destructive:
        print(f"  Skipped {len(skipped_destructive)} destructive function(s):")
        for fn, reason in skipped_destructive[:8]:
            print(f"    - {fn}  ({reason})")
        if len(skipped_destructive) > 8:
            print(f"    ... and {len(skipped_destructive) - 8} more")
        print(f"  Pass --include-destructive to fuzz them anyway (NOT RECOMMENDED).")

    # Check if hypothesis is installed
    try:
        __import__("hypothesis")
    except ImportError:
        print(f"  Note: pip install hypothesis to run these tests")


# === AXE 3: MUTATION TESTING WRAPPER (DeMillo 1978, Jia & Harman 2011) ===
def run_mutation(root, target_file=None):
    """Wrapper around mutmut for mutation testing.
    Mutation score = killed / total. Target: >80%."""
    mutmut = _check_dep("mutmut")
    if not mutmut:
        return

    cmd = [sys.executable, "-m", "mutmut", "run", "--no-progress"]
    if target_file:
        cmd += ["--paths-to-mutate", target_file]

    print(f"  Running mutation testing{' on ' + target_file if target_file else ''}...")
    print(f"  (This can take a while — mutmut runs your tests once per mutation)")
    try:
        subprocess.run(cmd, cwd=str(root), timeout=600, encoding="utf-8", errors="replace")
    except subprocess.TimeoutExpired:
        print("  Mutation testing timed out (10min limit)")
        return

    # Parse results
    r = subprocess.run([sys.executable, "-m", "mutmut", "results"],
                      capture_output=True, text=True, cwd=str(root),
                      encoding="utf-8", errors="replace")
    output = r.stdout

    # Extract counts
    killed = len(re.findall(r"Killed", output))
    survived = len(re.findall(r"Survived", output))
    timeout = len(re.findall(r"Timeout", output))
    suspicious = len(re.findall(r"Suspicious", output))
    total = killed + survived + timeout + suspicious
    score = (killed / total * 100) if total > 0 else 0

    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  MUTATION TESTING — {'PASS' if score >= MUTATION_THRESHOLD else 'FAIL'}")
    print(f"{bar}")
    print(f"  Total mutants:  {total}")
    print(f"  Killed:         {killed}")
    print(f"  Survived:       {survived}")
    print(f"  Timeout:        {timeout}")
    print(f"  Score:          {score:.0f}% (threshold: {MUTATION_THRESHOLD}%)")

    if survived > 0:
        print(f"\n  SURVIVORS (tests didn't catch these mutations):")
        # Get detailed survivor info
        for line in output.split("\n"):
            if "Survived" in line:
                print(f"    {line.strip()}")

    print(f"{bar}\n")

    if score < MUTATION_THRESHOLD:
        sys.exit(1)


# === AXE 4: SPECTRUM-BASED FAULT LOCALIZATION / Ochiai (Abreu et al. 2007) ===
def fault_locate(root):
    """Locate suspicious lines using Ochiai SBFL formula.
    suspiciousness(s) = failed(s) / sqrt(total_failed * (failed(s) + passed(s)))"""
    cov = _check_dep("coverage")
    if not cov:
        return

    # Check pytest-cov
    try:
        __import__("pytest_cov")
    except ImportError:
        print("  pytest-cov not installed. Install with: pip install pytest-cov")
        return

    test_files = find_tests(root)
    if not test_files:
        print("  No tests found.")
        return

    # Run pytest with per-test coverage context
    cov_json = str(root / FORGE_DIR / "coverage.json")
    os.makedirs(str(root / FORGE_DIR), exist_ok=True)
    cmd = [sys.executable, "-m", "pytest"] + [str(f) for f in test_files] + \
          ["--cov", "--cov-context=test", f"--cov-report=json:{cov_json}",
           "-v", "--tb=no", "--no-header", "-q"]

    print("  Running tests with per-test coverage...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(root),
                      timeout=600, encoding="utf-8", errors="replace")

    # Parse test results to know which tests passed/failed
    failed_tests = set()
    passed_tests = set()
    for line in (r.stdout + r.stderr).split("\n"):
        if " PASSED" in line:
            test_id = line.split(" PASSED")[0].strip()
            passed_tests.add(test_id)
        elif " FAILED" in line:
            test_id = line.split(" FAILED")[0].strip()
            failed_tests.add(test_id)

    if not failed_tests:
        print("  No failing tests. Nothing to localize.")
        return

    total_failed = len(failed_tests)

    # Load coverage JSON
    cov_data = load_json(cov_json)
    if not cov_data or "files" not in cov_data:
        print("  Coverage data not available. Check pytest-cov installation.")
        return

    # Build suspiciousness scores per line
    suspects = []
    for src_file, file_data in cov_data["files"].items():
        # Skip test files themselves
        if "test_" in src_file:
            continue
        contexts = file_data.get("contexts", {})
        executed = file_data.get("executed_lines", [])

        for line_no in executed:
            line_key = str(line_no)
            # Which tests covered this line?
            covering_tests = set()
            for ctx_name, ctx_lines in contexts.items():
                if line_no in ctx_lines:
                    covering_tests.add(ctx_name)

            f_count = len(covering_tests & failed_tests)
            p_count = len(covering_tests & passed_tests)

            if f_count == 0:
                continue

            denom = math.sqrt(total_failed * (f_count + p_count))
            score = f_count / denom if denom > 0 else 0.0

            suspects.append({
                "file": src_file, "line": line_no, "score": score,
                "failed": f_count, "passed": p_count
            })

    if not suspects:
        print("  No suspicious lines found (coverage data may be incomplete).")
        return

    suspects.sort(key=lambda x: x["score"], reverse=True)

    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  FAULT LOCALIZATION — Ochiai SBFL")
    print(f"  {total_failed} failing test(s), {len(passed_tests)} passing")
    print(f"{bar}")
    for s in suspects[:OCHIAI_TOP_N]:
        label = "highly suspect" if s["score"] > 0.7 else "suspect" if s["score"] > 0.4 else "low"
        print(f"  {s['score']:.2f}  {s['file']}:{s['line']}")
        print(f"       {s['failed']}/{total_failed} fail, {s['passed']}/{len(passed_tests)} pass — {label}")
    print(f"{bar}\n")


# === UNIFIED ANOMALY DETECTOR (Z-score + IQR hybrid) ===
def detect_anomalies(root, weeks=8):
    """Detect anomalous files across ALL forge metrics simultaneously.
    A file is anomalous if it's an outlier on 2+ metrics.
    Uses modified Z-score (robust to outliers) + IQR fence.
    Subsumes --predict + --flaky + --locate pattern detection."""
    tracked = _run_git(root, "ls-files", "*.py")
    if not tracked:
        print("  No tracked .py files found.")
        return
    files = [f for f in tracked.split("\n") if f.strip()]

    since = f"--since={weeks} weeks ago"
    raw_log = _run_git(root, "log", "--numstat", "--format=COMMIT %H %ae %aI %s", since, "--", "*.py")

    # Build per-file feature vectors
    file_stats = {}
    for f in files:
        p = root / f
        loc = len(p.read_text(encoding="utf-8", errors="replace").splitlines()) if p.exists() else 1
        file_stats[f] = {"added": 0, "deleted": 0, "commits": 0, "authors": set(),
                         "bugfixes": 0, "loc": max(loc, 1), "dates": []}

    current_msg = ""
    for line in raw_log.split("\n"):
        if line.startswith("COMMIT "):
            parts = line.split(" ", 4)
            current_msg = parts[4].lower() if len(parts) >= 5 else ""
            current_author = parts[2] if len(parts) >= 3 else ""
            current_date = parts[3] if len(parts) >= 4 else ""
        elif "\t" in line and current_msg is not None:
            parts = line.split("\t")
            if len(parts) == 3:
                added, deleted, fname = parts
                fname = fname.strip()
                if fname in file_stats:
                    s = file_stats[fname]
                    s["added"] += int(added) if added != "-" else 0
                    s["deleted"] += int(deleted) if deleted != "-" else 0
                    s["commits"] += 1
                    s["authors"].add(current_author)
                    s["dates"].append(current_date)
                    if any(w in current_msg for w in ["fix", "bug", "patch", "crash"]):
                        s["bugfixes"] += 1

    # Compute features
    features = {}
    for f, s in file_stats.items():
        if s["commits"] == 0:
            continue
        churn = (s["added"] + s["deleted"]) / s["loc"]
        signal = _build_commit_signal(s["dates"], weeks)
        wavelet = _haar_wavelet_energy(signal)
        features[f] = [churn, s["commits"], wavelet, len(s["authors"]),
                       s["bugfixes"], s["loc"]]

    if len(features) < 3:
        print(f"  Not enough files with activity ({len(features)}) for anomaly detection.")
        return

    # Modified Z-score per feature dimension (median-based, robust)
    n_dims = 6
    dim_names = ["churn", "freq", "wavelet", "authors", "bugfix", "loc"]
    anomaly_scores = {}

    for f in features:
        anomaly_scores[f] = {"flags": [], "total": 0.0}

    for d in range(n_dims):
        vals = [features[f][d] for f in features]
        median = sorted(vals)[len(vals) // 2]
        # MAD (median absolute deviation)
        abs_devs = sorted(abs(v - median) for v in vals)
        mad = abs_devs[len(abs_devs) // 2] if abs_devs else 1.0
        mad = max(mad, 1e-10)  # avoid division by zero

        for f in features:
            z = 0.6745 * (features[f][d] - median) / mad  # modified Z-score
            if abs(z) > ANOMALY_THRESHOLD:
                anomaly_scores[f]["flags"].append((dim_names[d], z))
                anomaly_scores[f]["total"] += abs(z)

    # Rank by total anomaly score, filter to files with 2+ flags
    anomalies = [(f, s) for f, s in anomaly_scores.items() if len(s["flags"]) >= 2]
    anomalies.sort(key=lambda x: x[1]["total"], reverse=True)

    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  ANOMALY DETECTION — {len(features)} files, {len(anomalies)} anomalous")
    print(f"{bar}")
    if not anomalies:
        print("  No multi-dimensional anomalies detected.")
    else:
        for f, s in anomalies[:15]:
            flags = " ".join(f"{name}={z:+.1f}" for name, z in s["flags"])
            print(f"  {s['total']:.1f}  {f}")
            print(f"       {flags}")
    print(f"{bar}\n")


# === BIO-ROBUSTNESS: Q-MODULARITY OF IMPORT GRAPH (Newman 2006) ===
def measure_robustness(root):
    """Compute Q-modularity of the Python import graph.
    High modularity = well-isolated modules = robust to mutations.
    Low modularity = tightly coupled = fragile, high mutation risk.
    Newman 2006: Q = (1/2m) * sum(A_ij - k_i*k_j/2m) * delta(c_i, c_j)."""
    tracked = _run_git(root, "ls-files", "*.py")
    if not tracked:
        print("  No tracked .py files found.")
        return
    files = [f for f in tracked.split("\n") if f.strip()]

    # Build import graph via AST
    modules = {}  # module_name -> file_path
    edges = []    # (importer, imported)

    for f in files:
        p = root / f
        if not p.exists():
            continue
        mod_name = Path(f).stem
        modules[mod_name] = f
        try:
            source = p.read_text(encoding="utf-8", errors="replace")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = alias.name.split(".")[0]
                    if target in modules or target in [Path(ff).stem for ff in files]:
                        edges.append((mod_name, target))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    target = node.module.split(".")[0]
                    if target in modules or target in [Path(ff).stem for ff in files]:
                        edges.append((mod_name, target))

    if not edges:
        print("  No internal imports found. Modules are fully isolated.")
        return

    # Compute degree per module
    all_mods = set()
    degree = Counter()
    for a, b in edges:
        all_mods.add(a)
        all_mods.add(b)
        degree[a] += 1
        degree[b] += 1

    m = len(edges)
    n = len(all_mods)

    if m == 0:
        print("  No import edges found.")
        return

    # Simple community detection: each directory = one community
    communities = {}
    for f in files:
        mod = Path(f).stem
        if mod in all_mods:
            parts = Path(f).parts
            community = parts[-2] if len(parts) > 1 else "root"
            communities[mod] = community

    # Compute Q-modularity
    adj = set(edges)
    q = 0.0
    for a in all_mods:
        for b in all_mods:
            if communities.get(a) != communities.get(b):
                continue
            a_ij = 1 if (a, b) in adj or (b, a) in adj else 0
            expected = degree[a] * degree[b] / (2 * m)
            q += (a_ij - expected)
    q /= (2 * m)

    # Per-module coupling score
    coupling = {}
    for mod in all_mods:
        internal = sum(1 for a, b in edges if (a == mod or b == mod) and
                      communities.get(a) == communities.get(b))
        external = sum(1 for a, b in edges if (a == mod or b == mod) and
                      communities.get(a) != communities.get(b))
        total = internal + external
        coupling[mod] = external / total if total > 0 else 0.0

    # Report
    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  BIO-ROBUSTNESS — Q-modularity of import graph")
    print(f"{bar}")
    print(f"  Modules: {n}  Imports: {m}  Communities: {len(set(communities.values()))}")
    print(f"  Q-modularity: {q:.3f}", end="")
    if q > 0.3:
        print(" (strong — well-isolated)")
    elif q > 0.1:
        print(" (moderate)")
    else:
        print(" (weak — tightly coupled, mutation-fragile)")

    # Show most coupled modules (highest risk)
    ranked = sorted(coupling.items(), key=lambda x: x[1], reverse=True)
    fragile = [(m, c) for m, c in ranked if c > 0.3]
    if fragile:
        print(f"\n  FRAGILE modules (high external coupling):")
        for mod, c in fragile[:10]:
            f_path = modules.get(mod, mod)
            print(f"    {c:.0%} external  {_safe_path(f_path)}")

    robust = [(m, c) for m, c in ranked if c == 0.0 and degree[m] > 0]
    if robust:
        print(f"\n  ROBUST modules (zero external coupling):")
        for mod, c in robust[:5]:
            f_path = modules.get(mod, mod)
            print(f"    {degree[mod]} internal imports  {_safe_path(f_path)}")

    print(f"{bar}\n")
    return q


# === FULL-CYCLE PIPELINE ===
def full_cycle(root):
    """Run the complete forge pipeline: predict → test → flaky → locate.
    Yggdrasil meta-prompt: the 6 axes form a natural pipeline."""
    bar = "=" * 50
    print(f"\n{bar}")
    print(f"  FORGE FULL CYCLE")
    print(f"{bar}\n")

    # Step 1: Predict risky files
    print("  [1/5] DEFECT PREDICTION")
    predict_defects(root)

    # Step 2: Anomaly scan
    print("  [2/5] ANOMALY DETECTION")
    detect_anomalies(root)

    # Step 3: Run tests
    print("  [3/5] RUNNING TESTS")
    results = run_tests(root)
    baseline = load_json(str(root / BASELINE_FILE))
    print_report(results, baseline)
    os.makedirs(str(root / FORGE_DIR), exist_ok=True)
    save_json(str(root / REPORT_FILE), results)
    log_run(root, results)

    # Step 4: If failures, locate
    if results["failed"] > 0:
        print("  [4/5] FAULT LOCALIZATION (Ochiai)")
        try:
            fault_locate(root)
        except SystemExit as e:
            if e.code not in (0, None):
                print(f"  fault_locate exited with code {e.code}, continuing pipeline")
    else:
        print("  [4/5] FAULT LOCALIZATION — skipped (no failures)")

    # Step 5: Robustness check
    print("  [5/5] BIO-ROBUSTNESS")
    measure_robustness(root)

    print(f"\n{bar}")
    print(f"  FULL CYCLE COMPLETE")
    print(f"{bar}\n")

    if results["failed"] > 0 or results["errors"] > 0:
        sys.exit(1)


def main():
    root = find_repo_root()
    args = sys.argv[1:]

    if "--init" in args:
        init_repo(root)
        return

    if "--add" in args:
        idx = args.index("--add")
        desc = " ".join(args[idx + 1:]) if idx + 1 < len(args) else "unnamed bug"
        add_bug(root, desc)
        return

    if "--close" in args:
        idx = args.index("--close")
        bug_id = args[idx + 1] if idx + 1 < len(args) else ""
        if not bug_id or bug_id.startswith("--"):
            print("  Usage: forge.py --close BUG-001")
            return
        close_bug(root, bug_id.upper())
        return

    if "--flaky" in args:
        idx = args.index("--flaky")
        runs = int(args[idx + 1]) if idx + 1 < len(args) and args[idx + 1].isdigit() else 5
        detect_flaky(root, runs)
        return

    if "--heatmap" in args:
        show_heatmap(root)
        return

    if "--bisect" in args:
        idx = args.index("--bisect")
        test_name = args[idx + 1] if idx + 1 < len(args) else ""
        if not test_name:
            print("  Usage: forge.py --bisect test_name")
            return
        bisect_test(root, test_name)
        return

    if "--fast-deep" in args:
        run_fast(root, verbose="--verbose" in args or "-v" in args, deep=True)
        return

    if "--fast" in args:
        run_fast(root, verbose="--verbose" in args or "-v" in args)
        return

    if "--snapshot" in args:
        idx = args.index("--snapshot")
        cmd_str = " ".join(args[idx + 1:]) if idx + 1 < len(args) else ""
        if not cmd_str:
            print("  Usage: forge.py --snapshot \"command to capture\"")
            return
        snapshot_capture(root, cmd_str)
        return

    if "--snapshot-check" in args:
        snapshot_check(root)
        return

    if "--predict" in args:
        idx = args.index("--predict")
        weeks = 8
        if "--weeks" in args:
            wi = args.index("--weeks")
            weeks = int(args[wi + 1]) if wi + 1 < len(args) and args[wi + 1].isdigit() else 8
        predict_defects(root, weeks)
        return

    if "--minimize" in args:
        idx = args.index("--minimize")
        test_name = args[idx + 1] if idx + 1 < len(args) else ""
        input_file = args[idx + 2] if idx + 2 < len(args) else ""
        if not test_name or not input_file:
            print("  Usage: forge.py --minimize TEST_NAME INPUT_FILE")
            return
        minimize_input(root, test_name, input_file)
        return

    if "--gen-props" in args:
        idx = args.index("--gen-props")
        module_path = args[idx + 1] if idx + 1 < len(args) else ""
        if not module_path:
            print("  Usage: forge.py --gen-props path/to/module.py [--include-destructive]")
            return
        include_destructive = "--include-destructive" in args
        if include_destructive:
            print("  WARNING: --include-destructive is set. Destructive functions WILL")
            print("  be fuzzed by Hypothesis. This can corrupt your repo (BUG-102).")
            print("  Make sure tests are isolated with tmp_path before running them.")
        gen_props(root, module_path, include_destructive=include_destructive)
        return

    if "--mutate" in args:
        idx = args.index("--mutate")
        target = args[idx + 1] if idx + 1 < len(args) and not args[idx + 1].startswith("-") else None
        run_mutation(root, target)
        return

    if "--locate" in args:
        fault_locate(root)
        return

    if "--anomaly" in args:
        weeks = 8
        if "--weeks" in args:
            wi = args.index("--weeks")
            weeks = int(args[wi + 1]) if wi + 1 < len(args) and args[wi + 1].isdigit() else 8
        detect_anomalies(root, weeks)
        return

    if "--robustness" in args:
        measure_robustness(root)
        return

    if "--full-cycle" in args:
        full_cycle(root)
        return

    if "--watch" in args:
        print("  Watching for changes... (Ctrl+C to stop)")
        last_hash = ""
        while True:
            # Hash all .py files
            h = hashlib.md5()
            for f in sorted(root.rglob("*.py")):
                if ".forge" not in str(f) and "__pycache__" not in str(f):
                    h.update(f.read_bytes())
            current = h.hexdigest()
            if current != last_hash:
                last_hash = current
                os.system("cls" if os.name == "nt" else "clear")
                results = run_tests(root)
                baseline = load_json(str(root / BASELINE_FILE))
                print_report(results, baseline)
                log_run(root, results)
                save_json(str(root / REPORT_FILE), results)
            time.sleep(2)
        return

    # Default: run tests
    verbose = "--verbose" in args or "-v" in args
    results = run_tests(root, verbose=verbose)
    baseline = load_json(str(root / BASELINE_FILE))
    print_report(results, baseline)

    if "--baseline" in args:
        save_json(str(root / BASELINE_FILE), results)
        print(f"  Baseline saved: {results['passed']} passed, {results['failed']} failed")

    # Always save report + log
    os.makedirs(str(root / FORGE_DIR), exist_ok=True)
    save_json(str(root / REPORT_FILE), results)
    log_run(root, results)

    if "--diff" in args:
        if baseline:
            print("  (Diff shown above in report)")
        else:
            print("  No baseline found. Run: forge.py --baseline")

    # Exit code: non-zero if failures
    if results["failed"] > 0 or results["errors"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
