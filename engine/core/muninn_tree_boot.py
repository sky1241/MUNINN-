"""P3.3 split (2026-05-10) — `boot` + 4 helpers extracted from muninn_tree.py.

Boot-time loading + ranking pipeline:
- `_load_virtual_branches` (was muninn_tree.py:1089-1202, 115L) — P20c cross-repo
- `_surface_insights_for_boot` (was muninn_tree.py:2555-2563, ~10L) — H3 huginn
- `_load_relevant_sessions` (was muninn_tree.py:2724-2774, 53L) — P22 session index
- `_surface_known_errors` (was muninn_tree.py:2882-2904, 23L) — P18 error fixes
- `boot` (was muninn_tree.py:1204-1857, 656L) — R7 main entry point

Re-exported via `from muninn_tree_boot import …` at end of muninn_tree.py.
External code keeps importing `from muninn_tree import boot, …` unchanged.
No standalone shim in muninn/ (see test_chunk_d11_shim_drift.py engine_only).

`_extract_error_fixes` and `_append_session_log` are NOT extracted because
muninn_feed.py imports them via `_m._extract_error_fixes` / `_m._append_session_log`
proxy — kept in muninn_tree.py to avoid extra round-trip.
"""
import json
import re
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from tokenizer import token_count

from muninn_tree import (
    _m,
    BUDGET,
    _actr_activation,
    _atomic_json_write,
    _ebbinghaus_recall,
    _tfidf_relevance,
    adaptive_boot_budget,
    classify_session,
    detect_session_mode,
    huginn_think,
    load_tree,
    predict_next,
    read_node,
    save_tree,
)


def _load_virtual_branches(query: str, budget_tokens: int) -> list:
    """P20c: Load read-only branches from other repos registered in repos.json.

    Returns list of (prefixed_name, text, token_count) tuples.
    Virtual branches are scored by TF-IDF at 0.5x weight vs local branches.
    Max 3 virtual branches loaded, max 50 scanned per repo. Read-only.
    """
    MAX_VIRTUAL = 3
    MAX_SCAN_PER_REPO = 50  # Cap: only scan most recent branches per repo
    WEIGHT_FACTOR = 0.5

    repos = _m._load_repos_registry()
    if not repos:
        return []

    current_repo = _m._REPO_PATH.resolve() if _m._REPO_PATH else None
    if not current_repo:
        return []

    # Collect candidate branches from other repos
    candidates = []  # (repo_name, branch_name, text, tokens, relevance)
    dead_repos = []  # repos to clean from registry

    for repo_name, repo_str in repos.items():
        try:
            repo_p = Path(repo_str)
            # Skip current repo
            if repo_p.resolve() == current_repo:
                continue
            # Check repo still exists
            if not repo_p.exists():
                dead_repos.append(repo_name)
                continue
            tree_dir = repo_p / ".muninn" / "tree"
            tree_meta = tree_dir / "tree.json"
            if not tree_meta.exists():
                continue

            tree_data = json.loads(tree_meta.read_text(encoding="utf-8"))
            other_nodes = tree_data.get("nodes", {})

            # Cap: only scan N most recent branches (by last_access)
            branch_items = [
                (bname, bnode) for bname, bnode in other_nodes.items()
                if bname != "root"
            ]
            branch_items.sort(
                key=lambda x: x[1].get("last_access", "2000-01-01"), reverse=True
            )
            branch_items = branch_items[:MAX_SCAN_PER_REPO]

            branch_contents = {}
            for bname, bnode in branch_items:
                bfile = tree_dir / bnode.get("file", "")
                if bfile.exists():
                    try:
                        text = bfile.read_text(encoding="utf-8")
                        if text.strip():
                            branch_contents[bname] = text
                    except (OSError, UnicodeDecodeError):
                        continue

            if not branch_contents:
                continue

            # Score by TF-IDF if query, else by temperature
            if query:
                scores = _tfidf_relevance(query, branch_contents)
                for bname, text in branch_contents.items():
                    score = scores.get(bname, 0.0) * WEIGHT_FACTOR
                    if score > 0.01:
                        tok = token_count(text)
                        candidates.append((repo_name, bname, text, tok, score))
            else:
                # No query: take hottest branches (by temperature)
                for bname, text in branch_contents.items():
                    bnode_data = other_nodes.get(bname, {})
                    temp = bnode_data.get("temperature", 0.0) * WEIGHT_FACTOR
                    if temp > 0.01:
                        tok = token_count(text)
                        candidates.append((repo_name, bname, text, tok, temp))

        except Exception:
            continue  # Never crash boot because of a broken remote repo

    # Clean dead repos from registry
    if dead_repos:
        try:
            reg_path = _m._repos_registry_path()
            registry = json.loads(reg_path.read_text(encoding="utf-8"))
            for name in dead_repos:
                registry.get("repos", {}).pop(name, None)
            _atomic_json_write(reg_path, registry)
        except (OSError, json.JSONDecodeError):
            pass

    if not candidates:
        return []

    # Sort by score descending, take top MAX_VIRTUAL within budget
    candidates.sort(key=lambda x: x[4], reverse=True)
    result = []
    used_tokens = 0
    for repo_name, bname, text, tok, score in candidates:
        if len(result) >= MAX_VIRTUAL:
            break
        if used_tokens + tok > budget_tokens:
            continue
        prefixed = f"{repo_name}::{bname}"
        result.append((prefixed, text, tok))
        used_tokens += tok

    return result


def _surface_insights_for_boot(query: str = "") -> str:
    """H3: Surface top 3 relevant insights at boot time."""
    insights = huginn_think(query=query, top_n=3)
    if not insights:
        return ""
    lines = ["=== huginn_insights ==="]
    for ins in insights:
        lines.append(f"  {ins['formatted']}")
    return "\n".join(lines)


def _load_relevant_sessions(query: str, sessions_dir: Path, latest_name: str,
                            budget: int, output: list):
    """P22: Search session index and load relevant past sessions at boot."""
    repo_path = sessions_dir.parent.parent  # .muninn/sessions -> repo
    index_path = repo_path / ".muninn" / "session_index.json"
    if not index_path.exists():
        return

    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        if not isinstance(index, list):
            return
    except (json.JSONDecodeError, OSError):
        return

    # Score each session by concept overlap with query
    query_words = set(re.findall(r'[A-Za-z]{4,}', query.lower()))
    if not query_words:
        return

    scored = []
    for entry in index:
        if entry.get("file") == latest_name:
            continue  # skip the one already loaded
        concepts = set(entry.get("concepts", []))
        overlap = len(query_words & concepts)
        # Also check tagged lines for query words
        for tagged_line in entry.get("tagged", []):
            tagged_words = set(re.findall(r'[A-Za-z]{4,}', tagged_line.lower()))
            overlap += len(query_words & tagged_words) * 0.5
        if overlap > 0:
            scored.append((overlap, entry))

    scored.sort(key=lambda x: x[0], reverse=True)

    # Load top 2 relevant sessions (if .mn file still exists)
    loaded = 0
    for score, entry in scored[:2]:
        mn_file = sessions_dir / entry.get("file", "")
        if not mn_file.exists():
            continue
        text = mn_file.read_text(encoding="utf-8")
        tokens = token_count(text)
        if tokens > budget:
            continue
        output.append(f"=== relevant_session ({entry.get('file', '?')}, {entry.get('date', '?')}) ===")
        output.append(text)
        budget -= tokens
        loaded += 1

    return loaded


def _surface_known_errors(repo_path: Path, query: str) -> str:
    """P18: Check if query matches a known error pattern. Returns fix hint or empty."""
    errors_path = repo_path / ".muninn" / "errors.json"
    if not errors_path.exists():
        return ""
    try:
        errors = json.loads(errors_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return ""

    query_lower = query.lower()
    hints = []
    for entry in errors:
        if not isinstance(entry, dict) or "error" not in entry or "fix" not in entry:
            continue
        # Check if query words overlap with error text
        # Strip punctuation for matching (e.g. "TypeError:" should match "TypeError")
        error_words = set(re.findall(r'[a-z0-9_]+', entry["error"].lower()))
        query_words = set(re.findall(r'[a-z0-9_]+', query_lower))
        overlap = error_words & query_words
        if len(overlap) >= 2:  # at least 2 word match (1 was too noisy)
            hints.append(f"KNOWN: {entry['error']} -> FIX: {entry['fix']}")
    return "\n".join(hints[:3])  # max 3 hints


def boot(query: str = "") -> str:
    """R7: load root + relevant branches based on query.

    Scoring (Generative Agents, Park et al. 2023):
      score = α×recency + β×importance + γ×relevance(query)
    where relevance uses TF-IDF cosine similarity on branch content.
    """
    # Adaptive boot budget based on context size
    BUDGET["max_loaded_tokens"] = adaptive_boot_budget()

    tree = load_tree()
    nodes = tree["nodes"]

    root_text = read_node("root", _tree=tree)
    loaded = [("root", root_text)]

    # A6: Boot pre-warm by git diff — load concepts from modified files
    if _m._REPO_PATH:
        try:
            r = subprocess.run(
                ["git", "diff", "--name-only", "HEAD~1"],
                cwd=str(_m._REPO_PATH), capture_output=True, text=True, timeout=5
            )
            if r.returncode == 0 and r.stdout.strip():
                diff_files = r.stdout.strip().split("\n")
                diff_concepts = set()
                for f in diff_files[:20]:
                    # Extract concept-like words from file paths
                    parts = re.findall(r'[a-zA-Z]{3,}', f.replace("/", " ").replace("\\", " "))
                    diff_concepts.update(p.lower() for p in parts if len(p) >= 4)
                if diff_concepts and not query:
                    query = " ".join(list(diff_concepts)[:10])
        except Exception:
            pass  # git not available or no commits

    # P23: Auto-continue — if no query, use last session's concepts
    if not query and _m._REPO_PATH:
        index_path = _m._REPO_PATH / ".muninn" / "session_index.json"
        if index_path.exists():
            try:
                idx = json.loads(index_path.read_text(encoding="utf-8"))
                if isinstance(idx, list) and idx:
                    last = idx[-1]
                    concepts = last.get("concepts", [])[:5]
                    if concepts:
                        query = " ".join(concepts)
            except (json.JSONDecodeError, OSError):
                pass

    # Defaults for variables set inside the query block (C2, B3, B4, V8B)
    blind_spot_concepts = set()
    blind_spots = []
    prediction_scores = {}
    scored = []

    if query:
        # P15: Query expansion via mycelium co-occurrences
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(_m._REPO_PATH or Path("."))

            # P20b: Pull relevant cross-repo knowledge from meta-mycelium
            query_words = re.findall(r'[A-Za-zÀ-ÿ]{3,}', query.lower())
            pulled = m.pull_from_meta(query_concepts=query_words)
            if pulled > 0:
                m.save()

            expanded = set(query_words)
            for word in query_words:
                for related, strength in m.get_related(word, top_n=3):
                    if strength >= 3:  # only strong connections
                        expanded.add(related)
            if expanded - set(query_words):
                query = query + " " + " ".join(expanded - set(query_words))
        except Exception as e:
            print(f"  mycelium query expansion skipped: {e}", file=sys.stderr)

        # Load branch contents for TF-IDF scoring
        branch_contents = {}
        for name, node in nodes.items():
            if name == "root":
                continue
            filepath = _m.TREE_DIR / node["file"]
            try:
                branch_contents[name] = filepath.read_text(encoding="utf-8", errors="ignore")
            except (FileNotFoundError, OSError):
                # Fallback: use tags as content (file may have been pruned concurrently)
                branch_contents[name] = " ".join(node.get("tags", []))

        # TF-IDF relevance scores (0-1)
        relevance_scores = _tfidf_relevance(query, branch_contents)

        # B5: Session mode detection (convergent/divergent) — used for weight
        # adjustment in B6 below, but _sigmoid_k is no longer read by
        # spread_activation (refactored to min-max normalization).
        try:
            session_mode = detect_session_mode()
        except Exception as e:
            session_mode = None
            print(f"  [warn] B5 session mode: {e}", file=sys.stderr)

        # Spreading Activation (Collins & Loftus 1975) — semantic boost
        # Propagates activation through mycelium to find branches that
        # share NO keywords but are semantically connected via co-occurrence
        activation_scores = {}  # branch_name -> activation bonus
        activated_set = {}  # concept -> activation strength (for V5A quorum)
        try:
            activated = m.spread_activation(query_words, hops=2, decay=0.5, top_n=50)  # type: ignore[possibly-undefined]
            if activated:
                # Map activated concepts to branches that contain them
                activated_set = {c: a for c, a in activated}
                for bname, bcontent in branch_contents.items():
                    bwords = set(re.findall(r'[a-z0-9_]+', bcontent.lower()))
                    overlap = bwords & set(activated_set.keys())
                    if overlap:
                        # Activation score = sum of activations for matching concepts
                        act_score = sum(activated_set[w] for w in overlap)
                        # Cap at 1.0 (don't penalize broad connections)
                        activation_scores[bname] = min(1.0, act_score)
        except Exception as e:
            print(f"  [warn] spreading activation: {e}", file=sys.stderr)

        # V3A: Transitive inference (Wynne 1995, Paz-y-Mino 2004)
        # Ordered chain reasoning: A->B->C infers A->C with decaying strength.
        # Complements spreading activation — tracks multiplicative path strength.
        transitive_scores = {}  # branch_name -> transitive bonus
        try:
            for qw in query_words[:5]:  # top 5 query words to limit compute
                inferred = m.transitive_inference(qw, max_hops=3, beta=0.5, top_n=20)  # type: ignore[possibly-undefined]
                if inferred:
                    inferred_set = {c: s for c, s in inferred}
                    for bname, bcontent in branch_contents.items():
                        bwords = set(re.findall(r'[a-z0-9_]+', bcontent.lower()))
                        overlap = bwords & set(inferred_set.keys())
                        if overlap:
                            t_score = sum(inferred_set[w] for w in overlap)
                            t_norm = min(1.0, t_score / max(len(overlap), 1))
                            transitive_scores[bname] = max(
                                transitive_scores.get(bname, 0), t_norm)
        except Exception as e:
            print(f"  [warn] V3A transitive: {e}", file=sys.stderr)

        # B3: Detect blind spots — boost branches that fill structural holes
        blind_spot_concepts = set()
        blind_spots = []
        try:
            blind_spots = m.detect_blind_spots(top_n=20)  # type: ignore[possibly-undefined]
            for a, b, _ in blind_spots:
                blind_spot_concepts.add(a)
                blind_spot_concepts.add(b)
        except Exception as e:
            print(f"  [warn] B3 blind spots: {e}", file=sys.stderr)

        # B4: Predict next branches — get prediction scores
        prediction_scores = {}
        try:
            predictions = predict_next(current_concepts=query_words, top_n=20, _mycelium=m)
            prediction_scores = {name: score for name, score in predictions}
        except Exception as e:
            print(f"  [warn] B4 predictions: {e}", file=sys.stderr)

        # V3B: Bayesian Theory of Mind — infer user goal from recent queries
        # (Baker, Saxe, Tenenbaum 2009, Cognition)
        # P(goal|actions) ~ exp(-cost) * prior
        # actions = last 3-5 session queries, goal = branch topic alignment
        btom_scores = {}  # branch_name -> goal alignment score
        if _m._REPO_PATH:
            try:
                import math
                index_path = _m._REPO_PATH / ".muninn" / "session_index.json"
                if index_path.exists():
                    idx = json.loads(index_path.read_text(encoding="utf-8"))
                    if isinstance(idx, list) and len(idx) >= 2:
                        # Collect concepts from last 5 sessions (actions)
                        recent = idx[-5:]
                        action_concepts = {}  # concept -> frequency across recent sessions
                        for sess in recent:
                            for c in sess.get("concepts", []):
                                action_concepts[c] = action_concepts.get(c, 0) + 1
                        if action_concepts:
                            # Normalize to probabilities
                            total_freq = sum(action_concepts.values())
                            action_probs = {c: f / total_freq for c, f in action_concepts.items()}
                            # Score each branch by goal alignment
                            for bname, bcontent in branch_contents.items():
                                try:
                                    bwords = set(re.findall(r'[a-z0-9_]+', bcontent.lower()))
                                    overlap = bwords & set(action_probs.keys())
                                    if overlap:
                                        alignment = sum(action_probs[w] for w in overlap)
                                        prior = nodes.get(bname, {}).get("usefulness") or 0.5
                                        # V3B fix: sigmoid instead of exp(-1/x) which kills signal
                                        posterior = (alignment / (alignment + 1.0)) * prior
                                        btom_scores[bname] = min(1.0, posterior)
                                except (KeyError, TypeError):
                                    continue
            except Exception as e:
                print(f"  [warn] V3B BToM: {e}", file=sys.stderr)

        # Close mycelium — all spreading activation / transitive work is done
        try:
            m.close()  # type: ignore[possibly-undefined]
        except (NameError, AttributeError):
            pass

        # B6: Adjust scoring weights by session type
        w_recall = 0.15
        w_relevance = 0.40
        w_activation = 0.20
        w_usefulness = 0.10
        w_rehearsal = 0.15
        try:
            session_type = classify_session()
            stype = session_type.get("type", "unknown")
            if stype == "debug":
                # Debug: boost recall (recent errors), reduce rehearsal
                w_recall = 0.20
                w_usefulness = 0.10
                w_rehearsal = 0.10
            elif stype == "explore":
                # Explore: boost activation (spread wider)
                w_activation = 0.30
                w_relevance = 0.30
                w_recall = 0.10
                w_usefulness = 0.15
            elif stype == "review":
                # Review: boost rehearsal (need to re-read)
                w_rehearsal = 0.25
                w_relevance = 0.35
                w_recall = 0.10
        except Exception as e:
            print(f"  [warn] B6 classify_session: {e}", file=sys.stderr)

        # V11B: Boyd-Richerson cultural transmission pre-compute (Boyd & Richerson 1985)
        # (1) Conformist bias: tag frequency across all branches (popular = boosted)
        # (2) Prestige bias: td_value from V2B (successful history)
        # (3) Guided variation: correction toward mean usefulness (mu=0.1)
        _tag_freq = {}  # tag -> count of branches with that tag
        _all_usefulness = []
        for _n, _nd in nodes.items():
            if _n == "root":
                continue
            for _t in _nd.get("tags", []):
                _tag_freq[_t] = _tag_freq.get(_t, 0) + 1
            _all_usefulness.append(_nd.get("usefulness", 0.5))
        _n_branches = max(1, len(_all_usefulness))
        _mean_usefulness = sum(_all_usefulness) / _n_branches if _all_usefulness else 0.5
        # Normalize tag frequencies to [0,1]
        _max_tag_freq = max(_tag_freq.values()) if _tag_freq else 1
        # Pre-cache tag sets for V1A coupling (avoids 13M set() constructions)
        _tag_sets_cache = {n: set(nd.get("tags", [])) for n, nd in nodes.items() if n != "root"}
        # V1A: Build tag -> [branches] index for O(1) coupling lookup (was O(n) per tag)
        _tag_to_branches = {}
        for _n, _nd in nodes.items():
            if _n == "root":
                continue
            for _t in _nd.get("tags", []):
                _tag_to_branches.setdefault(_t, []).append(_n)

        # Generative Agents scoring: recency + importance + relevance + activation
        scored = []
        for name, node in nodes.items():
            if name == "root":
                continue

            # Recall probability (Ebbinghaus/Settles spaced repetition)
            recall = _ebbinghaus_recall(node)

            # A2: ACT-R base-level activation (Anderson 1993)
            import math
            actr_raw = _actr_activation(node)
            actr_norm = 1.0 / (1.0 + math.exp(-actr_raw))  # sigmoid -> [0,1]
            recall_blended = 0.7 * recall + 0.3 * actr_norm

            # Relevance: TF-IDF cosine similarity
            relevance = relevance_scores.get(name, 0.0)

            # Activation: spreading activation bonus (Collins & Loftus 1975)
            activation = activation_scores.get(name, 0.0)

            # P36: Usefulness — feedback from past sessions (0.5 = neutral default)
            usefulness = node.get("usefulness", 0.5)

            # Rehearsal need: branches near forgetting threshold
            rehearsal_need = max(0.0, 1.0 - abs(recall - 0.2) / 0.2) if 0.05 < recall < 0.4 else 0.0

            # Base score with B6-adjusted weights
            total = (w_recall * recall_blended + w_relevance * relevance +
                     w_activation * activation + w_usefulness * usefulness +
                     w_rehearsal * rehearsal_need)

            # V7B: ACO pheromone scoring (Dorigo, Maniezzo, Colorni 1996)
            # p_ij = tau^alpha * eta^beta — combines history (tau) and local relevance (eta)
            # tau = usefulness * recall (pheromone = past success * freshness)
            # eta = relevance (heuristic = current query match)
            # alpha=1, beta=2 (beta>alpha = favor local relevance over history)
            tau = max(0.01, usefulness * recall_blended)  # pheromone deposit
            eta = max(0.01, relevance)  # local heuristic
            aco_score = min(1.0, tau * (eta ** 2))  # tau^1 * eta^2, clamped
            # Additive bonus: reward branches with strong history + relevance
            total += 0.05 * aco_score

            # B3: Blind spot bonus — branches covering structural holes get +0.05
            tags = set(node.get("tags", []))
            if tags & blind_spot_concepts:
                total += 0.05

            # V3A: Transitive inference bonus — branches reachable via ordered chains
            t_score = transitive_scores.get(name, 0.0)
            if t_score > 0:
                total += 0.10 * t_score  # V3A: max +0.10 (was 0.05, cosmetic)

            # B4: Prediction bonus — predicted branches get +0.03 * prediction_score
            pred_score = prediction_scores.get(name, 0.0)
            if pred_score > 0:
                total += 0.03 * min(1.0, pred_score)

            # V3B: BToM goal alignment bonus (Baker, Saxe, Tenenbaum 2009)
            btom_score = btom_scores.get(name, 0.0)
            if btom_score > 0:
                total += 0.04 * btom_score  # max +0.04

            # V11B: Boyd-Richerson 3 cultural biases (Boyd & Richerson 1985)
            # (1) Conformist bias: dp = beta*p*(1-p)*(2p-1)
            #     p = fraction of branches sharing this tag profile (popularity)
            _node_tags = node.get("tags", [])
            if _node_tags and _tag_freq:
                _p = sum(_tag_freq.get(t, 0) for t in _node_tags) / (_max_tag_freq * max(1, len(_node_tags)))
                _p = max(0.01, min(0.99, _p))
                _conform_dp = 0.3 * _p * (1.0 - _p) * (2.0 * _p - 1.0)  # beta=0.3
                total += 0.15 * _conform_dp  # V11B fix: was 0.02 (cosmetic)

            # (2) Prestige bias: p' = sum(w_i * p_i) — td_value as prestige
            _td_value = node.get("td_value", 0.5)
            _prestige = _td_value * usefulness  # prestige = success * usefulness
            total += 0.06 * _prestige  # V11B fix: was 0.02 (cosmetic)

            # (3) Guided variation: delta = mu*(p_opt - p)
            #     Pushes score toward population mean usefulness (convergence)
            _mu = 0.1
            _guided_delta = _mu * (_mean_usefulness - usefulness)
            total += 0.06 * _guided_delta  # V11B fix: was 0.02 (cosmetic)

            # V5A: Quorum sensing Hill switch (Waters & Bassler 2005)
            # Activate ONLY when enough neighbors are co-activated (quorum)
            # f(A) = A^n / (K^n + A^n), activated = number of activated co-occurring tags
            _node_tags_set = set(node.get("tags", []))
            if _node_tags_set and activated_set:
                # Count how many spreading-activation concepts overlap with this branch's tags
                _activated_count = sum(1 for t in _node_tags_set if t in activated_set)
                _K_quorum = 2.0  # threshold: need at least ~2 activated neighbors
                _n_hill = 3      # Hill coefficient (steepness)
                if _activated_count > 0:
                    _quorum = (_activated_count ** _n_hill) / (
                        _K_quorum ** _n_hill + _activated_count ** _n_hill)
                    total += 0.03 * _quorum  # V5A: max +0.03 (tuned by retrieval benchmark)

            # V1A: Coupled oscillator (Yekutieli et al. 2005)
            # Temperature coupling: branches connected via mycelium push toward each other
            # tau_coupling = sum_j C_ij * (temp_j - temp_i)
            # Uses _tag_to_branches index (O(1) lookup) instead of O(n) brute-force.
            _my_temp = node.get("temperature", 0.5)
            _coupling_sum = 0.0
            for _t in list(_node_tags_set)[:3]:  # top 3 tags for coupling
                for _sname in _tag_to_branches.get(_t, []):
                    if _sname == name:
                        continue
                    _other_temp = nodes.get(_sname, {}).get("temperature", 0.5)
                    _coupling_sum += 0.02 * (_other_temp - _my_temp)
                    break  # one coupling per tag
            total += max(-0.02, min(0.02, _coupling_sum))  # V1A: tuned by retrieval benchmark

            if total > 0.01:
                scored.append((name, total))

        scored.sort(key=lambda x: x[1], reverse=True)

        # V5B: Cross-inhibition winner-take-all (Seeley et al. 2012, Science)
        # When top branches have similar scores (within 15%), they cross-inhibit.
        # Better branch (higher r) wins. beta controls inhibition strength.
        # dNA/dt = rA*(1-NA/K)*NA - beta*NB*NA
        # Scores normalized to [0,1] before LV, then denormalized back.
        _beta_inhib = 0.05  # inhibition strength (tuned by retrieval benchmark)
        _K_inhib = 1.0      # carrying capacity
        _max_iter = 5
        if _beta_inhib > 0 and len(scored) >= 2:
            top_score = scored[0][1]
            if top_score > 0:
                # Only top 5 competitors (not all within 15% — that killed relevant branches)
                competitors = scored[:5]
                if len(competitors) >= 2:
                    # Normalize to [0,1] for LV dynamics (avoid scale mismatch)
                    pop = {n: s / top_score for n, s in competitors}
                    for _ in range(_max_iter):
                        new_pop = {}
                        for n, s in pop.items():
                            r = relevance_scores.get(n, 0.1)
                            growth = r * (1.0 - s / _K_inhib) * s
                            inhibition = sum(_beta_inhib * pop[peer] * s
                                            for peer in pop if peer != n)
                            new_s = s + 0.1 * (growth - inhibition)  # dt=0.1
                            new_pop[n] = max(0.001, min(_K_inhib, new_s))
                        pop = new_pop
                    # Denormalize back to original scale and update
                    score_map = dict(scored)
                    for n, s in pop.items():
                        score_map[n] = s * top_score  # restore scale
                    scored = sorted(score_map.items(), key=lambda x: x[1], reverse=True)

        loaded_tokens = nodes["root"]["lines"] * BUDGET["tokens_per_line"]

        # Bloom-style concept tracking: skip branches that add <5% new concepts
        loaded_concepts = set()
        # Seed with root concepts
        root_words = set(re.findall(r'[a-zA-Z]{4,}', root_text.lower()))
        loaded_concepts.update(root_words)

        for name, score in scored:
            node = nodes[name]
            node_tokens = node["lines"] * BUDGET["tokens_per_line"]
            if loaded_tokens + node_tokens > BUDGET["max_loaded_tokens"]:
                break
            # Check concept novelty before committing to load
            branch_text = read_node(name, _tree=tree)
            branch_concepts = set(re.findall(r'[a-zA-Z]{3,}', branch_text.lower()))
            new_concepts = branch_concepts - loaded_concepts
            if len(branch_concepts) > 10 and len(new_concepts) / len(branch_concepts) < 0.05:
                continue  # <5% new concepts, skip this branch
            loaded_concepts.update(branch_concepts)
            loaded.append((name, branch_text))
            loaded_tokens += node_tokens

        # C3: Auto-preload top predictions that weren't already loaded
        loaded_names = {n for n, _ in loaded}
        if prediction_scores:
            top_preds = sorted(prediction_scores.items(), key=lambda x: x[1], reverse=True)
            for pred_name, pred_score in top_preds[:3]:  # max 3 preloads
                if pred_name in loaded_names or pred_name not in nodes:
                    continue
                if pred_score < 0.3:
                    break  # only preload strong predictions
                node = nodes[pred_name]
                node_tokens = node["lines"] * BUDGET["tokens_per_line"]
                if loaded_tokens + node_tokens > BUDGET["max_loaded_tokens"]:
                    break
                branch_text = read_node(pred_name, _tree=tree)
                if branch_text:
                    loaded.append((pred_name, branch_text))
                    loaded_tokens += node_tokens
                    loaded_names.add(pred_name)
    else:
        ranked = sorted(
            [(n, d) for n, d in nodes.items() if n != "root"],
            key=lambda x: x[1].get("temperature", 0),
            reverse=True,
        )
        loaded_tokens = nodes["root"]["lines"] * BUDGET["tokens_per_line"]
        for name, node in ranked[:3]:
            node_tokens = node["lines"] * BUDGET["tokens_per_line"]
            if loaded_tokens + node_tokens > BUDGET["max_loaded_tokens"]:
                break
            branch_text = read_node(name, _tree=tree)
            loaded.append((name, branch_text))
            loaded_tokens += node_tokens

    # Save tree once after all reads (access_count/last_access updated in-place)
    save_tree(tree)

    # P20c: Virtual branches — read-only branches from other repos
    remaining_budget = BUDGET["max_loaded_tokens"] - loaded_tokens
    if remaining_budget > 500 and _m._REPO_PATH:
        virtual = _load_virtual_branches(query or "", remaining_budget)
        for vname, vtext, vtokens in virtual:
            loaded.append((vname, vtext))
            loaded_tokens += vtokens

    # C2: Boot feedback log — record which blind spots were covered
    if blind_spot_concepts and loaded:
        covered = set()
        uncovered = set()
        for a, b, reason in blind_spots:
            pair = f"{a}|{b}"
            loaded_tags = set()
            for _, text in loaded:
                loaded_tags.update(re.findall(r'[a-zA-Z]{3,}', text.lower()))
            if a in loaded_tags and b in loaded_tags:
                covered.add(pair)
            else:
                uncovered.add(pair)
        feedback = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "query": query or "",
            "blind_spots_total": len(blind_spot_concepts),
            "covered": list(covered),
            "uncovered": list(uncovered),
            "branches_loaded": [n for n, _ in loaded],
        }
        feedback_path = (_m._REPO_PATH or _m.MUNINN_ROOT) / ".muninn" / "boot_feedback.json"
        try:
            import json as _json
            history = []
            if feedback_path.exists():
                history = _json.loads(feedback_path.read_text(encoding="utf-8"))
                if not isinstance(history, list):
                    history = [history]
            history.append(feedback)
            history = history[-20:]  # keep last 20 boots
            _atomic_json_write(feedback_path, history, indent=1)
        except Exception as e:
            print(f"  [warn] boot feedback: {e}", file=sys.stderr)

    # P19: Dedup branches — skip if NCD similarity > 0.6 (too similar)
    deduped = []
    loaded_texts = []
    for name, text in loaded:
        if name == "root":
            deduped.append((name, text))
            loaded_texts.append(text)
            continue
        is_dup = False
        for prev_text in loaded_texts[-3:]:  # compare last 3 only (O(1) per branch)
            if not text or not prev_text:
                continue
            ncd = _m._ncd(text, prev_text)
            if ncd < 0.4:  # NCD < 0.4 = very similar content
                is_dup = True
                break
        if not is_dup:
            deduped.append((name, text))
            loaded_texts.append(text)

    output = []
    for name, text in deduped:
        output.append(f"=== {name} ===")
        output.append(text)

    # Load latest session .mn if it exists (tail-first if too large)
    sessions_dir = _m._REPO_PATH / ".muninn" / "sessions" if _m._REPO_PATH else _m.MUNINN_ROOT / ".muninn" / "sessions"
    if sessions_dir.exists():
        session_files = sorted(sessions_dir.glob("*.mn"))
        if session_files:
            latest = session_files[-1]
            session_text = latest.read_text(encoding="utf-8")
            remaining_budget = BUDGET["max_loaded_tokens"] - loaded_tokens
            session_tokens = token_count(session_text)

            if session_tokens <= remaining_budget:
                output.append(f"=== last_session ({latest.stem}) ===")
                output.append(session_text)
                loaded_tokens += session_tokens
            elif remaining_budget > 200:
                max_chars = remaining_budget * 3
                session_lines = session_text.split("\n")
                tail_lines = []
                char_count = 0
                for line in reversed(session_lines):
                    if char_count + len(line) + 1 > max_chars:
                        break
                    tail_lines.append(line)
                    char_count += len(line) + 1
                tail_lines.reverse()
                if tail_lines:
                    output.append(f"=== last_session ({latest.stem}) [tail] ===")
                    output.append("\n".join(tail_lines))
                    loaded_tokens += token_count("\n".join(tail_lines))

            # P22: Search session index for relevant past sessions
            if query and _m._REPO_PATH:
                remaining_budget = BUDGET["max_loaded_tokens"] - loaded_tokens
                if remaining_budget > 500:
                    _load_relevant_sessions(
                        query, sessions_dir, latest.name, remaining_budget, output
                    )

    # P18: Surface known error fixes if query matches
    if query and _m._REPO_PATH:
        error_hints = _surface_known_errors(_m._REPO_PATH, query)
        if error_hints:
            output.append("\n=== known_fixes ===")
            output.append(error_hints)

    # H3: Surface Huginn insights at boot
    if _m._REPO_PATH:
        huginn_output = _surface_insights_for_boot(query)
        if huginn_output:
            output.append("\n" + huginn_output)

    # V8B: Active sensing — info-theoretic disambiguation (Yang et al. 2016)
    # a* = argmax_a I(X;Y|a) — when uncertain, identify the concept that
    # would best disambiguate the top candidate branches.
    # Only triggered when top 3 scores are within 10% of each other.
    _v8b_hint = ""
    try:
        if query and len(scored) >= 3:
            _top3 = scored[:3]
            _spread = _top3[0][1] - _top3[2][1]
            if _spread < 0.10 * _top3[0][1] and _top3[0][1] > 0.01:
                # High uncertainty — find the most discriminative concept
                import math as _math
                _concept_dist = {}  # concept -> set of branches containing it (among top 3)
                for _sn, _ in _top3:
                    for _tag in nodes.get(_sn, {}).get("tags", []):
                        _concept_dist.setdefault(_tag, set()).add(_sn)
                # Best concept = one that splits top 3 most evenly (max entropy)
                _best_concept, _best_entropy = "", 0.0
                for _c, _branches_with in _concept_dist.items():
                    _p = len(_branches_with) / 3.0
                    if 0 < _p < 1:
                        _h = -_p * _math.log2(_p) - (1 - _p) * _math.log2(1 - _p)
                        if _h > _best_entropy:
                            _best_entropy = _h
                            _best_concept = _c
                if _best_concept:
                    _v8b_hint = _best_concept
    except Exception as e:
        print(f"  [warn] V8B active sensing: {e}", file=sys.stderr)

    # P36: Save boot manifest for feedback loop
    if _m._REPO_PATH:
        try:
            boot_manifest = {
                "branches": [name for name, _ in deduped if name != "root"],
                "query": query or "",
                "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            if _v8b_hint:
                boot_manifest["v8b_clarify"] = _v8b_hint
            manifest_path = _m._REPO_PATH / ".muninn" / "last_boot.json"
            _atomic_json_write(manifest_path, boot_manifest)
        except OSError:
            pass

    # KIComp: density scoring — drop low-information lines if over budget
    full_text = "\n".join(output)
    total_tokens = token_count(full_text)
    if total_tokens > BUDGET["max_loaded_tokens"]:
        full_text = _m._kicomp_filter(full_text, BUDGET["max_loaded_tokens"])

    # A8: Prune warning — warn if many dead branches
    try:
        branches = {k: v for k, v in nodes.items() if k != "root"}
        if branches:
            cold_count = sum(1 for v in branches.values()
                             if _ebbinghaus_recall(v) < 0.1)
            pct = cold_count / len(branches) * 100
            if pct > 45:
                full_text += (f"\n\n[MUNINN] {pct:.0f}% branches are cold "
                              f"({cold_count}/{len(branches)}). "
                              f"Consider running: muninn prune --force")
    except Exception:
        pass

    return full_text
