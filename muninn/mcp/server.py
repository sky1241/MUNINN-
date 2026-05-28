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

# --- PIPELINE_TRACE block (removable, see docs/PIPELINE_TRACE_REMOVAL.md) ---  # PIPELINE_TRACE
try:  # PIPELINE_TRACE
    _muninn_root = Path(__file__).resolve().parent.parent.parent  # PIPELINE_TRACE
    _pt_core = str(_muninn_root / "engine" / "core")  # PIPELINE_TRACE
    if _pt_core not in sys.path: sys.path.insert(0, _pt_core)  # PIPELINE_TRACE
    from pipeline_trace import log_event  # PIPELINE_TRACE
except Exception:  # PIPELINE_TRACE
    def log_event(*a, **kw): pass  # PIPELINE_TRACE
# --- end PIPELINE_TRACE block ---  # PIPELINE_TRACE


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

# ── Auto-calibration (chunk C.0) ─────────────────────────────────────────────
# Sky asked (2026-05-11 nuit): "je veux pas calibrer pour moi, je veux un
# système qui se calibre en fonction de chaque client". So the 4.0 default
# stays as a sane bootstrap, but on EACH client we log strength_local on
# every scope=auto call, recompute the p75 every CALIBRATION_RECOMPUTE_EVERY
# samples, and persist the calibrated value under the client's `.muninn/`.
# Opt-out via MUNINN_DUAL_AUTO_CALIBRATE=0.

CALIBRATION_MIN_SAMPLES = 30
CALIBRATION_RECOMPUTE_EVERY = 30
CALIBRATION_PERCENTILE = 75
CALIBRATION_THRESHOLD_MIN = 0.5  # clamp lower bound (anti aberration)
CALIBRATION_THRESHOLD_MAX = 50.0  # clamp upper bound (anti aberration)


def _is_auto_calibrate_enabled() -> bool:
    return os.environ.get("MUNINN_DUAL_AUTO_CALIBRATE", "1") != "0"


def _calibration_log_path(repo: Path) -> Path:
    return repo / ".muninn" / "dual_mycelium_calibration.jsonl"


def _calibration_threshold_path(repo: Path) -> Path:
    return repo / ".muninn" / "dual_mycelium_threshold.json"


def _get_calibrated_threshold(repo: Path) -> float:
    """Return the auto-calibrated threshold for this client repo.

    - If auto-calibration is disabled (env var), always return the default.
    - If the threshold JSON file doesn't exist or is corrupt, return default.
    - Otherwise return the stored value clamped to [MIN, MAX].
    Never raises.
    """
    if not _is_auto_calibrate_enabled():
        return THRESHOLD_LOCAL_STRONG
    try:
        path = _calibration_threshold_path(repo)
        if not path.exists():
            return THRESHOLD_LOCAL_STRONG
        data = json.loads(path.read_text(encoding="utf-8"))
        value = float(data.get("threshold", THRESHOLD_LOCAL_STRONG))
        return max(CALIBRATION_THRESHOLD_MIN,
                   min(CALIBRATION_THRESHOLD_MAX, value))
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return THRESHOLD_LOCAL_STRONG


def _log_strength_to_calibration(repo: Path, strength: float) -> None:
    """Append one observation to the client's calibration jsonl.

    Fire-and-forget : any I/O error is swallowed. The MCP tool path must
    never raise just because the calibration log couldn't be written.
    """
    if not _is_auto_calibrate_enabled():
        return
    try:
        path = _calibration_log_path(repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps({
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "strength": round(float(strength), 4),
        })
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass  # fire-and-forget


def _recompute_calibration_if_needed(repo: Path, force: bool = False) -> bool:
    """Read the jsonl log and (re)write the threshold JSON when conditions met.

    Triggers a recompute when :
      - auto-calibration enabled
      - sample count >= CALIBRATION_MIN_SAMPLES
      - sample count % CALIBRATION_RECOMPUTE_EVERY == 0 (or `force=True`)

    Returns True if a new threshold was written, False otherwise.
    Never raises.
    """
    if not _is_auto_calibrate_enabled():
        return False
    try:
        log_path = _calibration_log_path(repo)
        if not log_path.exists():
            return False
        samples: list[float] = []
        for raw_line in log_path.read_text(encoding="utf-8").splitlines():
            if not raw_line.strip():
                continue
            try:
                entry = json.loads(raw_line)
                s = float(entry.get("strength", 0.0))
                samples.append(s)
            except (json.JSONDecodeError, ValueError, TypeError):
                continue  # skip corrupt lines
        n = len(samples)
        if n < CALIBRATION_MIN_SAMPLES:
            return False
        if not force and (n % CALIBRATION_RECOMPUTE_EVERY != 0):
            return False
        # Compute the percentile (no numpy dependency — keep it light)
        sorted_samples = sorted(samples)
        # Linear interpolation between closest ranks (numpy-compatible)
        k = (CALIBRATION_PERCENTILE / 100.0) * (n - 1)
        lo = int(k)
        hi = min(lo + 1, n - 1)
        frac = k - lo
        percentile_value = sorted_samples[lo] + frac * (sorted_samples[hi] - sorted_samples[lo])
        clamped = max(CALIBRATION_THRESHOLD_MIN,
                      min(CALIBRATION_THRESHOLD_MAX, percentile_value))
        out = {
            "threshold": round(clamped, 4),
            "samples": n,
            "percentile": CALIBRATION_PERCENTILE,
            "raw_percentile_value": round(percentile_value, 4),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        path = _calibration_threshold_path(repo)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic-ish write
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
        os.replace(str(tmp), str(path))
        return True
    except Exception:
        return False


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

    Same heuristic as muninn-mem boot's query expansion (Park et al. 2023 style).
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
    log_event("pipeline.mcp.recall_local.begin", {})  # PIPELINE_TRACE
    start = time.time()

    # Clamp bounds so the tool can never blow up Claude's context window.
    top_k = max(TOP_K_MIN, min(TOP_K_MAX, int(top_k)))
    hops = max(HOPS_MIN, min(HOPS_MAX, int(hops)))

    repo = _resolve_repo_path(repo_path)
    if not (repo / ".muninn").exists():
        raise ValueError(
            f"{repo} is not a Muninn-bootstrapped project (no .muninn/ "
            f"directory). Run `muninn-mem init` in the repo first."
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


# ── G.1 (2026-05-12): universal degree-based stopword filter at query time ──
#
# ⚠️ DEAD CODE — DÉSACTIVÉ PAR DÉFAUT, NE PAS RÉACTIVER SANS LIRE CECI ⚠️
# (flag posé 2026-05-28 après 2h perdues à re-diagnostiquer le même piège)
#
# POURQUOI ON A CRÉÉ G.1 (12 mai) :
#   recall_meta("compression") renvoyait `est/les/pas` (stopwords FR) parce
#   que _STOPWORDS dans mycelium.py était anglais-only. Au lieu d'ajouter les
#   mots FR à la main, on a voulu un filtre "intelligent universel" : virer
#   les concepts top-N% par degré, en supposant "haut degré = stopword".
#
# POURQUOI C'EST DEAD CODE (désactivé f44fdb5 le 26 mai, confirmé mort le 28) :
#   L'hypothèse "haut degré = stopword" est FAUSSE. Les concepts CENTRAUX
#   légitimes (`fleet`, `code`, `muninn`, `claude`) ont aussi un haut degré.
#   Le filtre ne sait pas les distinguer. Sur la petite DB pc2 (2427 concepts)
#   `fleet` était rang 13 = top 0.5% → filtré comme stopword alors que c'est
#   LE concept-domaine #1. Le cousin pc2 a vu recall_meta('fleet') = 0 result
#   et a désactivé (default 0.05 → 0.0).
#
# LE VRAI FIX (2026-05-28) : compléter _STOPWORDS (mycelium.py) avec les mots
#   grammaticaux FR + EN manquants. Filtre par SENS (liste de mots-grammaire),
#   pas par degré → `fleet`/`code` survivent, `est`/`and`/`the` sont bloqués
#   À L'ENTRÉE (observe_text), pas juste au query-time. Plus simple, plus
#   correct. Le "truc intelligent topologique" était sur-ingénié.
#
# NE PAS réactiver G.1 (env var MUNINN_RECALL_STOPWORD_PERCENTILE > 0) sauf
# si tu as une whitelist de concepts-domaine à protéger. Sinon tu re-casses
# fleet/code/claude exactement comme le 26 mai.

def _recall_stopword_percentile() -> float:
    """Read MUNINN_RECALL_STOPWORD_PERCENTILE (default 0.0). 0 disables filter.

    Bounded to [0.0, 0.5] — beyond 50% we'd strip the entire result list.

    ⚠️ DEAD CODE depuis 2026-05-28 — voir le bloc de commentaire au-dessus.
    Default 0.0 = filtre désactivé. Le vrai filtrage stopword se fait
    maintenant À L'ENTRÉE via _STOPWORDS dans mycelium.py (filtre par sens,
    pas par degré). Réactiver ce filtre degree-based re-casse les concepts
    centraux légitimes (`fleet`, `code`, `muninn`) sur petites DBs.

    PHASE 1.5 fix (2026-05-26 pc2 audit finding): default lowered 0.05 → 0.0.
    Reason: 5% percentile filter wipes legitimate concepts on small DBs.
    Example pc2 meta DB (2427 concepts): `fleet` rank 13 = top 0.5% =
    filtered as "stopword" even though it's the user's primary domain
    concept. The percentile-based approach fundamentally fails on small DBs.
    """
    try:
        pct = float(os.environ.get("MUNINN_RECALL_STOPWORD_PERCENTILE", "0.0"))
    except ValueError:
        pct = 0.0
    return max(0.0, min(0.5, pct))


def _high_degree_set_from_meta(meta_db_path: Path, percentile: float) -> set[str]:
    """Compute the top-`percentile` highest-degree concept names in the meta DB.

    Mirrors mycelium_activation._get_high_degree_concepts() but for an
    arbitrary SQLite DB opened read-only. Returns lowercase concept names.

    percentile=0 short-circuits to an empty set (filter disabled).
    """
    if percentile <= 0.0 or not meta_db_path.exists():
        return set()
    try:
        conn = sqlite3.connect(
            f"file:{meta_db_path}?mode=ro",
            uri=True, timeout=2.0,
        )
        try:
            row = conn.execute("SELECT COUNT(*) FROM concepts").fetchone()
            n_concepts = row[0] if row else 0
            if n_concepts < 20:
                return set()
            cutoff = max(1, int(n_concepts * percentile))
            rows = conn.execute("""
                SELECT c.name, SUM(d.cnt) AS degree
                FROM (
                    SELECT a AS cid, COUNT(*) AS cnt FROM edges GROUP BY a
                    UNION ALL
                    SELECT b AS cid, COUNT(*) AS cnt FROM edges GROUP BY b
                ) AS d
                JOIN concepts c ON c.id = d.cid
                GROUP BY d.cid
                ORDER BY degree DESC
            """).fetchall()
        finally:
            conn.close()
    except sqlite3.OperationalError:
        return set()
    if not rows:
        return set()
    idx = min(cutoff - 1, len(rows) - 1)
    threshold = max(rows[idx][1], 20)
    return {str(name).lower() for name, deg in rows if deg >= threshold}


def _filter_high_degree(results: list[dict], hub_set: set[str]) -> list[dict]:
    """Drop entries from `results` whose lowercased concept name is in hub_set."""
    if not hub_set:
        return results
    return [r for r in results
            if str(r.get("concept", "")).lower() not in hub_set]


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
    log_event("pipeline.mcp.recall_meta.begin", {})  # PIPELINE_TRACE
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
    # G.1: build candidate list larger than top_k so the filter has room to work.
    raw_results = [
        {"concept": name, "activation": round(score, 4), "hops": hops}
        for name, score in sorted_pairs[:top_k * 2]
    ]
    pct = _recall_stopword_percentile()
    hub_set = _high_degree_set_from_meta(meta_db_path, pct)
    results = _filter_high_degree(raw_results, hub_set)[:top_k]
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
    log_event("pipeline.mcp.recall_dual.begin", {})  # PIPELINE_TRACE
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
        # Chunk C.0: per-client auto-calibration. Use the calibrated threshold
        # if available, fall back to the global default otherwise.
        repo_resolved = _resolve_repo_path(repo_path)
        threshold_used = _get_calibrated_threshold(repo_resolved)
        out["threshold_used"] = round(threshold_used, 4)
        # Log this observation so the threshold can self-calibrate over time.
        _log_strength_to_calibration(repo_resolved, strength_local)
        if strength_local >= threshold_used:
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
        # Recompute calibration periodically (fire-and-forget).
        _recompute_calibration_if_needed(repo_resolved)

    out["elapsed_ms"] = round((time.time() - start) * 1000.0, 2)
    return out


# ── Chunk B.5 runbook tools (read-only CHANGELOG / WINTER_TREE / MASTER_MCP) ─


# Whitelist of allowed runbook documents (anti path-traversal).
# (path_relative_to_repo, parser_type)
_RUNBOOK_DOCS = {
    "changelog":   ("CHANGELOG.md", "h2_date"),
    "winter_tree": ("WINTER_TREE.md", "h2_title"),
    "battle_plan": ("docs/BATTLE_PLAN_MASTER_MCP.md", "h2_numbered"),
}

_DOC_NAME_RE = re.compile(r"^[a-z_]{1,32}$")
_SECTION_ID_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,79}$")
_H2_HEADER_RE = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_DATE_PREFIX_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})(?:\s*\(([^)]+)\))?")
_NUMBERED_PREFIX_RE = re.compile(r"^(\d+)\.\s")
RUNBOOK_TOOL_MAX_CHARS = 40_000


def _slugify_runbook(text: str) -> str:
    """Lower + non-alnum→'-' + collapse repeated dashes + trim dashes."""
    s = text.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s[:80] or "section"


def _resolve_runbook_path(document: str, repo: Path) -> Path:
    """Returns the absolute path to the runbook document, validated."""
    if document not in _RUNBOOK_DOCS:
        raise ValueError(
            f"invalid document {document!r}. Allowed: {sorted(_RUNBOOK_DOCS)}"
        )
    rel, _ = _RUNBOOK_DOCS[document]
    return repo / rel


def _parse_runbook_sections(content: str, doc_type: str) -> list[dict]:
    """Parse runbook content into sections by H2 headers.

    Returns list of dicts with: {id, title, line, char_start, char_end}.
    `id` slug depends on doc_type:
      - h2_date     : "YYYY-MM-DD" or "YYYY-MM-DD-suffix"
      - h2_title    : slug(title)
      - h2_numbered : "N" (just the number), or slug if no number prefix.
    """
    if not content:
        return []
    matches = list(_H2_HEADER_RE.finditer(content))
    if not matches:
        return []
    sections: list[dict] = []
    seen_ids: set[str] = set()
    for i, m in enumerate(matches):
        title = m.group(1).strip()
        char_start = m.end()
        char_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        line = content[: m.start()].count("\n") + 1

        if doc_type == "h2_date":
            dm = _DATE_PREFIX_RE.match(title)
            if dm:
                date = dm.group(1)
                suffix = dm.group(2)
                section_id = date if not suffix else f"{date}-{_slugify_runbook(suffix)}"
            else:
                section_id = _slugify_runbook(title)
        elif doc_type == "h2_numbered":
            nm = _NUMBERED_PREFIX_RE.match(title)
            section_id = nm.group(1) if nm else _slugify_runbook(title)
        else:  # h2_title
            section_id = _slugify_runbook(title)

        # Dedup if same id (rare) — append counter
        base_id = section_id
        counter = 2
        while section_id in seen_ids:
            section_id = f"{base_id}-{counter}"
            counter += 1
        seen_ids.add(section_id)

        sections.append({
            "id": section_id,
            "title": title,
            "line": line,
            "char_start": char_start,
            "char_end": char_end,
        })
    return sections


def _runbook_list_sections_impl(
    document: str,
    repo_path: str | None = None,
) -> dict:
    """Return the list of H2 sections for the requested runbook."""
    log_event("pipeline.mcp.runbook_list_sections.begin", {})  # PIPELINE_TRACE
    start = time.time()
    if not isinstance(document, str) or not _DOC_NAME_RE.match(document):
        raise ValueError(
            f"invalid document {document!r}: must match ^[a-z_]{{1,32}}$"
        )
    if document not in _RUNBOOK_DOCS:
        raise ValueError(
            f"invalid document {document!r}. Allowed: {sorted(_RUNBOOK_DOCS)}"
        )
    repo = _resolve_repo_path(repo_path)
    file_path = _resolve_runbook_path(document, repo)
    if not file_path.exists():
        return {
            "document": document,
            "sections": [],
            "count": 0,
            "file_path": str(file_path),
            "repo_path": str(repo),
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
            "error": "document_missing",
        }
    content = file_path.read_text(encoding="utf-8")
    _, doc_type = _RUNBOOK_DOCS[document]
    sections = _parse_runbook_sections(content, doc_type)
    return {
        "document": document,
        "sections": [
            {"id": s["id"], "title": s["title"], "line": s["line"]}
            for s in sections
        ],
        "count": len(sections),
        "file_path": str(file_path),
        "repo_path": str(repo),
        "elapsed_ms": round((time.time() - start) * 1000.0, 2),
    }


def _runbook_get_impl(
    document: str,
    section_id: str,
    repo_path: str | None = None,
) -> dict:
    """Return the content + metadata for one H2 section of the requested runbook."""
    log_event("pipeline.mcp.runbook_get.begin", {})  # PIPELINE_TRACE
    start = time.time()
    if not isinstance(document, str) or not _DOC_NAME_RE.match(document):
        raise ValueError(
            f"invalid document {document!r}: must match ^[a-z_]{{1,32}}$"
        )
    if document not in _RUNBOOK_DOCS:
        raise ValueError(
            f"invalid document {document!r}. Allowed: {sorted(_RUNBOOK_DOCS)}"
        )
    if not isinstance(section_id, str) or not _SECTION_ID_RE.match(section_id):
        raise ValueError(
            f"invalid section_id {section_id!r}: must match ^[a-z0-9][a-z0-9_-]{{0,79}}$"
        )
    repo = _resolve_repo_path(repo_path)
    file_path = _resolve_runbook_path(document, repo)
    if not file_path.exists():
        return {
            "error": "document_missing",
            "document": document,
            "section_id": section_id,
            "file_path": str(file_path),
            "repo_path": str(repo),
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
        }
    content = file_path.read_text(encoding="utf-8")
    _, doc_type = _RUNBOOK_DOCS[document]
    sections = _parse_runbook_sections(content, doc_type)
    match = next((s for s in sections if s["id"] == section_id), None)
    if match is None:
        return {
            "error": "section_not_found",
            "document": document,
            "section_id": section_id,
            "available_sections": [s["id"] for s in sections],
            "file_path": str(file_path),
            "repo_path": str(repo),
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
        }
    body = content[match["char_start"]:match["char_end"]].strip()
    capped, truncated = _cap_with_marker(body, RUNBOOK_TOOL_MAX_CHARS)
    return {
        "document": document,
        "section_id": section_id,
        "title": match["title"],
        "content": capped,
        "line": match["line"],
        "truncated": truncated,
        "file_path": str(file_path),
        "repo_path": str(repo),
        "elapsed_ms": round((time.time() - start) * 1000.0, 2),
    }


# ── Chunk B.4 BUGS.md tools (read-only) ─────────────────────────────────────


# Bug ID validation — anti path-traversal + format guarantee.
_BUG_ID_RE = re.compile(r"^BUG-\d{3,4}$")

# Match `## BUG-XXX:` and `### BUG-XXX:` headers (tolerate optional ~~strike~~).
_BUG_HEADER_RE = re.compile(
    r"^(#{2,3})\s+(?:~~)?(BUG-\d{3,4}):\s*(.+?)(?:~~)?\s*$",
    re.MULTILINE,
)

# Status field inside a bug body.
_BUG_STATUS_RE = re.compile(
    r"^\s*-\s*\*\*Status\*\*:\s*\**\s*([A-Za-z]+)",
    re.MULTILINE,
)

# Section fields: Symptom, Root cause, Fix, Test, Regression.
_BUG_SECTION_NAMES = ("Symptom", "Root cause", "Fix", "Test", "Regression")

BUGS_TOOL_MAX_CHARS = 30_000
BUGS_LIST_LIMIT_MAX = 500
VALID_BUG_STATUS = {"OPEN", "FIXED", "WONTFIX", "PARTIAL"}


def _load_bugs_md(repo: Path) -> str | None:
    """Read <repo>/BUGS.md or return None if absent. Read-only."""
    bugs_path = repo / "BUGS.md"
    if not bugs_path.exists() or not bugs_path.is_file():
        return None
    try:
        return bugs_path.read_text(encoding="utf-8")
    except OSError:
        return None


def _parse_bugs_md(content: str) -> list[dict]:
    """Parse BUGS.md into a list of bug dicts.

    Each bug: {id, status, title, body, sections: {...}, line: int}.
    Skips the literal "BUG-XXX" template placeholder.
    """
    if not content:
        return []
    matches = list(_BUG_HEADER_RE.finditer(content))
    if not matches:
        return []
    bugs: list[dict] = []
    for i, m in enumerate(matches):
        bug_id = m.group(2)
        if bug_id == "BUG-XXX":
            continue  # template line
        title = m.group(3).strip()
        body_start = m.end()
        body_end = matches[i + 1].start() if i + 1 < len(matches) else len(content)
        body = content[body_start:body_end].strip()

        status_match = _BUG_STATUS_RE.search(body)
        status = status_match.group(1).upper() if status_match else "UNKNOWN"

        sections: dict[str, str] = {}
        for name in _BUG_SECTION_NAMES:
            # Capture from `**Name**:` until the next `**Field**:` or end of body
            pattern = re.compile(
                rf"^\s*-\s*\*\*{re.escape(name)}\*\*:\s*(.+?)"
                rf"(?=^\s*-\s*\*\*(?:{'|'.join(re.escape(n) for n in _BUG_SECTION_NAMES)})\*\*|\Z)",
                re.MULTILINE | re.DOTALL | re.IGNORECASE,
            )
            sm = pattern.search(body)
            if sm:
                sections[name] = sm.group(1).strip()

        # Approximate line number = number of '\n' before the header + 1
        line_num = content[: m.start()].count("\n") + 1

        bugs.append({
            "id": bug_id,
            "status": status,
            "title": title,
            "body": body,
            "sections": sections,
            "line": line_num,
        })
    # Dedup by id keeping FIRST occurrence (canonical wins over ~~legacy~~)
    seen: set[str] = set()
    unique: list[dict] = []
    for b in bugs:
        if b["id"] in seen:
            continue
        seen.add(b["id"])
        unique.append(b)
    return unique


def _bugs_list_impl(
    repo_path: str | None = None,
    status_filter: str | None = None,
    limit: int = 50,
) -> dict:
    """Return a short headers-only list of bugs from <repo>/BUGS.md.

    Read-only. Filters by status when `status_filter` is set (case-insensitive).
    """
    log_event("pipeline.mcp.bugs_list.begin", {})  # PIPELINE_TRACE
    start = time.time()
    limit = max(1, min(BUGS_LIST_LIMIT_MAX, int(limit)))
    repo = _resolve_repo_path(repo_path)
    content = _load_bugs_md(repo)
    if content is None:
        return {
            "bugs": [],
            "count": 0,
            "total": 0,
            "status_filter": status_filter,
            "truncated": False,
            "repo_path": str(repo),
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
        }
    all_bugs = _parse_bugs_md(content)
    if status_filter:
        status_filter_norm = status_filter.strip().upper()
        filtered = [b for b in all_bugs if b["status"] == status_filter_norm]
    else:
        filtered = list(all_bugs)
    total = len(filtered)
    truncated = total > limit
    sliced = filtered[:limit]
    out_bugs = [
        {"id": b["id"], "status": b["status"], "title": b["title"], "line": b["line"]}
        for b in sliced
    ]
    return {
        "bugs": out_bugs,
        "count": len(out_bugs),
        "total": total,
        "status_filter": status_filter,
        "truncated": truncated,
        "repo_path": str(repo),
        "elapsed_ms": round((time.time() - start) * 1000.0, 2),
    }


def _bugs_get_impl(bug_id: str, repo_path: str | None = None) -> dict:
    """Return one bug's full content + parsed sections.

    Read-only. `bug_id` is regex-validated (`^BUG-\\d{3,4}$`) for defense
    against path traversal — even though we never touch the filesystem with
    the bug_id, we keep the same hardening pattern as B.2 tree_get_branch.
    """
    log_event("pipeline.mcp.bugs_get.begin", {})  # PIPELINE_TRACE
    start = time.time()
    if not isinstance(bug_id, str) or not _BUG_ID_RE.match(bug_id):
        raise ValueError(
            f"invalid bug_id {bug_id!r}: must match ^BUG-\\d{{3,4}}$"
        )
    repo = _resolve_repo_path(repo_path)
    content = _load_bugs_md(repo)
    if content is None:
        return {
            "error": "bugs_md_missing",
            "bug_id": bug_id,
            "repo_path": str(repo),
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
        }
    all_bugs = _parse_bugs_md(content)
    match = next((b for b in all_bugs if b["id"] == bug_id), None)
    if match is None:
        return {
            "error": "bug_not_found",
            "bug_id": bug_id,
            "available_count": len(all_bugs),
            "repo_path": str(repo),
            "elapsed_ms": round((time.time() - start) * 1000.0, 2),
        }
    capped, truncated = _cap_with_marker(match["body"], BUGS_TOOL_MAX_CHARS)
    return {
        "id": match["id"],
        "status": match["status"],
        "title": match["title"],
        "content": capped,
        "sections": dict(match["sections"]),
        "line": match["line"],
        "truncated": truncated,
        "repo_path": str(repo),
        "elapsed_ms": round((time.time() - start) * 1000.0, 2),
    }


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
            f"project. Run `muninn-mem init` in the repo first."
        )
    tree_json = tree_dir / "tree.json"
    if not tree_json.exists():
        raise ValueError(
            f"{repo}/.muninn/tree/tree.json is missing. Re-run `muninn-mem init` "
            f"or `muninn-mem bootstrap` to regenerate."
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
    log_event("pipeline.mcp.tree_get_root.begin", {})  # PIPELINE_TRACE
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
    log_event("pipeline.mcp.tree_get_branch.begin", {})  # PIPELINE_TRACE
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
    log_event("pipeline.mcp.tree_list_branches.begin", {})  # PIPELINE_TRACE
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

    # ── Chunk B.5 runbook tools (read-only) ──

    @app.tool()
    def runbook_list_sections(
        document: str,
        repo_path: str | None = None,
    ) -> dict:
        """List H2 sections of a Muninn runbook document.

        Companion to `runbook_get`. Use this first to discover section IDs
        before reading their content.

        Args:
            document: one of "changelog" | "winter_tree" | "battle_plan"
                      (strict whitelist — anti path-traversal).
            repo_path: absolute path to the project (defaults to $MUNINN_REPO
                       env, then cwd).

        Returns:
            {
              "document": str,
              "sections": [{"id": str, "title": str, "line": int}],
              "count": int,
              "file_path": str,
              "repo_path": str,
              "elapsed_ms": float,
              "error"?: "document_missing",     # if the file is absent
            }

        Section IDs by document:
          - "changelog"   : `YYYY-MM-DD` or `YYYY-MM-DD-suffix` (slug)
          - "winter_tree" : slug of the section title
          - "battle_plan" : just the number ("0", "1", "2", ...)
        """
        return _runbook_list_sections_impl(
            document=document, repo_path=repo_path,
        )

    @app.tool()
    def runbook_get(
        document: str,
        section_id: str,
        repo_path: str | None = None,
    ) -> dict:
        """Read one H2 section of a Muninn runbook document.

        Companion to `runbook_list_sections` — call that first to discover
        valid section IDs.

        Args:
            document: one of "changelog" | "winter_tree" | "battle_plan"
                      (strict whitelist).
            section_id: section identifier, validated against
                        `^[a-z0-9][a-z0-9_-]{0,79}$` (anti path-traversal).
            repo_path: absolute path to the project.

        Returns:
            {
              "document": str, "section_id": str, "title": str,
              "content": str,                # cap 40K chars (~10K tokens)
              "line": int,                   # line in the source file
              "truncated": bool,
              "file_path": str, "repo_path": str, "elapsed_ms": float,
            }

        If the section doesn't exist: {"error": "section_not_found",
        "available_sections": [...], ...} WITHOUT raising — recover by
        calling runbook_list_sections.

        Raises:
            ValueError on invalid document or section_id format.
        """
        return _runbook_get_impl(
            document=document, section_id=section_id, repo_path=repo_path,
        )

    # ── Chunk B.4 BUGS.md tools (read-only) ──

    @app.tool()
    def bugs_list(
        repo_path: str | None = None,
        status_filter: str | None = None,
        limit: int = 50,
    ) -> dict:
        """List bugs from the project's BUGS.md (headers only).

        Read-only. Returns a compact header list so you can decide which
        bugs to read in full via `bugs_get(bug_id)`.

        Args:
            repo_path: absolute path to the project (defaults to $MUNINN_REPO
                       env, then cwd).
            status_filter: case-insensitive filter — typically "OPEN",
                           "FIXED", "WONTFIX", "PARTIAL". None = all bugs.
            limit: max bugs returned (1..500, default 50).

        Returns:
            {
              "bugs": [{"id": "BUG-111", "status": "FIXED",
                        "title": "tree write paths leak", "line": int}],
              "count": int,                # bugs actually returned
              "total": int,                # bugs matched before limit
              "status_filter": str | None,
              "truncated": bool,           # True if total > count
              "repo_path": str,
              "elapsed_ms": float,
            }

        Empty result (count=0) is returned silently if BUGS.md is missing.
        """
        return _bugs_list_impl(
            repo_path=repo_path, status_filter=status_filter, limit=limit,
        )

    @app.tool()
    def bugs_get(bug_id: str, repo_path: str | None = None) -> dict:
        """Read one bug's full content + parsed sections from BUGS.md.

        Companion to `bugs_list`. Use `bugs_list` first to discover IDs.
        Read-only.

        Args:
            bug_id: bug identifier, e.g. "BUG-111". Validated against
                    `^BUG-\\d{3,4}$` — anti path-traversal hardening.
            repo_path: absolute path to the project.

        Returns:
            {
              "id": str, "status": str, "title": str,
              "content": str,              # full bug body (cap 30K chars)
              "sections": {"Symptom": str, "Root cause": str,
                            "Fix": str, "Test": str, "Regression": str},
              "line": int,                 # line number in BUGS.md
              "truncated": bool,
              "repo_path": str,
              "elapsed_ms": float,
            }

        If the bug doesn't exist: returns {"error": "bug_not_found", "bug_id",
        "available_count", ...} WITHOUT raising — Claude can recover by
        listing bugs and retrying.

        Raises:
            ValueError on invalid bug_id format (regex mismatch).
        """
        return _bugs_get_impl(bug_id=bug_id, repo_path=repo_path)

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
    """Entry point for the `muninn-mcp-mem` console_script and `python -m muninn.mcp`.

    Default behavior: run the FastMCP server over stdio (Claude Code spawns
    the process and talks JSON-RPC over stdin/stdout).

    CHUNK MCP E.4 (2026-05-12): added argparse so `--help` / `--version` /
    `--list-tools` are intercepted and exit cleanly instead of starting the
    stdio loop (which would hang waiting for JSON-RPC input).
    """
    import argparse
    from muninn import __version__

    parser = argparse.ArgumentParser(
        prog="muninn-mcp-mem",
        description="Muninn MCP server — exposes 10 read-only tools "
                    "(mycelium recall, tree, bugs, runbook) to Claude Code via stdio.",
        epilog="With no arguments, runs the stdio MCP server (default). "
               "Claude Code spawns this process automatically — you typically "
               "do NOT invoke it directly.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"muninn-mcp-mem {__version__} (muninn-memory)",
    )
    parser.add_argument(
        "--list-tools",
        action="store_true",
        help="Print the 10 registered MCP tool names and exit (useful for sanity-check).",
    )
    args = parser.parse_args()

    if args.list_tools:
        # Create the app to introspect registered tools without entering stdio loop.
        app = create_server()
        # FastMCP keeps tools in app._tool_manager (internal); fall back to a hardcoded
        # known list if the internal API changes.
        try:
            tools = sorted(app._tool_manager._tools.keys())
        except AttributeError:
            tools = [
                "mycelium_recall_local", "mycelium_recall_meta", "mycelium_recall",
                "tree_get_root", "tree_get_branch", "tree_list_branches",
                "bugs_list", "bugs_get",
                "runbook_list_sections", "runbook_get",
            ]
        print(f"muninn-mcp-mem {__version__} — {len(tools)} tool(s):")
        for t in tools:
            print(f"  {t}")
        return

    _log.info("Muninn MCP server starting (stdio transport)")
    app = create_server()
    app.run(transport="stdio")


if __name__ == "__main__":
    main()
