"""Muninn MCP server — FastMCP scaffold + first tool `mycelium_recall_local`.

Chunk B.1 of docs/BATTLE_PLAN_MASTER_MCP.md. First step of Phase B (MCP
server core, the killer feature). This module is a PURE ADAPTER over
Mycelium.spread_activation — no new algorithmic logic, hence no forge
property tests required (RULE 5 N/A : not under engine/core/).

Architecture:
  - FastMCP app named "muninn"
  - Transport: stdio (Claude Code spawns the process)
  - 1 tool exposed: mycelium_recall_local (this chunk B.1)
  - Future chunks will add: mycelium_recall_meta (B.3), mycelium_recall
    with auto routing (B.3), tree_get_root (B.4), bugs_list (B.5), etc.

Logging: stderr ONLY. stdout is reserved for the MCP JSON-RPC protocol —
any stray print() to stdout corrupts the wire format.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "muninn.mcp requires the 'mcp' package. "
        "Install with: pip install 'muninn-memory[mcp]'"
    ) from exc


# stderr-only logger (stdout = MCP protocol, must stay clean)
_log = logging.getLogger("muninn.mcp")
if not _log.handlers:
    _handler = logging.StreamHandler(sys.stderr)
    _handler.setFormatter(logging.Formatter(
        "%(asctime)s [muninn.mcp] %(levelname)s: %(message)s"
    ))
    _log.addHandler(_handler)
    _log.setLevel(logging.INFO)


# Hard caps — protect Claude's context window and avoid pathological queries.
TOP_K_MAX = 100
TOP_K_MIN = 1
HOPS_MAX = 3
HOPS_MIN = 1

# Tool result cap — a tool response lives in the current message (not the
# system prompt cache), so Claude tolerates a bit more than the SessionStart
# hook (40K). We cap at 60K chars (~15K tokens) with a truncated sentinel.
TREE_TOOL_MAX_CHARS = 60_000

# Branch name validation — anti path-traversal. Matches the Muninn convention
# `root` / `bNN` / arbitrary safe identifiers.
_BRANCH_NAME_RE = re.compile(r"^[A-Za-z0-9_]{1,64}$")


# ── Chunk B.3 dual-mycelium routing thresholds ──────────────────────────────
# Defaults validated by an 11-source deep audit (Collins-Loftus 1975, Anderson
# ACT-R, Weaviate/Pinecone hybrid search, Cormack 2009 RRF, Liu 2024 lost-in-
# the-middle, Anthropic Contextual Retrieval 2024, BEIR/MTEB).
# All overridable via env vars so users can calibrate without code changes.

THRESHOLD_LOCAL_STRONG = float(os.environ.get("MUNINN_DUAL_LOCAL_STRONG", "4.0"))
ALPHA_LOCAL = float(os.environ.get("MUNINN_DUAL_LOCAL_WEIGHT", "0.7"))
BETA_META = float(os.environ.get("MUNINN_DUAL_META_WEIGHT", "0.3"))
TOP_K_DEFAULT = int(os.environ.get("MUNINN_DUAL_TOP_K", "10"))
FUSION_METHOD = os.environ.get("MUNINN_DUAL_FUSION", "linear")  # "linear" | "rrf"

# RRF constant (Cormack, Clarke & Buettcher SIGIR 2009).
RRF_K = 60


def _resolve_repo_path(repo_path: str | None) -> Path:
    """Resolve the target repo: explicit arg > MUNINN_REPO env > cwd."""
    if repo_path:
        return Path(repo_path).resolve()
    env_repo = os.environ.get("MUNINN_REPO")
    if env_repo:
        return Path(env_repo).resolve()
    return Path.cwd().resolve()


def _tokenize_query(query: str) -> list[str]:
    """Extract word-like tokens (>=3 chars) from the free-text query.

    Same heuristic as muninn boot's query expansion (Park et al. 2023 style).
    """
    return [w.lower() for w in re.findall(r"[A-Za-zÀ-ÿ]{3,}", query or "")]


def _recall_local_impl(
    query: str,
    top_k: int = 10,
    repo_path: str | None = None,
    hops: int = 2,
) -> dict:
    """Pure-Python implementation of the mycelium_recall_local tool.

    Factored out of the FastMCP @tool wrapper so that tests can call it
    directly without spinning up a stdio subprocess.

    Returns a JSON-serializable dict:
      {
        "query": str,
        "results": [{"concept": str, "activation": float, "hops": int}],
        "elapsed_ms": float,
        "source": "local",
        "repo_path": str,
      }

    Raises:
        ValueError if repo_path is not a Muninn-bootstrapped project
            (i.e. no .muninn/ directory).
    """
    start = time.time()

    # Clamp bounds so the tool can never blow up Claude's context window.
    top_k = max(TOP_K_MIN, min(TOP_K_MAX, int(top_k)))
    hops = max(HOPS_MIN, min(HOPS_MAX, int(hops)))

    repo = _resolve_repo_path(repo_path)
    if not (repo / ".muninn").exists():
        raise ValueError(
            f"{repo} is not a Muninn-bootstrapped project (no .muninn/ "
            f"directory). Run `muninn init` in the repo first."
        )

    # Lazy-import Mycelium so the bare `import muninn.mcp` does not load
    # the entire engine (~24K LOC). Server boot stays fast.
    _engine_core = Path(__file__).resolve().parent.parent.parent / "engine" / "core"
    if str(_engine_core) not in sys.path:
        sys.path.insert(0, str(_engine_core))
    from mycelium import Mycelium  # noqa: E402

    seeds = _tokenize_query(query)
    results: list[dict] = []

    if not seeds:
        elapsed_ms = (time.time() - start) * 1000.0
        return {
            "query": query,
            "results": [],
            "elapsed_ms": round(elapsed_ms, 2),
            "source": "local",
            "repo_path": str(repo),
        }

    try:
        m = Mycelium(repo)
    except (sqlite3.OperationalError, OSError) as exc:
        _log.warning("mycelium open failed: %s", exc)
        elapsed_ms = (time.time() - start) * 1000.0
        return {
            "query": query,
            "results": [],
            "elapsed_ms": round(elapsed_ms, 2),
            "source": "local",
            "repo_path": str(repo),
            "error": f"db_unavailable: {type(exc).__name__}",
        }

    try:
        activated = m.spread_activation(seeds, hops=hops, top_n=top_k)
    except sqlite3.OperationalError as exc:
        # DB locked by another writer — degrade gracefully.
        _log.warning("mycelium db locked: %s", exc)
        activated = []
    except Exception as exc:  # noqa: BLE001 — never crash the MCP tool
        _log.exception("spread_activation failed: %s", exc)
        activated = []
    finally:
        try:
            m.close()
        except Exception:
            pass

    for concept, activation in activated[:top_k]:
        results.append({
            "concept": str(concept),
            "activation": round(float(activation), 4),
            "hops": hops,
        })

    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "query": query,
        "results": results,
        "elapsed_ms": round(elapsed_ms, 2),
        "source": "local",
        "repo_path": str(repo),
    }


# ── Chunk B.3 dual-mycelium routing (read-only meta access) ─────────────────


def _resolve_meta_db_path() -> Path:
    """Resolve the meta_mycelium.db path: MUNINN_META_PATH > ~/.muninn/.

    MUNINN_META_PATH (if set) points to the DIRECTORY containing
    meta_mycelium.db, NOT the file itself — matches mycelium_meta.py convention.
    """
    env_dir = os.environ.get("MUNINN_META_PATH")
    if env_dir:
        return Path(env_dir).expanduser().resolve() / "meta_mycelium.db"
    return Path.home() / ".muninn" / "meta_mycelium.db"


def _tokenize_for_meta(query: str) -> list[str]:
    """Same tokenization as the local recall — keeps the two sides aligned."""
    return _tokenize_query(query)


def _recall_meta_impl(
    query: str,
    top_k: int = 10,
    hops: int = 2,
) -> dict:
    """Read-only query into the meta-mycelium (federation cross-repo).

    Uses the MyceliumDB neighbor lookup directly — no spread_activation
    on the meta graph (it has 7.5M edges; full 2-hop would be too expensive).
    Falls back gracefully when the meta DB is absent or locked: returns
    `{results: [], error: "meta_unavailable" | "meta_locked"}` instead of
    raising — so the auto-router can degrade to local-only.
    """
    start = time.time()
    top_k = max(TOP_K_MIN, min(TOP_K_MAX, int(top_k)))
    meta_db_path = _resolve_meta_db_path()

    if not meta_db_path.exists():
        return {
            "query": query,
            "results": [],
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
            "source": "meta",
            "meta_path": str(meta_db_path),
            "error": "meta_unavailable",
        }

    seeds = _tokenize_for_meta(query)
    if not seeds:
        return {
            "query": query,
            "results": [],
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
            "source": "meta",
            "meta_path": str(meta_db_path),
        }

    # Open the meta DB read-only via SQLite URI. We bypass MyceliumDB.__init__
    # so we don't trigger any schema migrations or session-start side-effects.
    aggregated: dict[str, float] = {}
    seed_set = set(seeds)
    try:
        conn = sqlite3.connect(
            f"file:{meta_db_path}?mode=ro",
            uri=True, timeout=2.0,
        )
        try:
            placeholders = ",".join("?" for _ in seeds)
            cursor = conn.execute(
                f"""
                SELECT c1.name, c2.name, e.count
                FROM edges e
                JOIN concepts c1 ON c1.id = e.a
                JOIN concepts c2 ON c2.id = e.b
                WHERE c1.name IN ({placeholders}) OR c2.name IN ({placeholders})
                ORDER BY e.count DESC
                LIMIT ?
                """,
                seeds + seeds + [top_k * 4],
            )
            rows = cursor.fetchall()
            # Aggregate neighbors by name, summing edge counts.
            for a_name, b_name, count in rows:
                neighbor = b_name if a_name in seed_set else a_name
                if neighbor in seed_set:
                    continue  # skip self-references
                aggregated[neighbor] = aggregated.get(neighbor, 0.0) + float(count)
        finally:
            conn.close()
    except sqlite3.OperationalError as exc:
        _log.warning("meta DB locked or unreadable: %s", exc)
        return {
            "query": query,
            "results": [],
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
            "source": "meta",
            "meta_path": str(meta_db_path),
            "error": "meta_locked",
        }
    except Exception as exc:
        _log.exception("meta query failed: %s", exc)
        return {
            "query": query,
            "results": [],
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
            "source": "meta",
            "meta_path": str(meta_db_path),
            "error": f"meta_error: {type(exc).__name__}",
        }

    # Normalize aggregated counts onto [0, 1] so they're comparable with the
    # local spread_activation outputs.
    if aggregated:
        max_count = max(aggregated.values())
        if max_count > 0:
            for k_ in aggregated:
                aggregated[k_] = aggregated[k_] / max_count

    sorted_pairs = sorted(aggregated.items(), key=lambda kv: kv[1], reverse=True)
    results = [
        {"concept": name, "activation": round(score, 4), "hops": hops}
        for name, score in sorted_pairs[:top_k]
    ]
    return {
        "query": query,
        "results": results,
        "elapsed_ms": round((time.time() - start) * 1000.0, 2),
        "source": "meta",
        "meta_path": str(meta_db_path),
    }


def _compute_strength_total(results: list[dict]) -> float:
    """Sum of activations — the local-confidence proxy used by `auto`."""
    return float(sum(float(r.get("activation", 0.0)) for r in results))


def _merge_results(
    local_results: list[dict],
    meta_results: list[dict],
    fusion: str,
    alpha: float,
    beta: float,
    top_k: int,
) -> list[dict]:
    """Merge local + meta results into a single ranked list.

    - "linear" : min-max normalize each side, then `score = α·local + β·meta`
                 per concept (lowercased dedup key). Robust to magnitude
                 differences between local (94k edges) and meta (7.5M).
    - "rrf"    : Reciprocal Rank Fusion (Cormack 2009).
                 `score = α/(K+rank_local) + β/(K+rank_meta)` with K=60.
                 Pure rank-based; raw activations ignored. Most robust to
                 magnitude gaps but loses score-level granularity.
    """
    if fusion not in ("linear", "rrf"):
        fusion = "linear"

    # Index results by lowercased concept name (dedup key)
    local_map: dict[str, dict] = {}
    meta_map: dict[str, dict] = {}
    for r in local_results or []:
        key = str(r.get("concept", "")).lower()
        if key:
            local_map[key] = r
    for r in meta_results or []:
        key = str(r.get("concept", "")).lower()
        if key:
            meta_map[key] = r

    all_keys = set(local_map) | set(meta_map)
    if not all_keys:
        return []

    scored: dict[str, dict] = {}

    if fusion == "linear":
        # Min-max normalize each side onto [0, 1].
        def _norm(results, m):
            vals = [float(r.get("activation", 0.0)) for r in results]
            if not vals:
                return {}
            lo, hi = min(vals), max(vals)
            span = hi - lo if hi > lo else 1.0
            return {
                str(r.get("concept", "")).lower(): (float(r.get("activation", 0.0)) - lo) / span
                for r in results
            }

        local_norm = _norm(local_results or [], "local")
        meta_norm = _norm(meta_results or [], "meta")
        for key in all_keys:
            score = alpha * local_norm.get(key, 0.0) + beta * meta_norm.get(key, 0.0)
            base = local_map.get(key) or meta_map.get(key) or {}
            scored[key] = {
                "concept": base.get("concept", key),
                "activation": round(score, 4),
                "hops": base.get("hops", 2),
                "from": "both" if key in local_map and key in meta_map
                        else ("local" if key in local_map else "meta"),
            }
    else:  # rrf
        # Build rank maps: rank 0 = first place.
        def _ranks(results):
            return {str(r.get("concept", "")).lower(): i for i, r in enumerate(results or [])}

        local_rank = _ranks(local_results)
        meta_rank = _ranks(meta_results)
        for key in all_keys:
            score = 0.0
            if key in local_rank:
                score += alpha / (RRF_K + local_rank[key] + 1)
            if key in meta_rank:
                score += beta / (RRF_K + meta_rank[key] + 1)
            base = local_map.get(key) or meta_map.get(key) or {}
            scored[key] = {
                "concept": base.get("concept", key),
                "activation": round(score, 6),
                "hops": base.get("hops", 2),
                "from": "both" if key in local_map and key in meta_map
                        else ("local" if key in local_map else "meta"),
            }

    sorted_results = sorted(
        scored.values(), key=lambda d: d["activation"], reverse=True
    )
    return sorted_results[:top_k]


def _recall_dual_impl(
    query: str,
    scope: str = "auto",
    top_k: int = 10,
    hops: int = 2,
    repo_path: str | None = None,
    fusion: str | None = None,
    alpha: float | None = None,
    beta: float | None = None,
) -> dict:
    """Smart router: picks local-only / meta-only / both / auto based on `scope`.

    `auto` first queries local; if `sum(activations) >= THRESHOLD_LOCAL_STRONG`
    we trust local alone, otherwise we also query meta and merge the two
    via the configured fusion method.

    `fusion` / `alpha` / `beta` default to module constants (env-var driven).
    """
    start = time.time()
    if scope not in ("auto", "local", "meta", "both"):
        scope = "auto"
    top_k = max(TOP_K_MIN, min(TOP_K_MAX, int(top_k)))
    fusion = fusion or FUSION_METHOD
    alpha = ALPHA_LOCAL if alpha is None else float(alpha)
    beta = BETA_META if beta is None else float(beta)

    out: dict = {
        "query": query,
        "scope": scope,
        "results": [],
        "elapsed_ms": 0.0,
        "source": "",
        "scope_used": "",
        "fusion_used": None,
        "strength_local": None,
        "strength_meta": None,
        "repo_path": None,
        "meta_path": str(_resolve_meta_db_path()),
    }

    if scope == "local":
        r = _recall_local_impl(query=query, top_k=top_k,
                                repo_path=repo_path, hops=hops)
        out["results"] = r.get("results", [])
        out["source"] = "local"
        out["scope_used"] = "local"
        out["strength_local"] = _compute_strength_total(out["results"])
        out["repo_path"] = r.get("repo_path")
    elif scope == "meta":
        r = _recall_meta_impl(query=query, top_k=top_k, hops=hops)
        out["results"] = r.get("results", [])
        out["source"] = "meta"
        out["scope_used"] = "meta"
        out["strength_meta"] = _compute_strength_total(out["results"])
    elif scope == "both":
        rl = _recall_local_impl(query=query, top_k=top_k,
                                 repo_path=repo_path, hops=hops)
        rm = _recall_meta_impl(query=query, top_k=top_k, hops=hops)
        merged = _merge_results(
            rl.get("results", []), rm.get("results", []),
            fusion, alpha, beta, top_k,
        )
        out["results"] = merged
        out["source"] = "local+meta"
        out["scope_used"] = "both"
        out["fusion_used"] = fusion
        out["strength_local"] = _compute_strength_total(rl.get("results", []))
        out["strength_meta"] = _compute_strength_total(rm.get("results", []))
        out["repo_path"] = rl.get("repo_path")
    else:  # auto
        rl = _recall_local_impl(query=query, top_k=top_k,
                                 repo_path=repo_path, hops=hops)
        strength_local = _compute_strength_total(rl.get("results", []))
        out["strength_local"] = strength_local
        out["repo_path"] = rl.get("repo_path")
        if strength_local >= THRESHOLD_LOCAL_STRONG:
            out["results"] = rl.get("results", [])
            out["source"] = "local"
            out["scope_used"] = "auto→local"
        else:
            rm = _recall_meta_impl(query=query, top_k=top_k, hops=hops)
            out["strength_meta"] = _compute_strength_total(rm.get("results", []))
            if not rm.get("results"):
                # meta unavailable → fall back to local-only
                out["results"] = rl.get("results", [])
                out["source"] = "local"
                out["scope_used"] = "auto→local (meta_unavailable)"
            else:
                merged = _merge_results(
                    rl.get("results", []), rm.get("results", []),
                    fusion, alpha, beta, top_k,
                )
                out["results"] = merged
                out["source"] = "local+meta"
                out["scope_used"] = "auto→merged"
                out["fusion_used"] = fusion

    out["elapsed_ms"] = round((time.time() - start) * 1000.0, 2)
    return out


# ── Chunk B.2 tree tools (read-only) ─────────────────────────────────────────


def _load_tree_for_repo(repo: Path) -> dict:
    """Load <repo>/.muninn/tree/tree.json read-only (no side-effects).

    Deliberately bypasses engine/core/muninn_tree.read_node() which mutates
    `access_count`, updates `last_access`, calls `save_tree`, and triggers
    reconsolidation. The MCP tree tools must NOT change the Muninn state
    of Sky's repo just because Claude queried it.

    Raises:
        ValueError if repo is not Muninn-bootstrapped or tree.json missing.
    """
    tree_dir = repo / ".muninn" / "tree"
    if not tree_dir.exists() or not tree_dir.is_dir():
        raise ValueError(
            f"{repo} has no .muninn/tree/ directory — not a Muninn-bootstrapped "
            f"project. Run `muninn init` in the repo first."
        )
    tree_json = tree_dir / "tree.json"
    if not tree_json.exists():
        raise ValueError(
            f"{repo}/.muninn/tree/tree.json is missing. Re-run `muninn init` "
            f"or `muninn bootstrap` to regenerate."
        )
    try:
        return json.loads(tree_json.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{tree_json} is not valid JSON: {exc}") from exc


def _cap_with_marker(content: str, max_chars: int) -> tuple[str, bool]:
    """Truncate at last newline before max_chars + marker. Returns (text, truncated)."""
    if len(content) <= max_chars:
        return content, False
    marker = "\n…[truncated, content exceeds %d chars]" % max_chars
    slice_end = max(0, max_chars - len(marker))
    # Snap to the last newline to avoid cutting mid-line.
    cut = content.rfind("\n", 0, slice_end)
    if cut > 0:
        slice_end = cut
    return content[:slice_end] + marker, True


def _read_branch_file(repo: Path, file_name: str) -> str:
    """Read <repo>/.muninn/tree/<file_name>. Path traversal already guarded by
    branch_name regex upstream, but we double-check resolved path stays inside
    the tree dir as a belt-and-suspenders.
    """
    tree_dir = (repo / ".muninn" / "tree").resolve()
    target = (tree_dir / file_name).resolve()
    if not str(target).startswith(str(tree_dir)):
        raise ValueError(f"branch file {file_name!r} escapes the tree dir")
    if not target.exists():
        raise FileNotFoundError(str(target))
    return target.read_text(encoding="utf-8")


def _tree_get_root_impl(repo_path: str | None = None) -> dict:
    """Read-only fetch of <repo>/.muninn/tree/root.mn + its metadata."""
    start = time.time()
    repo = _resolve_repo_path(repo_path)
    tree = _load_tree_for_repo(repo)
    nodes = tree.get("nodes", {})
    root_meta = nodes.get("root")
    if root_meta is None:
        raise ValueError(f"{repo}/.muninn/tree/tree.json has no 'root' node")
    file_name = root_meta.get("file", "root.mn")
    try:
        content = _read_branch_file(repo, file_name)
    except FileNotFoundError as exc:
        raise ValueError(f"root.mn not found: {exc}") from exc
    capped, truncated = _cap_with_marker(content, TREE_TOOL_MAX_CHARS)
    metadata = {
        "lines": root_meta.get("lines"),
        "max_lines": root_meta.get("max_lines"),
        "last_access": root_meta.get("last_access"),
        "access_count": root_meta.get("access_count"),
        "tags": list(root_meta.get("tags", [])),
        "children": list(root_meta.get("children", [])),
        "hash": root_meta.get("hash"),
        "temperature": root_meta.get("temperature"),
    }
    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "node": "root",
        "content": capped,
        "metadata": metadata,
        "truncated": truncated,
        "repo_path": str(repo),
        "elapsed_ms": round(elapsed_ms, 2),
    }


def _tree_get_branch_impl(branch_name: str, repo_path: str | None = None) -> dict:
    """Read-only fetch of <repo>/.muninn/tree/<branch_name>.mn + metadata.

    `branch_name` is validated against ^[A-Za-z0-9_]{1,64}$ — anti path-traversal.
    If the branch doesn't exist, returns {error, available} instead of raising
    so Claude can recover (typically by calling tree_list_branches).
    """
    start = time.time()
    if not isinstance(branch_name, str) or not _BRANCH_NAME_RE.match(branch_name):
        raise ValueError(
            f"invalid branch_name {branch_name!r}: must match ^[A-Za-z0-9_]{{1,64}}$"
        )
    repo = _resolve_repo_path(repo_path)
    tree = _load_tree_for_repo(repo)
    nodes = tree.get("nodes", {})
    if branch_name not in nodes:
        elapsed_ms = (time.time() - start) * 1000.0
        return {
            "error": f"branch {branch_name!r} not in tree",
            "available": sorted(n for n in nodes.keys() if n != "root"),
            "repo_path": str(repo),
            "elapsed_ms": round(elapsed_ms, 2),
        }
    meta = nodes[branch_name]
    file_name = meta.get("file", f"{branch_name}.mn")
    try:
        content = _read_branch_file(repo, file_name)
    except FileNotFoundError:
        elapsed_ms = (time.time() - start) * 1000.0
        return {
            "error": f"branch {branch_name!r} file {file_name!r} missing on disk",
            "available": sorted(n for n in nodes.keys() if n != "root"),
            "repo_path": str(repo),
            "elapsed_ms": round(elapsed_ms, 2),
        }
    capped, truncated = _cap_with_marker(content, TREE_TOOL_MAX_CHARS)
    metadata = {
        "lines": meta.get("lines"),
        "max_lines": meta.get("max_lines"),
        "last_access": meta.get("last_access"),
        "access_count": meta.get("access_count"),
        "tags": list(meta.get("tags", [])),
        "hash": meta.get("hash"),
        "temperature": meta.get("temperature"),
        "usefulness": meta.get("usefulness"),
    }
    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "node": branch_name,
        "content": capped,
        "metadata": metadata,
        "truncated": truncated,
        "repo_path": str(repo),
        "elapsed_ms": round(elapsed_ms, 2),
    }


def _tree_list_branches_impl(repo_path: str | None = None) -> dict:
    """List all branches sorted by last_access DESC. Excludes 'root'.

    Lets Claude discover what branches exist before querying with tree_get_branch.
    """
    start = time.time()
    repo = _resolve_repo_path(repo_path)
    tree = _load_tree_for_repo(repo)
    nodes = tree.get("nodes", {})
    branches = []
    for name, meta in nodes.items():
        if name == "root":
            continue
        if not isinstance(meta, dict):
            continue
        branches.append({
            "name": name,
            "lines": meta.get("lines"),
            "last_access": meta.get("last_access", ""),
            "access_count": meta.get("access_count", 0),
            "temperature": meta.get("temperature"),
            "tags": list(meta.get("tags", []))[:5],
            "children_count": len(meta.get("children", [])),
        })
    branches.sort(key=lambda b: b.get("last_access") or "", reverse=True)
    elapsed_ms = (time.time() - start) * 1000.0
    return {
        "branches": branches,
        "count": len(branches),
        "repo_path": str(repo),
        "elapsed_ms": round(elapsed_ms, 2),
    }


def create_server() -> FastMCP:
    """Build the Muninn FastMCP app and register the chunk-B.1 + B.2 tools.

    Factored from main() so tests can introspect the registered tools
    without spawning a stdio process.
    """
    app = FastMCP("muninn")

    @app.tool()
    def mycelium_recall_local(
        query: str,
        top_k: int = 10,
        repo_path: str | None = None,
        hops: int = 2,
    ) -> dict:
        """Search Sky's *local* mycelium for concepts semantically related to query.

        Uses Collins & Loftus 1975 spreading activation over the project's
        .muninn/mycelium.db (NOT the meta-mycelium). Latency target <50ms.

        Args:
            query: free-text question or keywords ("BUG-104 spill tree").
            top_k: max results returned (1..100, default 10).
            repo_path: absolute path to a Muninn-bootstrapped project.
                       Defaults to $MUNINN_REPO env, then cwd.
            hops: spreading-activation propagation depth (1..3, default 2).

        Returns:
            {
              "query": str,
              "results": [{"concept": str, "activation": float, "hops": int}],
              "elapsed_ms": float,
              "source": "local",
              "repo_path": str,
            }

        Raises:
            ValueError if repo_path is not a Muninn-bootstrapped project.
        """
        return _recall_local_impl(
            query=query, top_k=top_k, repo_path=repo_path, hops=hops,
        )

    # ── Chunk B.3 dual-mycelium routing (local / meta / auto / both) ──

    @app.tool()
    def mycelium_recall_meta(
        query: str,
        top_k: int = 10,
        hops: int = 2,
    ) -> dict:
        """Search the *meta*-mycelium (federation cross-repo, ~7.5M edges).

        READ-ONLY query on ~/.muninn/meta_mycelium.db (or wherever
        MUNINN_META_PATH points). Use this when you want broader, cross-repo
        signal that the project-local mycelium (`mycelium_recall_local`)
        wouldn't have observed.

        Args:
            query: free-text query.
            top_k: max results (1..100, default 10).
            hops: included for symmetry with the local tool; meta query is
                  single-hop neighbor lookup, so this is informational only.

        Returns:
            {
              "query": str, "results": [{"concept", "activation", "hops"}],
              "elapsed_ms": float, "source": "meta", "meta_path": str,
              "error"?: "meta_unavailable" | "meta_locked"
            }

        Fail-safe: returns empty `results` with an `error` tag if the meta DB
        is missing or locked — never raises.
        """
        return _recall_meta_impl(query=query, top_k=top_k, hops=hops)

    @app.tool()
    def mycelium_recall(
        query: str,
        scope: str = "auto",
        top_k: int = 10,
        hops: int = 2,
        repo_path: str | None = None,
    ) -> dict:
        """Smart dual-mycelium router. Chooses local / meta / both / auto.

        Use this when you don't want to decide upfront whether the project
        mycelium has enough signal — the `auto` heuristic queries local
        first and only falls back to meta if `sum(activations) <
        THRESHOLD_LOCAL_STRONG` (default 4.0, configurable via
        MUNINN_DUAL_LOCAL_STRONG env var).

        Args:
            query: free-text query.
            scope: one of "auto" (default), "local", "meta", "both".
                   - "auto"  : local first, fallback merge if weak
                   - "local" : project mycelium only (B.1 equivalent)
                   - "meta"  : federation only (B.3 _meta tool equivalent)
                   - "both"  : force fusion of local + meta
            top_k: max results (1..100, default 10 — NDCG@10 standard).
            hops: spreading-activation depth for local (1..3).
            repo_path: defaults to $MUNINN_REPO env or cwd.

        Returns:
            {
              "query": str, "scope": str, "results": [...],
              "source": "local" | "meta" | "local+meta",
              "scope_used": "local" | "meta" | "both" | "auto→local" |
                            "auto→merged" | "auto→local (meta_unavailable)",
              "fusion_used": "linear" | "rrf" | None,
              "strength_local": float | None,
              "strength_meta": float | None,
              "elapsed_ms": float, "repo_path": str | None, "meta_path": str,
            }

        Tuning (env vars):
            MUNINN_DUAL_LOCAL_STRONG   (default 4.0)
            MUNINN_DUAL_LOCAL_WEIGHT   (default 0.7)
            MUNINN_DUAL_META_WEIGHT    (default 0.3)
            MUNINN_DUAL_TOP_K          (default 10)
            MUNINN_DUAL_FUSION         (default "linear", or "rrf")
        """
        return _recall_dual_impl(
            query=query, scope=scope, top_k=top_k, hops=hops,
            repo_path=repo_path,
        )

    # ── Chunk B.2 tree tools (read-only access to .muninn/tree/) ──

    @app.tool()
    def tree_get_root(repo_path: str | None = None) -> dict:
        """Read Muninn's root.mn — the project's compressed summary.

        Returns the content of <repo>/.muninn/tree/root.mn (the ~200 token
        machine-optimal snapshot listing project name, language, line count,
        focal file, mycelium state, top files, top keywords, recent commits)
        plus its metadata (children branches, tags, hash, last_access).

        Args:
            repo_path: absolute path to a Muninn-bootstrapped project. Defaults
                       to $MUNINN_REPO env, then cwd.

        Returns:
            {
              "node": "root",
              "content": str,                # the literal root.mn text
              "metadata": {
                "lines": int, "max_lines": int,
                "last_access": str, "access_count": int,
                "tags": [str], "children": [str],
                "hash": str, "temperature": float,
              },
              "truncated": bool,             # True if content > 60K chars
              "repo_path": str,
              "elapsed_ms": float,
            }

        Read-only: this tool does NOT update access_count or last_access on
        disk (unlike engine/core read_node). Safe to call from a query path.

        Raises:
            ValueError if repo_path is not a Muninn-bootstrapped project
            (no .muninn/tree/tree.json).
        """
        return _tree_get_root_impl(repo_path=repo_path)

    @app.tool()
    def tree_get_branch(branch_name: str, repo_path: str | None = None) -> dict:
        """Read one branch .mn (typically bNN) from Muninn's tree.

        Companion to tree_get_root. Use tree_list_branches first if you
        don't know which branches exist in this repo.

        Args:
            branch_name: branch identifier (e.g. "b02", "b07"). Must match
                         the regex ^[A-Za-z0-9_]{1,64}$ — anti path-traversal.
            repo_path: absolute path to a Muninn-bootstrapped project.

        Returns the same shape as tree_get_root, but `metadata` carries
        `usefulness` and `temperature` (no `children`). If the branch is
        absent, returns `{error, available, repo_path, elapsed_ms}` WITHOUT
        raising — so you can recover by listing branches and retrying.

        Read-only: no tree.json or mycelium.db modification.

        Raises:
            ValueError on invalid branch_name (path traversal attempt) or
            on a non-Muninn repo.
        """
        return _tree_get_branch_impl(branch_name=branch_name, repo_path=repo_path)

    @app.tool()
    def tree_list_branches(repo_path: str | None = None) -> dict:
        """List Muninn tree branches sorted by last_access DESC (hot first).

        Returns:
            {
              "branches": [
                {"name": "b02", "lines": 47, "last_access": "2026-05-11",
                 "access_count": 3, "temperature": 0.8, "tags": [...],
                 "children_count": 0},
                ...
              ],
              "count": int,
              "repo_path": str,
              "elapsed_ms": float,
            }

        Excludes "root" (use tree_get_root for that). Read-only.

        Raises:
            ValueError on non-Muninn repo.
        """
        return _tree_list_branches_impl(repo_path=repo_path)

    return app


def main() -> None:
    """Entry point for the `muninn-mcp` console_script and `python -m muninn.mcp`.

    Runs the FastMCP server over stdio (Claude Code spawns the process and
    talks JSON-RPC over stdin/stdout).
    """
    _log.info("Muninn MCP server starting (stdio transport)")
    app = create_server()
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
