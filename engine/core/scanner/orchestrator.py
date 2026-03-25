"""
B-SCAN-14: Orchestrator — wires ALL scanner briques together
==============================================================
Main entry point for the Muninn security scanner. Runs the full pipeline:
  cache check (12) -> graph metrics (04) -> priority rank (05)
  -> LLM+regex in parallel (06+07) -> AST confirm (08) -> merge (09)
  -> propagation (10) -> dynamic detect (11) -> report (13)

INPUT:  repo path + options (--full | --incremental | --dry-run | --no-llm)
OUTPUT: ScanReport (from B-SCAN-13)

Pure Python, no mandatory external dependencies.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path

# ── Triple import fallback ─────────────────────────────────────────
try:
    from engine.core.scanner import __name__ as _pkg_check
except ImportError:
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.normpath(os.path.join(_here, '..', '..', '..'))
    if _root not in sys.path:
        sys.path.insert(0, _root)

# ── Import all briques with triple fallback ────────────────────────

def _import_brick(abs_path, rel_path, names):
    """Import names from a module using triple fallback."""
    mod = None
    try:
        mod = __import__(abs_path, fromlist=names)
    except ImportError:
        try:
            mod = __import__(rel_path, fromlist=names)
        except ImportError:
            pass
    if mod is None:
        return {n: None for n in names}
    return {n: getattr(mod, n, None) for n in names}

# B-SCAN-12: Cache
_cache = _import_brick(
    "engine.core.scanner.cache", "cache",
    ["load_cache", "save_cache", "compute_delta", "update_cache", "ScanCacheEntry"])
load_cache = _cache["load_cache"]
save_cache = _cache["save_cache"]
compute_delta = _cache["compute_delta"]
update_cache = _cache["update_cache"]
ScanCacheEntry = _cache["ScanCacheEntry"]

# B-SCAN-04: R0 Calculator
_r0 = _import_brick(
    "engine.core.scanner.r0_calculator", "r0_calculator",
    ["compute_graph_metrics", "FileMetrics", "GraphMetrics"])
compute_graph_metrics = _r0["compute_graph_metrics"]

# B-SCAN-05: Priority Ranker
_rank = _import_brick(
    "engine.core.scanner.priority_ranker", "priority_ranker",
    ["rank_files", "RankedFile"])
rank_files = _rank["rank_files"]

# B-SCAN-06: LLM Scanner
_llm = _import_brick(
    "engine.core.scanner.llm_scanner", "llm_scanner",
    ["scan_file", "scan_batch", "LLMFinding"])
llm_scan_file = _llm["scan_file"]

# B-SCAN-07: Regex Filters
_regex = _import_brick(
    "engine.core.scanner.regex_filters", "regex_filters",
    ["scan_file_content", "load_bible", "RegexMatch"])
regex_scan_file_content = _regex["scan_file_content"]
regex_load_bible = _regex["load_bible"]

# B-SCAN-08: AST Analyzer
_ast = _import_brick(
    "engine.core.scanner.ast_analyzer", "ast_analyzer",
    ["analyze_findings", "analyze_finding", "ASTVerdict"])
ast_analyze_findings = _ast["analyze_findings"]

# B-SCAN-09: Merger
_merger = _import_brick(
    "engine.core.scanner.merger", "merger",
    ["merge_findings", "MergedFinding", "summary"])
merge_findings = _merger["merge_findings"]

# B-SCAN-10: Propagation
_prop = _import_brick(
    "engine.core.scanner.propagation", "propagation",
    ["propagate_findings", "PropagationResult", "BlastRadius"])
propagate_findings = _prop["propagate_findings"]

# B-SCAN-11: Dynamic Detector
_dyn = _import_brick(
    "engine.core.scanner.dynamic_detector", "dynamic_detector",
    ["scan_content", "scan_file", "DynamicImport", "ScanResult"])
dyn_scan_content = _dyn["scan_content"]

# B-SCAN-13: Report
_report = _import_brick(
    "engine.core.scanner.report", "report",
    ["generate_report", "ScanReport", "to_markdown", "to_json", "compute_exit_code"])
generate_report = _report["generate_report"]
ScanReport = _report["ScanReport"]
report_to_markdown = _report["to_markdown"]
report_to_json = _report["to_json"]
compute_exit_code = _report["compute_exit_code"]

# B-SCAN-01: Bible Scraper (for core bible)
_bible_scraper = _import_brick(
    "engine.core.scanner.bible_scraper", "bible_scraper",
    ["scrape_bible", "BibleEntry"])
scrape_bible = _bible_scraper["scrape_bible"]

# B-SCAN-02: Bible Compressor
_bible_comp = _import_brick(
    "engine.core.scanner.bible_compressor", "bible_compressor",
    ["compress_bible", "load_bible_mn"])
compress_bible = _bible_comp["compress_bible"]
load_bible_mn = _bible_comp["load_bible_mn"]

logger = logging.getLogger(__name__)

_SCANNER_VERSION = "0.1.0"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dataclasses
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class ScanOptions:
    """Options for the orchestrator."""
    repo_path: str = ""
    full: bool = False
    incremental: bool = True
    dry_run: bool = False
    no_llm: bool = False
    bible_dir: str = None
    output_dir: str = None
    max_llm_files: int = 0       # 0 = top 20%
    propagation_method: str = "auto"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Language detection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_EXT_TO_LANG = {
    ".py": "python", ".pyw": "python",
    ".js": "javascript", ".jsx": "javascript",
    ".ts": "javascript", ".tsx": "javascript",
    ".go": "go",
    ".java": "java",
    ".rb": "ruby",
    ".php": "php",
    ".c": "c_cpp", ".h": "c_cpp", ".cpp": "c_cpp", ".hpp": "c_cpp",
    ".yaml": "config", ".yml": "config",
    ".json": "config", ".toml": "config",
    ".ini": "config", ".env": "config",
}


def _detect_languages(repo_path: str) -> dict:
    """Map file -> language for all source files in repo.

    Args:
        repo_path: root of the repository

    Returns:
        dict {relative_file_path: language}
    """
    result = {}
    skip_dirs = {".git", "node_modules", "__pycache__", "venv", ".venv",
                 "dist", "build", ".muninn", ".tox", "vendor", ".mypy_cache"}
    for root, dirs, files in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in skip_dirs and not d.startswith(".")]
        for fname in files:
            ext = os.path.splitext(fname)[1].lower()
            lang = _EXT_TO_LANG.get(ext)
            if lang:
                rel = os.path.relpath(os.path.join(root, fname), repo_path)
                rel = rel.replace("\\", "/")
                result[rel] = lang
    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Import graph builder
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_IMPORT_PATTERNS = {
    "python": [
        re.compile(r'^\s*import\s+([\w.]+)'),
        re.compile(r'^\s*from\s+([\w.]+)\s+import'),
    ],
    "javascript": [
        re.compile(r'''require\s*\(\s*['"]([^'"]+)['"]\s*\)'''),
        re.compile(r'''import\s+.*?from\s+['"]([^'"]+)['"]'''),
        re.compile(r'''import\s*\(\s*['"]([^'"]+)['"]\s*\)'''),
    ],
    "go": [
        re.compile(r'^\s*"([^"]+)"'),
        re.compile(r'^\s*\w+\s+"([^"]+)"'),
    ],
    "java": [
        re.compile(r'^\s*import\s+([\w.]+);'),
    ],
}


def _build_graph(repo_path: str, file_langs: dict = None) -> dict:
    """Build dependency graph from import statements.

    Args:
        repo_path: root of the repository
        file_langs: dict {relative_file_path: language} (optional, computed if None)

    Returns:
        adjacency dict {file: [(neighbor, 1.0), ...]}
    """
    if file_langs is None:
        file_langs = _detect_languages(repo_path)

    graph = {}
    # Read all files
    file_contents = {}
    for fpath, lang in file_langs.items():
        full_path = os.path.join(repo_path, fpath)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                file_contents[fpath] = f.read()
        except (OSError, IOError):
            continue

    # All files are nodes
    for fpath in file_langs:
        graph[fpath] = []

    # Extract imports per file
    for fpath, lang in file_langs.items():
        content = file_contents.get(fpath, "")
        if not content:
            continue
        patterns = _IMPORT_PATTERNS.get(lang, [])
        if not patterns:
            continue

        imports_found = set()
        for line in content.splitlines():
            for pat in patterns:
                m = pat.search(line)
                if m:
                    imports_found.add(m.group(1))

        # Try to resolve imports to files in the repo
        edges = []
        for imp in imports_found:
            # Convert dotted import to path
            imp_path = imp.replace(".", "/")
            # Try matching against known files
            for candidate in file_langs:
                cand_no_ext = os.path.splitext(candidate)[0].replace("\\", "/")
                if cand_no_ext.endswith(imp_path) or cand_no_ext == imp_path:
                    if candidate != fpath:
                        edges.append((candidate, 1.0))
                        break

        graph[fpath] = edges

    return graph


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# File hashing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _hash_file(file_path: str) -> str:
    """SHA-256 hash of a file."""
    h = hashlib.sha256()
    try:
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
    except (OSError, IOError):
        return ""
    return h.hexdigest()


def _hash_all_files(repo_path: str, file_langs: dict) -> dict:
    """Hash all source files. Returns {relative_path: sha256}."""
    hashes = {}
    for fpath in file_langs:
        full = os.path.join(repo_path, fpath)
        sha = _hash_file(full)
        if sha:
            hashes[fpath] = sha
    return hashes


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# File selection
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _select_files(options: ScanOptions, file_langs: dict, cache_path: str) -> list:
    """Select which files to scan based on options and cache.

    Args:
        options: scan options
        file_langs: dict {file: language}
        cache_path: path to scan_cache.json

    Returns:
        list of file paths to scan
    """
    all_files = sorted(file_langs.keys())

    if options.full or not os.path.exists(cache_path):
        return all_files

    if not options.incremental:
        return all_files

    # Incremental: use cache delta
    hashes = _hash_all_files(options.repo_path, file_langs)
    if compute_delta is None:
        return all_files
    delta = compute_delta(hashes, cache_path)
    return delta.to_scan


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Bible loading
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _load_bibles(bible_dir: str, languages: dict) -> dict:
    """Load bible entries per language.

    Args:
        bible_dir: directory with bible JSON files
        languages: dict mapping unique language names

    Returns:
        dict {language: list_of_bible_entries}
    """
    bibles = {}
    if not bible_dir or not os.path.isdir(bible_dir):
        return bibles

    unique_langs = set(languages.values()) if isinstance(languages, dict) else set()
    for lang in unique_langs:
        if lang == "config":
            continue
        if regex_load_bible is not None:
            entries = regex_load_bible(bible_dir, lang)
            if entries:
                bibles[lang] = entries
    return bibles


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Scan log
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _log_scan(log_path: str, scan_data: dict) -> None:
    """Append scan data as a JSON line to the scan log.

    Args:
        log_path: path to .muninn/scan_log.jsonl
        scan_data: dict with scan metadata
    """
    try:
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(scan_data, ensure_ascii=False) + "\n")
    except (OSError, IOError) as e:
        logger.warning(f"[B-SCAN-14] Failed to write scan log: {e}")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Helpers
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _simple_graph(graph: dict) -> dict:
    """Convert weighted adjacency {f: [(n, w), ...]} to unweighted {f: [n, ...]}."""
    simple = {}
    for node, edges in graph.items():
        neighbors = []
        for item in edges:
            if isinstance(item, (list, tuple)):
                neighbors.append(item[0])
            else:
                neighbors.append(item)
        simple[node] = neighbors
    return simple


def _read_file(repo_path: str, rel_path: str) -> str:
    """Read a file from the repo, return content or empty string."""
    try:
        full = os.path.join(repo_path, rel_path)
        with open(full, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except (OSError, IOError):
        return ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Main pipeline
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scan(options: ScanOptions):
    """Run the full scan pipeline.

    Args:
        options: ScanOptions with repo_path and flags

    Returns:
        ScanReport from B-SCAN-13
    """
    t_start = time.time()
    errors = []
    timings = {}

    repo_path = options.repo_path
    if not repo_path or not os.path.isdir(repo_path):
        report = ScanReport(
            exit_code=0,
            files_scanned=0,
            scan_duration=0.0,
        ) if ScanReport else None
        return report

    muninn_dir = os.path.join(repo_path, ".muninn")
    cache_path = os.path.join(muninn_dir, "scan_cache.json")
    log_path = os.path.join(muninn_dir, "scan_log.jsonl")
    output_dir = options.output_dir or os.path.join(muninn_dir, "scan_output")

    # ── Phase 0: Detect languages ──────────────────────────────────
    t0 = time.time()
    try:
        file_langs = _detect_languages(repo_path)
    except Exception as e:
        logger.error(f"[B-SCAN-14] Language detection failed: {e}")
        errors.append(f"lang_detect: {e}")
        file_langs = {}
    timings["detect_languages"] = time.time() - t0

    if not file_langs:
        report = ScanReport(
            exit_code=0,
            files_scanned=0,
            scan_duration=time.time() - t_start,
        ) if ScanReport else None
        return report

    # ── Phase 1: Select files (cache check, B-SCAN-12) ────────────
    t0 = time.time()
    try:
        files_to_scan = _select_files(options, file_langs, cache_path)
    except Exception as e:
        logger.error(f"[B-SCAN-14] File selection failed: {e}")
        errors.append(f"select_files: {e}")
        files_to_scan = sorted(file_langs.keys())
    timings["select_files"] = time.time() - t0

    # ── Dry run: return file list without scanning ─────────────────
    if options.dry_run:
        report = ScanReport(
            exit_code=0,
            files_scanned=0,
            scan_duration=time.time() - t_start,
            coverage_flags={
                "dry_run": True,
                "files_to_scan": files_to_scan,
                "total_files": len(file_langs),
            },
        ) if ScanReport else None
        return report

    # ── Phase 2: Build dependency graph ────────────────────────────
    t0 = time.time()
    try:
        graph = _build_graph(repo_path, file_langs)
    except Exception as e:
        logger.error(f"[B-SCAN-14] Graph build failed: {e}")
        errors.append(f"graph_build: {e}")
        graph = {f: [] for f in file_langs}
    timings["build_graph"] = time.time() - t0

    # ── Phase 3: Graph metrics (B-SCAN-04) ─────────────────────────
    t0 = time.time()
    per_file_metrics = {}
    global_metrics = None
    try:
        if compute_graph_metrics is not None:
            per_file_metrics, global_metrics = compute_graph_metrics(dict(graph))
    except Exception as e:
        logger.error(f"[B-SCAN-14] Graph metrics failed: {e}")
        errors.append(f"graph_metrics: {e}")
    timings["graph_metrics"] = time.time() - t0

    # ── Phase 4: Priority rank (B-SCAN-05) ─────────────────────────
    t0 = time.time()
    ranked = []
    simple = _simple_graph(graph)
    try:
        if rank_files is not None and per_file_metrics:
            ranked = rank_files(per_file_metrics, simple)
    except Exception as e:
        logger.error(f"[B-SCAN-14] Priority ranking failed: {e}")
        errors.append(f"priority_rank: {e}")
    timings["priority_rank"] = time.time() - t0

    # ── Phase 5: Load bibles (B-SCAN-01+02) ────────────────────────
    t0 = time.time()
    bibles = {}
    try:
        if options.bible_dir:
            bibles = _load_bibles(options.bible_dir, file_langs)
    except Exception as e:
        logger.error(f"[B-SCAN-14] Bible loading failed: {e}")
        errors.append(f"bible_load: {e}")
    timings["load_bibles"] = time.time() - t0

    # ── Phase 6: Determine LLM files ──────────────────────────────
    # top 20% by priority, or max_llm_files
    if ranked and not options.no_llm:
        n_llm = options.max_llm_files
        if n_llm <= 0:
            n_llm = max(1, len(ranked) // 5)
        llm_files = [r.file for r in ranked[:n_llm] if r.file in set(files_to_scan)]
    else:
        llm_files = []

    # ── Phase 7: LLM scan (B-SCAN-06) + Regex scan (B-SCAN-07) ───
    t0 = time.time()
    llm_findings = []
    regex_findings = []

    # Regex pass on all files to scan
    try:
        if regex_scan_file_content is not None:
            for fpath in files_to_scan:
                lang = file_langs.get(fpath, "")
                content = _read_file(repo_path, fpath)
                if not content:
                    continue
                bible_entries = bibles.get(lang, [])
                matches = regex_scan_file_content(content, lang, bible_entries, filename=fpath)
                regex_findings.extend(matches)
    except Exception as e:
        logger.error(f"[B-SCAN-14] Regex scan failed: {e}")
        errors.append(f"regex_scan: {e}")
    timings["regex_scan"] = time.time() - t0

    # LLM pass (skipped if --no-llm or no LLM available)
    t0 = time.time()
    if not options.no_llm and llm_scan_file is not None and llm_files:
        try:
            for fpath in llm_files:
                lang = file_langs.get(fpath, "")
                content = _read_file(repo_path, fpath)
                if not content:
                    continue
                bible_mn = ""  # LLM bible loaded separately if available
                findings = llm_scan_file(fpath, content, lang, bible_mn)
                llm_findings.extend(findings)
        except Exception as e:
            logger.error(f"[B-SCAN-14] LLM scan failed (degrading to regex+AST): {e}")
            errors.append(f"llm_scan: {e}")
    timings["llm_scan"] = time.time() - t0

    # ── Phase 8: AST confirm (B-SCAN-08) ──────────────────────────
    t0 = time.time()
    ast_verdicts = []
    try:
        if ast_analyze_findings is not None:
            # Build finding dicts for AST analysis
            all_raw_findings = []
            for rm in regex_findings:
                all_raw_findings.append({
                    "file": getattr(rm, "file", ""),
                    "line": getattr(rm, "line", 0),
                    "pattern_id": getattr(rm, "pattern_id", ""),
                    "severity": getattr(rm, "severity", "INFO"),
                })
            for lf in llm_findings:
                all_raw_findings.append({
                    "file": getattr(lf, "file", ""),
                    "line": getattr(lf, "line", 0),
                    "pattern_id": getattr(lf, "type", ""),
                    "severity": getattr(lf, "severity", "INFO"),
                })

            # Read file contents for AST
            file_contents = {}
            files_needed = {f["file"] for f in all_raw_findings}
            for fpath in files_needed:
                content = _read_file(repo_path, fpath)
                if content:
                    file_contents[fpath] = content

            if all_raw_findings:
                ast_verdicts = ast_analyze_findings(all_raw_findings, file_contents)
    except Exception as e:
        logger.error(f"[B-SCAN-14] AST analysis failed: {e}")
        errors.append(f"ast_analyze: {e}")
    timings["ast_analyze"] = time.time() - t0

    # ── Phase 9: Merge (B-SCAN-09) ────────────────────────────────
    t0 = time.time()
    merged = []
    try:
        if merge_findings is not None:
            merged = merge_findings(
                llm_findings=llm_findings,
                regex_findings=regex_findings,
                ast_verdicts=ast_verdicts,
            )
    except Exception as e:
        logger.error(f"[B-SCAN-14] Merge failed: {e}")
        errors.append(f"merge: {e}")
    timings["merge"] = time.time() - t0

    # ── Phase 10: Propagation (B-SCAN-10) ─────────────────────────
    t0 = time.time()
    propagation_result = None
    try:
        if propagate_findings is not None and merged:
            # Build finding dicts for propagation
            prop_findings = []
            for i, mf in enumerate(merged):
                prop_findings.append({
                    "id": f"F-{i}",
                    "file": mf.file,
                    "severity": mf.severity,
                })
            # Build file_metrics dict for propagation
            fm_dict = {}
            for fname in file_langs:
                fm = per_file_metrics.get(fname)
                fm_dict[fname] = {
                    "loc": len(_read_file(repo_path, fname).splitlines()) if fm else 0,
                    "temperature": getattr(fm, "temperature", 0.0) if fm else 0.0,
                    "degree": getattr(fm, "r0", 0) if fm else 0,
                }
            propagation_result = propagate_findings(
                prop_findings, simple, fm_dict, method=options.propagation_method,
            )
    except Exception as e:
        logger.error(f"[B-SCAN-14] Propagation failed: {e}")
        errors.append(f"propagation: {e}")
    timings["propagation"] = time.time() - t0

    # ── Phase 11: Dynamic detect (B-SCAN-11) ──────────────────────
    t0 = time.time()
    dynamic_imports = []
    try:
        if dyn_scan_content is not None:
            for fpath in files_to_scan:
                lang = file_langs.get(fpath, "")
                content = _read_file(repo_path, fpath)
                if not content:
                    continue
                result = dyn_scan_content(content, file_path=fpath, language=lang)
                dynamic_imports.extend(result.findings)
    except Exception as e:
        logger.error(f"[B-SCAN-14] Dynamic detection failed: {e}")
        errors.append(f"dynamic_detect: {e}")
    timings["dynamic_detect"] = time.time() - t0

    # ── Phase 12: Report (B-SCAN-13) ──────────────────────────────
    t0 = time.time()
    scan_duration = time.time() - t_start
    try:
        if generate_report is not None:
            # Convert propagation result to dict for report
            prop_dict = None
            if propagation_result is not None:
                try:
                    prop_dict = asdict(propagation_result)
                except Exception:
                    prop_dict = {
                        "regime": getattr(propagation_result, "regime", "local"),
                        "lambda_c": getattr(propagation_result, "lambda_c", 0.0),
                        "percolation_pc": getattr(propagation_result, "percolation_pc", 0.0),
                        "patch_plan": getattr(propagation_result, "patch_order", []),
                    }

            # Convert global metrics to dict
            gm_dict = None
            if global_metrics is not None:
                try:
                    gm_dict = asdict(global_metrics)
                except Exception:
                    gm_dict = vars(global_metrics)

            report = generate_report(
                findings=merged,
                propagation_result=prop_dict,
                dynamic_imports=dynamic_imports,
                graph_metrics=gm_dict,
                scan_duration=scan_duration,
                files_scanned=len(files_to_scan),
                graph=simple,
            )
        else:
            report = ScanReport(
                findings=merged,
                exit_code=compute_exit_code(merged) if compute_exit_code else 0,
                scan_duration=scan_duration,
                files_scanned=len(files_to_scan),
            )
    except Exception as e:
        logger.error(f"[B-SCAN-14] Report generation failed: {e}")
        errors.append(f"report: {e}")
        report = ScanReport(
            exit_code=2 if merged else 0,
            scan_duration=scan_duration,
            files_scanned=len(files_to_scan),
        )
    timings["report"] = time.time() - t0

    # ── Phase 13: Update cache ────────────────────────────────────
    try:
        if update_cache is not None and not options.dry_run:
            hashes = _hash_all_files(repo_path, {f: file_langs[f] for f in files_to_scan if f in file_langs})
            for fpath, sha in hashes.items():
                # Extract findings for this file
                file_findings = [
                    {"type": getattr(mf, "type", ""), "line": getattr(mf, "line", 0),
                     "severity": getattr(mf, "severity", "")}
                    for mf in merged if getattr(mf, "file", "") == fpath
                ]
                update_cache(cache_path, fpath, sha, file_findings)
    except Exception as e:
        logger.error(f"[B-SCAN-14] Cache update failed: {e}")
        errors.append(f"cache_update: {e}")

    # ── Phase 14: Log scan ────────────────────────────────────────
    try:
        by_severity = {}
        for mf in merged:
            sev = getattr(mf, "severity", "INFO")
            by_severity[sev] = by_severity.get(sev, 0) + 1

        _log_scan(log_path, {
            "start": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "duration": round(scan_duration, 3),
            "files_scanned": len(files_to_scan),
            "total_files": len(file_langs),
            "findings_total": len(merged),
            "findings_by_severity": by_severity,
            "errors": errors,
            "timings": {k: round(v, 3) for k, v in timings.items()},
            "options": {
                "full": options.full,
                "incremental": options.incremental,
                "dry_run": options.dry_run,
                "no_llm": options.no_llm,
            },
        })
    except Exception as e:
        logger.warning(f"[B-SCAN-14] Scan logging failed: {e}")

    return report


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Convenience wrapper
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scan_repo(repo_path: str, **kwargs):
    """Convenience wrapper: scan a repo with keyword options.

    Args:
        repo_path: path to the repository root
        **kwargs: any ScanOptions field (full, incremental, dry_run, no_llm, etc.)

    Returns:
        ScanReport
    """
    options = ScanOptions(repo_path=repo_path, **kwargs)
    return scan(options)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Muninn Security Scanner — B-SCAN-14 Orchestrator")
    parser.add_argument("repo_path", help="Path to the repository to scan")
    parser.add_argument("--full", action="store_true", help="Force full rescan")
    parser.add_argument("--incremental", action="store_true", default=True,
                        help="Incremental scan (default)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be scanned")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM pass")
    parser.add_argument("--bible-dir", help="Bible directory path")
    parser.add_argument("--output-dir", help="Output directory for reports")
    parser.add_argument("--propagation", default="auto", choices=["auto", "debtrank", "heat_kernel"],
                        help="Propagation method (default: auto)")

    args = parser.parse_args()

    opts = ScanOptions(
        repo_path=args.repo_path,
        full=args.full,
        incremental=args.incremental,
        dry_run=args.dry_run,
        no_llm=args.no_llm,
        bible_dir=args.bible_dir,
        output_dir=args.output_dir,
        propagation_method=args.propagation,
    )

    result = scan(opts)

    if result is not None and report_to_markdown is not None:
        print(report_to_markdown(result))
    elif result is not None:
        print(f"Exit code: {result.exit_code}")
        print(f"Files scanned: {result.files_scanned}")
        print(f"Findings: {len(result.findings)}")

    sys.exit(result.exit_code if result else 0)
