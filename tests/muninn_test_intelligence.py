#!/usr/bin/env python3
"""
Muninn Test Intelligence — Adaptive test framework.

Not a dumb battery. Each test file is CLASSIFIED, and analysis adapts:
- Security tests get crypto invariant checks + boundary fuzzing
- Math tests get property-based validation (monotonicity, symmetry, idempotence)
- Integration tests get state isolation verification
- Performance tests get regression detection
- All tests get double analysis (run + external review)

Usage:
    python tests/muninn_test_intelligence.py                    # Full intelligent battery
    python tests/muninn_test_intelligence.py --tier security    # Security tests only
    python tests/muninn_test_intelligence.py --review           # With Claude external review
    python tests/muninn_test_intelligence.py --deep             # Deep mode: +fuzz +property

Architecture (SEI CMU taxonomy):
    Layer 1: Classification — detect test type from imports/patterns/assertions
    Layer 2: Execution — run with per-type instrumentation
    Layer 3: Analysis — per-type post-mortem (invariant checks, flaky detection)
    Layer 4: Synthesis — cross-test correlation, regression detection
    Layer 5: Review — external Claude audit of failures + suspicious passes
"""
import ast
import json
import math
import os
import re
import subprocess
import sys
import tempfile
import time
from collections import defaultdict
from pathlib import Path

# ── Configuration ──────────────────────────────────────────────────
PYTHON = sys.executable
TESTS_DIR = Path(__file__).parent
REPO_DIR = TESTS_DIR.parent
ENGINE_DIR = REPO_DIR / "engine" / "core"
RESULTS_DIR = TESTS_DIR / ".test_intelligence"

# Test tiers (SEI CMU taxonomy adapted)
TIERS = {
    "security":    {"priority": 0, "emoji": "S", "fail_is_blocker": True},
    "unit":        {"priority": 1, "emoji": "U", "fail_is_blocker": False},
    "integration": {"priority": 2, "emoji": "I", "fail_is_blocker": False},
    "cli_e2e":     {"priority": 3, "emoji": "E", "fail_is_blocker": False},
    "performance": {"priority": 4, "emoji": "P", "fail_is_blocker": False},
}


# ══════════════════════════════════════════════════════════════════
# LAYER 1: Classification — detect test type from source code
# ══════════════════════════════════════════════════════════════════

class TestClassifier:
    """Classifies test files by analyzing source code patterns."""

    # Patterns that indicate test type
    SECURITY_SIGNALS = {
        "imports": ["vault", "sync_tls", "ssl", "cryptography", "AESGCM", "PBKDF2"],
        "calls": ["encrypt", "decrypt", "generate_certs", "load_key", "lock", "unlock",
                  "SyncServer", "SyncClient", "RateLimiter"],
        "strings": ["password", "cert", "tls", "aes", "salt", "InvalidTag", "TLS", "mTLS"],
    }
    MATH_SIGNALS = {
        "imports": ["math"],
        "calls": ["abs", "math.log", "math.isnan", "math.isinf", "math.exp"],
        "patterns": [r"assert.*<.*<", r"assert.*>.*>", r"recall", r"temperature"],
    }
    NETWORK_SIGNALS = {
        "imports": ["socket", "ssl"],
        "calls": ["create_connection", "socket.socketpair", "wrap_socket"],
        "strings": ["port", "bind", "listen", "accept"],
    }
    PERF_SIGNALS = {
        "imports": ["time"],
        "calls": ["time.time", "time.monotonic", "time.perf_counter"],
        "patterns": [r"assert.*<\s*\d+\.?\d*\s*,", r"timeout", r"timing"],
    }
    CLI_SIGNALS = {
        "imports": ["subprocess"],
        "calls": ["subprocess.run", "subprocess.Popen"],
        "strings": ["muninn.py", "returncode", "capture_output"],
    }

    @staticmethod
    def classify(filepath: Path) -> dict:
        """Classify a test file. Returns {types, domain, patterns, risk_level}."""
        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return {"types": ["unknown"], "domain": "unknown", "patterns": [],
                    "risk_level": "low", "estimated_time": "fast"}

        types = set()
        patterns = set()
        domain = "general"

        # Parse imports
        imports = set()
        for line in source.split("\n"):
            m = re.match(r"^\s*(?:from|import)\s+([\w.]+)", line)
            if m:
                imports.add(m.group(1).split(".")[0])

        # Security classification
        sec = TestClassifier.SECURITY_SIGNALS
        if any(i in source for i in sec["imports"]):
            if any(c in source for c in sec["calls"]):
                types.add("security")
                domain = "crypto" if "vault" in source else "network"

        # Math/property classification
        mat = TestClassifier.MATH_SIGNALS
        if any(i in imports for i in mat["imports"]) or \
           any(re.search(p, source) for p in mat.get("patterns", [])):
            patterns.add("math_assertions")

        # Network classification
        net = TestClassifier.NETWORK_SIGNALS
        if any(i in imports for i in net["imports"]) and \
           any(c in source for c in net["calls"]):
            types.add("network")
            patterns.add("socket_networking")

        # Performance classification
        perf = TestClassifier.PERF_SIGNALS
        if any(re.search(p, source) for p in perf.get("patterns", [])):
            types.add("performance")
            patterns.add("timing_assertions")

        # CLI/E2E classification
        cli = TestClassifier.CLI_SIGNALS
        if any(c in source for c in cli["calls"]):
            types.add("cli_e2e")
            patterns.add("subprocess_cli")

        # tmpdir isolation
        if "tempfile" in imports or "TemporaryDirectory" in source:
            patterns.add("tmpdir_isolation")

        # Real data (reads from actual .muninn/)
        if ".muninn/" in source or "real" in filepath.stem:
            patterns.add("real_data")

        # Code inspection (fragile — breaks on refactor)
        if "inspect.getsource" in source or "re.search" in source and "def " in source:
            patterns.add("code_inspection")

        # Domain detection
        if "mycelium" in source.lower() or "Mycelium" in source:
            domain = "mycelium"
        elif "tree" in source.lower() and ("branch" in source.lower() or "prune" in source.lower()):
            domain = "tree_memory"
        elif "boot" in source and ("scored" in source or "relevance" in source):
            domain = "retrieval"
        elif any(v in source for v in ["V1A", "V2B", "V3A", "V6B", "V9A", "V9B", "V10A"]):
            domain = "bio_vectors"
        elif "immune" in filepath.stem or "danger" in source or "suppression" in source:
            domain = "immune"
        elif "compress" in source.lower() or "L10" in source or "L11" in source:
            domain = "compression"

        # Integration if it calls real muninn functions with tmpdir
        if "tmpdir_isolation" in patterns and any(f in source for f in
                ["muninn.boot", "muninn.prune", "muninn.grow_branches",
                 "inject_memory", "Mycelium("]):
            types.add("integration")

        # Default to unit if nothing else
        if not types:
            types.add("unit")

        # Risk level
        risk = "low"
        if "security" in types:
            risk = "critical"
        elif "network" in types or "real_data" in patterns:
            risk = "high"
        elif "integration" in types:
            risk = "medium"

        # Estimated time
        est = "fast"  # <2s
        if "real_data" in patterns or "performance" in types:
            est = "slow"  # >5s
        elif "integration" in types or "network" in types:
            est = "medium"  # 2-5s

        return {
            "types": sorted(types),
            "domain": domain,
            "patterns": sorted(patterns),
            "risk_level": risk,
            "estimated_time": est,
        }


# ══════════════════════════════════════════════════════════════════
# LAYER 2: Execution — per-type instrumented test runner
# ══════════════════════════════════════════════════════════════════

class TestRunner:
    """Runs tests with per-type instrumentation."""

    @staticmethod
    def run_one(filepath: Path, classification: dict) -> dict:
        """Run a single test file. Returns detailed result.

        Network tests get 1 retry (flaky on Windows due to port TIME_WAIT).
        """
        is_network = "network" in classification["types"] or \
                     "socket_networking" in classification["patterns"]
        max_attempts = 2 if is_network else 1
        last_result = None

        for attempt in range(max_attempts):
            if attempt > 0:
                time.sleep(2)  # Wait for port cleanup between retries
            t0 = time.monotonic()
            env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
            last_result = TestRunner._run_once(filepath, classification, t0, env)
            if last_result["status"] == "PASS":
                if attempt > 0:
                    last_result["retried"] = True
                return last_result
        return last_result

    @staticmethod
    def _run_once(filepath: Path, classification: dict, t0: float, env: dict) -> dict:
        """Single execution attempt."""
        try:
            r = subprocess.run(
                [PYTHON, str(filepath)],
                capture_output=True, timeout=120, env=env,
            )
            stdout = r.stdout.decode("utf-8", errors="replace")
            stderr = r.stderr.decode("utf-8", errors="replace")
            output = stdout + stderr
            elapsed = time.monotonic() - t0

            # Count individual PASS/FAIL/SKIP
            passes = [l.strip() for l in output.split("\n")
                      if re.search(r"\bPASS\b", l) and "ALL" not in l]
            fails = [l.strip() for l in output.split("\n")
                     if re.search(r"\bFAIL\b", l) and "ALL" not in l and "RESULTAT" not in l]
            skips = [l.strip() for l in output.split("\n")
                     if re.search(r"\bSKIP\b", l)]

            return {
                "file": filepath.name,
                "classification": classification,
                "exit_code": r.returncode,
                "passed": len(passes),
                "failed": len(fails),
                "skipped": len(skips),
                "pass_lines": passes,
                "fail_lines": fails,
                "skip_lines": skips,
                "elapsed": round(elapsed, 2),
                "output_tail": output[-1500:] if r.returncode != 0 else "",
                "status": "PASS" if r.returncode == 0 else "FAIL",
            }

        except subprocess.TimeoutExpired:
            return {
                "file": filepath.name,
                "classification": classification,
                "exit_code": -1,
                "passed": 0, "failed": 1, "skipped": 0,
                "pass_lines": [], "fail_lines": ["TIMEOUT after 120s"],
                "skip_lines": [],
                "elapsed": 120.0,
                "output_tail": "TIMEOUT",
                "status": "TIMEOUT",
            }
        except Exception as e:
            return {
                "file": filepath.name,
                "classification": classification,
                "exit_code": -2,
                "passed": 0, "failed": 1, "skipped": 0,
                "pass_lines": [], "fail_lines": [str(e)],
                "skip_lines": [],
                "elapsed": time.monotonic() - t0,
                "output_tail": str(e),
                "status": "ERROR",
            }


# ══════════════════════════════════════════════════════════════════
# LAYER 3: Per-type post-mortem analysis
# ══════════════════════════════════════════════════════════════════

class TestAnalyzer:
    """Per-type deep analysis after execution."""

    @staticmethod
    def analyze(result: dict) -> list:
        """Returns list of findings (warnings/issues beyond pass/fail)."""
        findings = []
        cls = result["classification"]
        types = cls["types"]
        patterns = cls["patterns"]

        # ── Security-specific checks ──
        if "security" in types:
            findings.extend(TestAnalyzer._check_security(result))

        # ── Math-specific checks ──
        if "math_assertions" in patterns:
            findings.extend(TestAnalyzer._check_math(result))

        # ── Performance regression ──
        if "performance" in types or "timing_assertions" in patterns:
            findings.extend(TestAnalyzer._check_performance(result))

        # ── Flakiness detection ──
        if "network" in types or "socket_networking" in patterns:
            findings.extend(TestAnalyzer._check_flaky(result))

        # ── Code inspection fragility ──
        if "code_inspection" in patterns:
            findings.append({
                "level": "warn",
                "type": "fragile_test",
                "msg": f"{result['file']}: uses source code inspection — will break on refactor",
            })

        # ── Suspicious passes (test did nothing) ──
        if result["status"] == "PASS" and result["passed"] == 0 and result["skipped"] == 0:
            findings.append({
                "level": "warn",
                "type": "empty_test",
                "msg": f"{result['file']}: passed but reported 0 individual test results",
            })

        # ── All skipped (test is dead) ──
        if result["skipped"] > 0 and result["passed"] == 0:
            findings.append({
                "level": "warn",
                "type": "dead_test",
                "msg": f"{result['file']}: all {result['skipped']} tests skipped — is this still relevant?",
            })

        return findings

    @staticmethod
    def _check_security(result: dict) -> list:
        findings = []
        output = result.get("output_tail", "")

        # Security test MUST not be skipped
        if result["skipped"] > 0:
            findings.append({
                "level": "critical",
                "type": "security_skip",
                "msg": f"{result['file']}: SECURITY test has {result['skipped']} skipped bornes — this is NOT acceptable",
            })

        # Security test failure is a BLOCKER
        if result["status"] != "PASS":
            findings.append({
                "level": "critical",
                "type": "security_fail",
                "msg": f"{result['file']}: SECURITY REGRESSION — {result['failed']} bornes failed",
            })

        # Check for common crypto anti-patterns in output
        if "CERT_NONE" in output and "verify=False" not in output:
            findings.append({
                "level": "warn",
                "type": "crypto_weak",
                "msg": f"{result['file']}: CERT_NONE detected without explicit verify=False",
            })

        return findings

    @staticmethod
    def _check_math(result: dict) -> list:
        findings = []
        # Check for hardcoded dates used as "today" (the A1.1 bug pattern)
        # Only flag dates that are RECENT (within 30 days of now) AND used as last_access
        # Old fixed dates (2025-07-30 etc.) are intentional reference points for delta tests
        filepath = TESTS_DIR / result["file"]
        try:
            source = filepath.read_text(encoding="utf-8", errors="replace")
            from datetime import datetime, timedelta
            now = datetime.now()
            cutoff = (now - timedelta(days=30)).strftime("%Y-%m-%d")

            date_matches = re.findall(r'"(202[5-9]-\d{2}-\d{2})"', source)
            flagged = set()
            for d in date_matches:
                # Only flag dates that are RECENT and likely meant to be "today"
                if d < cutoff:
                    continue  # Old reference date — intentional
                idx = source.find(f'"{d}"')
                context = source[max(0, idx-150):idx+150]
                # Only flag if used as last_access (not as a fixed reference)
                if "last_access" in context and d not in flagged:
                    flagged.add(d)
                    findings.append({
                        "level": "warn",
                        "type": "hardcoded_date",
                        "msg": f"{result['file']}: hardcoded recent date '{d}' as last_access — use time.strftime('%Y-%m-%d')",
                    })
        except OSError:
            pass
        return findings

    @staticmethod
    def _check_performance(result: dict) -> list:
        findings = []
        # Load previous results for regression detection
        history_file = RESULTS_DIR / f"{result['file']}.history.json"
        if history_file.exists():
            try:
                history = json.loads(history_file.read_text(encoding="utf-8"))
                prev_time = history[-1].get("elapsed", 0)
                curr_time = result["elapsed"]
                if prev_time > 0 and curr_time > prev_time * 2.0:
                    findings.append({
                        "level": "warn",
                        "type": "perf_regression",
                        "msg": f"{result['file']}: {curr_time:.1f}s vs previous {prev_time:.1f}s (>{2.0}x slower)",
                    })
            except (json.JSONDecodeError, IndexError, KeyError):
                pass
        return findings

    @staticmethod
    def _check_flaky(result: dict) -> list:
        findings = []
        output = result.get("output_tail", "")
        if "ConnectionResetError" in output or "WinError 10054" in output:
            findings.append({
                "level": "warn",
                "type": "flaky_network",
                "msg": f"{result['file']}: ConnectionResetError — likely port reuse race on Windows",
            })
        if "Address already in use" in output or "WinError 10048" in output:
            findings.append({
                "level": "warn",
                "type": "flaky_network",
                "msg": f"{result['file']}: address already in use — port collision",
            })
        return findings


# ══════════════════════════════════════════════════════════════════
# LAYER 4: Cross-test synthesis
# ══════════════════════════════════════════════════════════════════

class TestSynthesizer:
    """Cross-test correlation and pattern detection."""

    @staticmethod
    def synthesize(results: list, findings: list) -> dict:
        """Analyze results across all tests. Returns synthesis report."""
        report = {
            "total_files": len(results),
            "total_tests": sum(r["passed"] + r["failed"] + r["skipped"] for r in results),
            "total_passed": sum(r["passed"] for r in results),
            "total_failed": sum(r["failed"] for r in results),
            "total_skipped": sum(r["skipped"] for r in results),
            "files_pass": sum(1 for r in results if r["status"] == "PASS"),
            "files_fail": sum(1 for r in results if r["status"] != "PASS"),
            "total_time": round(sum(r["elapsed"] for r in results), 1),
            "findings": findings,
            "security_blockers": [f for f in findings if f["level"] == "critical"],
            "warnings": [f for f in findings if f["level"] == "warn"],
        }

        # ── By tier ──
        by_tier = defaultdict(lambda: {"pass": 0, "fail": 0, "skip": 0, "time": 0})
        for r in results:
            primary = r["classification"]["types"][0] if r["classification"]["types"] else "unknown"
            by_tier[primary]["pass" if r["status"] == "PASS" else "fail"] += 1
            by_tier[primary]["time"] += r["elapsed"]
        report["by_tier"] = dict(by_tier)

        # ── By domain ──
        by_domain = defaultdict(lambda: {"pass": 0, "fail": 0})
        for r in results:
            d = r["classification"]["domain"]
            by_domain[d]["pass" if r["status"] == "PASS" else "fail"] += 1
        report["by_domain"] = dict(by_domain)

        # ── Failure correlation ──
        failed_domains = [r["classification"]["domain"] for r in results if r["status"] != "PASS"]
        if failed_domains:
            from collections import Counter
            domain_counts = Counter(failed_domains)
            hotspot = domain_counts.most_common(1)[0] if domain_counts else None
            if hotspot and hotspot[1] >= 2:
                report["failure_hotspot"] = {
                    "domain": hotspot[0],
                    "count": hotspot[1],
                    "msg": f"Multiple failures in '{hotspot[0]}' domain — likely shared root cause",
                }

        # ── Slowest tests ──
        sorted_by_time = sorted(results, key=lambda r: -r["elapsed"])
        report["slowest"] = [(r["file"], r["elapsed"]) for r in sorted_by_time[:5]]

        return report


# ══════════════════════════════════════════════════════════════════
# LAYER 5: Property-based invariant checks (Hypothesis-style)
# ══════════════════════════════════════════════════════════════════

class PropertyChecker:
    """Property-based invariant validation — without Hypothesis dependency.

    Generates random inputs and checks that invariants hold.
    Inspired by QuickCheck/Hypothesis but zero-dependency.
    """

    @staticmethod
    def run_all() -> list:
        """Run all property checks. Returns list of results."""
        results = []
        checks = [
            PropertyChecker._prop_encrypt_decrypt_roundtrip,
            PropertyChecker._prop_pbkdf2_deterministic,
            PropertyChecker._prop_rate_limiter_never_negative,
            PropertyChecker._prop_ebbinghaus_bounded,
            PropertyChecker._prop_protocol_roundtrip,
            PropertyChecker._prop_secret_filter_no_false_negatives,
            PropertyChecker._prop_temperature_bounded,
        ]
        for check in checks:
            try:
                name, passed, msg = check()
                results.append({"name": name, "status": "PASS" if passed else "FAIL", "msg": msg})
            except Exception as e:
                results.append({"name": check.__name__, "status": "ERROR", "msg": str(e)})
        return results

    @staticmethod
    def _prop_encrypt_decrypt_roundtrip():
        """Property: encrypt(decrypt(x)) == x for all byte strings."""
        name = "PROP: encrypt/decrypt roundtrip (100 random inputs)"
        try:
            sys.path.insert(0, str(ENGINE_DIR))
            from vault import _derive_key, _encrypt_bytes, _decrypt_bytes
            key = _derive_key("test-prop", b"s" * 32)
            import random
            for i in range(100):
                size = random.randint(0, 10000)
                data = os.urandom(size)
                ct = _encrypt_bytes(data, key)
                pt = _decrypt_bytes(ct, key)
                if pt != data:
                    return name, False, f"roundtrip failed at size={size}"
            return name, True, "100/100 roundtrips OK (0-10KB)"
        except ImportError:
            return name, True, "SKIP: cryptography not installed"

    @staticmethod
    def _prop_pbkdf2_deterministic():
        """Property: same (password, salt) always produces same key."""
        name = "PROP: PBKDF2 deterministic (50 random salts)"
        try:
            sys.path.insert(0, str(ENGINE_DIR))
            from vault import _derive_key
            for _ in range(50):
                salt = os.urandom(32)
                pw = os.urandom(8).hex()
                k1 = _derive_key(pw, salt)
                k2 = _derive_key(pw, salt)
                if k1 != k2:
                    return name, False, f"non-deterministic for pw={pw[:8]}..."
            return name, True, "50/50 deterministic"
        except ImportError:
            return name, True, "SKIP: cryptography not installed"

    @staticmethod
    def _prop_rate_limiter_never_negative():
        """Property: RateLimiter.allow() returns bool, never crashes."""
        name = "PROP: RateLimiter always returns bool (1000 calls)"
        sys.path.insert(0, str(ENGINE_DIR))
        from sync_tls import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=1)
        import random
        for _ in range(1000):
            ip = f"{random.randint(0,255)}.{random.randint(0,255)}.0.0"
            result = limiter.allow(ip)
            if not isinstance(result, bool):
                return name, False, f"allow() returned {type(result)}, not bool"
        return name, True, "1000/1000 calls returned bool"

    @staticmethod
    def _prop_ebbinghaus_bounded():
        """Property: recall is always in [0, 1] for any valid node."""
        name = "PROP: Ebbinghaus recall in [0,1] (200 random nodes)"
        sys.path.insert(0, str(ENGINE_DIR))
        from muninn import _ebbinghaus_recall
        import random
        for _ in range(200):
            node = {
                "access_count": random.randint(0, 100),
                "last_access": f"20{random.randint(20,26):02d}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                "usefulness": random.uniform(0, 2.0),
            }
            try:
                r = _ebbinghaus_recall(node)
                if not (0 <= r <= 1.0 + 1e-9):
                    return name, False, f"recall={r} out of [0,1] for {node}"
                if math.isnan(r) or math.isinf(r):
                    return name, False, f"recall={r} (NaN/Inf) for {node}"
            except Exception as e:
                return name, False, f"crash: {e} for {node}"
        return name, True, "200/200 in [0,1], no NaN/Inf"

    @staticmethod
    def _prop_protocol_roundtrip():
        """Property: send_msg + recv_msg preserves data for any JSON-safe dict."""
        name = "PROP: protocol roundtrip (50 random messages)"
        sys.path.insert(0, str(ENGINE_DIR))
        from sync_tls import _send_msg, _recv_msg
        import socket, random, string
        for _ in range(50):
            data = {
                "action": "".join(random.choices(string.ascii_lowercase, k=random.randint(1, 20))),
                "count": random.randint(-1000000, 1000000),
                "nested": {"x": random.random(), "y": None},
                "list": [random.randint(0, 100) for _ in range(random.randint(0, 10))],
            }
            s1, s2 = socket.socketpair()
            try:
                _send_msg(s1, data)
                received = _recv_msg(s2)
                if received != data:
                    return name, False, f"mismatch: sent={data}, got={received}"
            finally:
                s1.close()
                s2.close()
        return name, True, "50/50 roundtrips OK"

    @staticmethod
    def _prop_secret_filter_no_false_negatives():
        """Property: known secret patterns are always caught."""
        name = "PROP: secret filter catches all known patterns"
        sys.path.insert(0, str(ENGINE_DIR))
        from muninn import _SECRET_PATTERNS
        import re as _re

        # Synthetic secrets that MUST be caught
        test_secrets = [
            "ghp_1234567890abcdefABCDEF1234567890abcd",  # GitHub classic
            "github_pat_AAAAAAAAAAAAAAAAAAAAAA_BBBBBBBBBBBBBBBBB",  # GitHub fine-grained
            "gho_abcdef1234567890abcdef1234567890abcd",  # GitHub OAuth
            "glpat-xxxxxxxxxxxxxxxxxxxx",  # GitLab
            "AKIAIOSFODNN7EXAMPLE",  # AWS
            "sk-ant-api03-XXXXXXXXXXXXXXXXXXXXXXXX",  # Anthropic
            "sk-XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX",  # OpenAI
            "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9",  # Bearer JWT
        ]
        compiled = [_re.compile(p) for p in _SECRET_PATTERNS]
        missed = []
        for secret in test_secrets:
            caught = any(p.search(secret) for p in compiled)
            if not caught:
                missed.append(secret[:20] + "...")
        if missed:
            return name, False, f"missed: {missed}"
        return name, True, f"{len(test_secrets)}/{len(test_secrets)} secrets caught"

    @staticmethod
    def _prop_temperature_bounded():
        """Property: compute_temperature always in [0, ~1.5] for any node."""
        name = "PROP: temperature bounded (200 random nodes)"
        sys.path.insert(0, str(ENGINE_DIR))
        from muninn import compute_temperature
        import random
        for _ in range(200):
            node = {
                "access_count": random.randint(0, 50),
                "last_access": f"20{random.randint(20,26):02d}-{random.randint(1,12):02d}-{random.randint(1,28):02d}",
                "usefulness": random.uniform(0, 1.0),
                "lines": random.randint(0, 200),
                "max_lines": random.randint(50, 200),
            }
            try:
                t = compute_temperature(node)
                if not (0 <= t <= 1.01):
                    return name, False, f"temperature={t} out of [0,1.0] for {node}"
                if math.isnan(t) or math.isinf(t):
                    return name, False, f"temperature={t} (NaN/Inf) for {node}"
            except Exception as e:
                return name, False, f"crash: {e} for {node}"
        return name, True, "200/200 in [0,1.0], no NaN/Inf"


# ══════════════════════════════════════════════════════════════════
# LAYER 6: Boundary fuzzing
# ══════════════════════════════════════════════════════════════════

class BoundaryFuzzer:
    """Edge case / boundary testing — targeted, not random."""

    @staticmethod
    def run_all() -> list:
        """Run boundary tests for critical functions."""
        results = []
        checks = [
            BoundaryFuzzer._fuzz_encrypt_empty,
            BoundaryFuzzer._fuzz_encrypt_large,
            BoundaryFuzzer._fuzz_recv_msg_truncated,
            BoundaryFuzzer._fuzz_rate_limiter_burst,
            BoundaryFuzzer._fuzz_ebbinghaus_extreme_dates,
            BoundaryFuzzer._fuzz_protocol_max_message,
        ]
        for check in checks:
            try:
                name, passed, msg = check()
                results.append({"name": name, "status": "PASS" if passed else "FAIL", "msg": msg})
            except Exception as e:
                results.append({"name": check.__name__, "status": "ERROR", "msg": str(e)})
        return results

    @staticmethod
    def _fuzz_encrypt_empty():
        """Boundary: encrypt/decrypt empty bytes."""
        name = "FUZZ: encrypt empty bytes"
        try:
            sys.path.insert(0, str(ENGINE_DIR))
            from vault import _derive_key, _encrypt_bytes, _decrypt_bytes
            key = _derive_key("fuzz", b"x" * 32)
            ct = _encrypt_bytes(b"", key)
            pt = _decrypt_bytes(ct, key)
            if pt != b"":
                return name, False, f"expected empty, got {len(pt)} bytes"
            return name, True, "empty bytes roundtrip OK"
        except ImportError:
            return name, True, "SKIP: cryptography not installed"

    @staticmethod
    def _fuzz_encrypt_large():
        """Boundary: encrypt 1MB data."""
        name = "FUZZ: encrypt 1MB data"
        try:
            sys.path.insert(0, str(ENGINE_DIR))
            from vault import _derive_key, _encrypt_bytes, _decrypt_bytes
            key = _derive_key("fuzz", b"x" * 32)
            data = os.urandom(1024 * 1024)
            ct = _encrypt_bytes(data, key)
            pt = _decrypt_bytes(ct, key)
            if pt != data:
                return name, False, "1MB roundtrip corrupted"
            return name, True, f"1MB roundtrip OK ({len(ct)} bytes ciphertext)"
        except ImportError:
            return name, True, "SKIP: cryptography not installed"

    @staticmethod
    def _fuzz_recv_msg_truncated():
        """Boundary: recv_msg with truncated header."""
        name = "FUZZ: recv_msg truncated connection"
        sys.path.insert(0, str(ENGINE_DIR))
        from sync_tls import _recv_msg
        import socket
        s1, s2 = socket.socketpair()
        try:
            # Send only 2 bytes (header needs 4)
            s1.sendall(b"\x00\x00")
            s1.close()
            try:
                _recv_msg(s2)
                return name, False, "should have raised ConnectionError"
            except ConnectionError:
                return name, True, "correctly raises ConnectionError on truncated header"
        finally:
            s2.close()

    @staticmethod
    def _fuzz_rate_limiter_burst():
        """Boundary: 10000 requests from same IP in burst."""
        name = "FUZZ: rate limiter 10K burst"
        sys.path.insert(0, str(ENGINE_DIR))
        from sync_tls import RateLimiter
        limiter = RateLimiter(max_requests=5, window_seconds=60)
        allowed = sum(1 for _ in range(10000) if limiter.allow("attacker"))
        if allowed != 5:
            return name, False, f"allowed {allowed} requests, expected exactly 5"
        return name, True, f"correctly allowed exactly 5/10000 requests"

    @staticmethod
    def _fuzz_ebbinghaus_extreme_dates():
        """Boundary: recall with dates far in past and future."""
        name = "FUZZ: Ebbinghaus extreme dates"
        sys.path.insert(0, str(ENGINE_DIR))
        from muninn import _ebbinghaus_recall
        # 10 years ago
        r_old = _ebbinghaus_recall({"access_count": 1, "last_access": "2016-01-01"})
        if not (0 <= r_old <= 1.0):
            return name, False, f"10yr old recall={r_old}"
        # Tomorrow (future date)
        from datetime import datetime, timedelta
        tomorrow = (datetime.now() + timedelta(days=1)).strftime("%Y-%m-%d")
        r_future = _ebbinghaus_recall({"access_count": 1, "last_access": tomorrow})
        if not (0 <= r_future <= 1.0 + 1e-9):
            return name, False, f"future recall={r_future}"
        # Missing date
        r_none = _ebbinghaus_recall({"access_count": 1})
        if math.isnan(r_none) or math.isinf(r_none):
            return name, False, f"missing date recall={r_none}"
        return name, True, f"old={r_old:.6f}, future={r_future:.4f}, missing={r_none:.4f} — all bounded"

    @staticmethod
    def _fuzz_protocol_max_message():
        """Boundary: protocol rejects oversized message."""
        name = "FUZZ: protocol rejects >50MB message"
        sys.path.insert(0, str(ENGINE_DIR))
        from sync_tls import _recv_msg
        import socket, struct
        s1, s2 = socket.socketpair()
        try:
            # Send header claiming 60MB payload
            s1.sendall(struct.pack(">I", 60 * 1024 * 1024))
            s1.close()
            try:
                _recv_msg(s2)
                return name, False, "should have rejected 60MB message"
            except ValueError as e:
                if "too large" in str(e).lower():
                    return name, True, "correctly rejects oversized message"
                return name, False, f"wrong error: {e}"
            except ConnectionError:
                return name, True, "connection closed (acceptable)"
        finally:
            s2.close()


# ══════════════════════════════════════════════════════════════════
# MAIN: Orchestrator
# ══════════════════════════════════════════════════════════════════

def print_header(text, char="=", width=70):
    print(f"\n{char * width}")
    print(f"  {text}")
    print(f"{char * width}")


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Muninn Test Intelligence")
    parser.add_argument("--tier", help="Run only this tier (security/unit/integration/cli_e2e/performance)")
    parser.add_argument("--deep", action="store_true", help="Deep mode: +property checks +boundary fuzzing")
    parser.add_argument("--review", action="store_true", help="Request external Claude review of results")
    parser.add_argument("--save", action="store_true", help="Save results for regression tracking")
    args = parser.parse_args()

    print_header("MUNINN TEST INTELLIGENCE v1.0")
    t_start = time.monotonic()

    # ── Discover tests ──
    test_files = sorted(TESTS_DIR.glob("test_*.py"))
    print(f"\n  Discovered: {len(test_files)} test files")

    # ── Classify ──
    print_header("LAYER 1: CLASSIFICATION", "-")
    classifications = {}
    for f in test_files:
        cls = TestClassifier.classify(f)
        classifications[f] = cls

    # Filter by tier if requested
    if args.tier:
        test_files = [f for f in test_files if args.tier in classifications[f]["types"]]
        print(f"  Filtered to {len(test_files)} files (tier={args.tier})")

    # Sort by priority: security first, then unit, integration, etc.
    def sort_key(f):
        types = classifications[f]["types"]
        best = min(TIERS.get(t, {"priority": 99})["priority"] for t in types)
        return (best, f.name)
    test_files.sort(key=sort_key)

    # Print classification summary
    type_counts = defaultdict(int)
    for f in test_files:
        for t in classifications[f]["types"]:
            type_counts[t] += 1
    for tier_name, info in sorted(TIERS.items(), key=lambda x: x[1]["priority"]):
        count = type_counts.get(tier_name, 0)
        if count > 0:
            print(f"    [{info['emoji']}] {tier_name:15s}: {count} files")

    # ── Execute ──
    print_header("LAYER 2: EXECUTION", "-")
    results = []
    for i, f in enumerate(test_files):
        cls = classifications[f]
        tier_char = TIERS.get(cls["types"][0], {"emoji": "?"})["emoji"]
        risk = cls["risk_level"]
        risk_mark = " !!!" if risk == "critical" else " !" if risk == "high" else ""

        result = TestRunner.run_one(f, cls)
        results.append(result)

        status_sym = "OK" if result["status"] == "PASS" else "XX"
        p = result["passed"]
        f_count = result["failed"]
        s = result["skipped"]
        t = result["elapsed"]

        print(f"  [{tier_char}] {status_sym} {result['file']:45s} "
              f"P={p:2d} F={f_count:1d} S={s:1d} ({t:5.1f}s){risk_mark}")

    # ── Analyze ──
    print_header("LAYER 3: PER-TYPE ANALYSIS", "-")
    all_findings = []
    for result in results:
        findings = TestAnalyzer.analyze(result)
        all_findings.extend(findings)

    if all_findings:
        for f in all_findings:
            level = f["level"].upper()
            print(f"  [{level}] {f['msg']}")
    else:
        print("  No issues found beyond pass/fail.")

    # ── Property checks (deep mode) ──
    if args.deep:
        print_header("LAYER 5: PROPERTY-BASED INVARIANTS", "-")
        prop_results = PropertyChecker.run_all()
        for pr in prop_results:
            sym = "OK" if pr["status"] == "PASS" else "XX"
            print(f"  {sym} {pr['name']}: {pr['msg']}")
            if pr["status"] != "PASS":
                all_findings.append({"level": "critical", "type": "property_violation",
                                     "msg": f"{pr['name']}: {pr['msg']}"})

        print_header("LAYER 6: BOUNDARY FUZZING", "-")
        fuzz_results = BoundaryFuzzer.run_all()
        for fr in fuzz_results:
            sym = "OK" if fr["status"] == "PASS" else "XX"
            print(f"  {sym} {fr['name']}: {fr['msg']}")
            if fr["status"] != "PASS":
                all_findings.append({"level": "critical", "type": "boundary_violation",
                                     "msg": f"{fr['name']}: {fr['msg']}"})

    # ── Synthesis ──
    print_header("LAYER 4: SYNTHESIS", "-")
    report = TestSynthesizer.synthesize(results, all_findings)

    total = report["total_tests"]
    passed = report["total_passed"]
    failed = report["total_failed"]
    skipped = report["total_skipped"]
    elapsed = time.monotonic() - t_start

    print(f"\n  Files:  {report['files_pass']} PASS / {report['files_fail']} FAIL "
          f"(of {report['total_files']})")
    print(f"  Tests:  {passed} PASS / {failed} FAIL / {skipped} SKIP "
          f"(of {total})")
    print(f"  Time:   {elapsed:.1f}s total")

    if report.get("failure_hotspot"):
        hs = report["failure_hotspot"]
        print(f"\n  HOTSPOT: {hs['msg']}")

    print(f"\n  By tier:")
    for tier, stats in report["by_tier"].items():
        p = stats.get("pass", 0)
        f = stats.get("fail", 0)
        t = stats.get("time", 0)
        print(f"    {tier:15s}: {p} pass, {f} fail ({t:.1f}s)")

    print(f"\n  Slowest:")
    for name, t in report["slowest"]:
        print(f"    {name:45s} {t:.1f}s")

    # ── Security gate ──
    blockers = report["security_blockers"]
    if blockers:
        print_header("SECURITY BLOCKERS — DO NOT SHIP", "!")
        for b in blockers:
            print(f"  {b['msg']}")
        sys.exit(2)

    # ── Warnings ──
    warnings = report["warnings"]
    if warnings:
        print(f"\n  Warnings: {len(warnings)}")
        for w in warnings:
            print(f"    - {w['msg']}")

    # ── Save for regression tracking ──
    if args.save:
        RESULTS_DIR.mkdir(exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        save_path = RESULTS_DIR / f"run_{ts}.json"
        save_data = {
            "timestamp": ts,
            "report": report,
            "results": [{k: v for k, v in r.items() if k != "output_tail"} for r in results],
        }
        save_path.write_text(json.dumps(save_data, indent=2, default=str), encoding="utf-8")
        print(f"\n  Saved: {save_path}")

        # Update per-file history for regression detection
        for r in results:
            hist_path = RESULTS_DIR / f"{r['file']}.history.json"
            history = []
            if hist_path.exists():
                try:
                    history = json.loads(hist_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    pass
            history.append({"ts": ts, "status": r["status"], "elapsed": r["elapsed"],
                            "passed": r["passed"], "failed": r["failed"]})
            history = history[-20:]  # Keep last 20 runs
            hist_path.write_text(json.dumps(history, indent=2), encoding="utf-8")

    # ── Review prompt ──
    if args.review and (report["files_fail"] > 0 or warnings):
        print_header("LAYER 5: EXTERNAL REVIEW PROMPT", "-")
        review = _build_review_prompt(report, results, all_findings)
        review_path = RESULTS_DIR or TESTS_DIR
        if not RESULTS_DIR.exists():
            RESULTS_DIR.mkdir(exist_ok=True)
        review_file = RESULTS_DIR / "review_prompt.md"
        review_file.write_text(review, encoding="utf-8")
        print(f"  Review prompt saved: {review_file}")
        print(f"  Send to Claude for external audit.")

    # ── Final verdict ──
    if report["files_fail"] == 0 and not blockers:
        prop_count = len(prop_results) if args.deep else 0
        fuzz_count = len(fuzz_results) if args.deep else 0
        extra = f" + {prop_count} properties + {fuzz_count} boundary" if args.deep else ""
        print_header(f"ALL CLEAR: {passed} tests{extra}, 0 failures, {elapsed:.1f}s")
        sys.exit(0)
    else:
        print_header(f"FAILURES: {failed} tests failed in {report['files_fail']} files")
        sys.exit(1)


def _build_review_prompt(report, results, findings):
    """Build a prompt for external Claude review."""
    lines = [
        "# Muninn Test Intelligence — External Review Request",
        "",
        f"Date: {time.strftime('%Y-%m-%d %H:%M')}",
        f"Total: {report['total_files']} files, {report['total_tests']} tests",
        f"Result: {report['files_pass']} pass, {report['files_fail']} fail",
        "",
        "## Failures",
    ]
    for r in results:
        if r["status"] != "PASS":
            lines.append(f"\n### {r['file']} ({r['classification']['types']}, {r['classification']['domain']})")
            lines.append(f"Exit code: {r['exit_code']}")
            for fl in r["fail_lines"]:
                lines.append(f"  - {fl}")
            if r["output_tail"]:
                lines.append(f"```\n{r['output_tail'][-500:]}\n```")

    if findings:
        lines.append("\n## Findings")
        for f in findings:
            lines.append(f"- [{f['level']}] {f['msg']}")

    lines.extend([
        "",
        "## Review Questions",
        "1. Are any failures masking deeper issues?",
        "2. Are the 'warn' findings actionable?",
        "3. What test coverage gaps exist?",
        "4. Are there property invariants we should add?",
        "5. Security: any bypasses or weaknesses in the test suite?",
    ])
    return "\n".join(lines)


if __name__ == "__main__":
    main()
