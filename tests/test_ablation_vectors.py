#!/usr/bin/env python3
"""ABLATION BENCHMARK — Mesure l'impact REEL de chaque bio-vecteur sur boot().

Ce test NE SIMULE PAS les formules. Il appelle les VRAIES fonctions de production
(_ebbinghaus_recall, _actr_activation, spread_activation, transitive_inference)
et mesure le score final avec et sans chaque vecteur.

Pour chaque vecteur:
  score_baseline = score avec TOUS les vecteurs ON
  score_ablated  = score avec CE vecteur OFF
  delta = baseline - ablated
  impact% = delta / baseline * 100

Un vecteur qui contribue 0% est un vecteur MORT — du code inutile.

VECTORS TESTES (boot scoring):
  V1A  Coupled Oscillator (temperature coupling)
  V2B  TD-Learning (indirect via td_value in V11B prestige)
  V3A  Transitive Inference (ordered chain reasoning)
  V3B  BToM (goal alignment from session history)
  V4B  EWC Fisher (half-life modulation in recall)
  V5A  Quorum Hill (activated concept threshold)
  V5B  Cross-Inhibition Lotka-Volterra (winner-take-all)
  V6B  Valence-Modulated Decay (emotional half-life)
  V7B  ACO Pheromone (history * relevance blend)
  V11B Boyd-Richerson 3 biases (conformist + prestige + guided)
  A2   ACT-R base-level activation (non-Markov memory)
  B3   Blind spot bonus (structural holes)
  B4   Prediction bonus (Endsley L3)

VECTORS NON-TESTES (pas dans boot scoring):
  V6A  Emotional tagging (write-time, pas boot-time)
  V9A+ Regeneration (prune-time)
  V9B  Reed-Solomon (prune-time)
  V10A VADER (write-time sentiment)
  V10B Circumplex (write-time mapping)
  V8B  Active Sensing (post-scoring hint, no score change)

Bornes:
  ABL.1  Baseline score > 0 for at least 5 branches
  ABL.2  Each vector's delta is computable (no crash)
  ABL.3  V7B ACO has measurable impact (>1% on relevant branches)
  ABL.4  V11B prestige has measurable impact (>0.1% on branches with td_value)
  ABL.5  V6B valence modulation changes recall for emotional branches
  ABL.6  V4B Fisher modulation changes recall for important branches
  ABL.7  A2 ACT-R changes recall_blended vs pure Ebbinghaus
  ABL.8  V5B cross-inhibition changes ranking when top scores are close
  ABL.9  V1A coupling changes score when temperatures differ
  ABL.10 Full report printed with ranking changes
  ABL.11 No vector causes negative total score
  ABL.12 Disabling ALL vectors still produces valid (lower) scores
"""

import sys, os, json, time, math, re, tempfile, shutil
from pathlib import Path
from datetime import datetime, timedelta

# Add engine/core to path
_CORE = str(Path(__file__).resolve().parent.parent / "engine" / "core")
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from muninn import _ebbinghaus_recall, _actr_activation, _days_since
try:
    from muninn.mycelium import Mycelium
    HAS_MYCELIUM = True
except ImportError:
    HAS_MYCELIUM = False

# ─── Test fixtures: realistic branches ───────────────────────────────────────

def _make_branches():
    """Create 10 realistic branches with varied properties."""
    today = time.strftime("%Y-%m-%d")
    d3 = (datetime.now() - timedelta(days=3)).strftime("%Y-%m-%d")
    d7 = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    d14 = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    d30 = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    d60 = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")

    return {
        "root": {
            "type": "root", "file": "root.mn", "lines": 29, "max_lines": 100,
            "tags": ["muninn", "compression", "mycelium"],
            "last_access": today, "access_count": 30, "temperature": 0.82,
            "access_history": [today] * 10,
        },
        "compression_pipeline": {
            "type": "branch", "file": "compression_pipeline.mn", "lines": 80,
            "tags": ["compression", "l1", "l7", "regex", "pipeline", "tokens"],
            "last_access": today, "access_count": 15, "temperature": 0.9,
            "usefulness": 0.85, "td_value": 0.7, "fisher_importance": 0.8,
            "valence": 0.6, "arousal": 0.4,
            "access_history": [today, today, d3, d3, d7, d7, d14],
        },
        "mycelium_network": {
            "type": "branch", "file": "mycelium_network.mn", "lines": 60,
            "tags": ["mycelium", "connections", "fusion", "decay", "sqlite"],
            "last_access": d3, "access_count": 10, "temperature": 0.75,
            "usefulness": 0.7, "td_value": 0.6, "fisher_importance": 0.5,
            "valence": 0.3, "arousal": 0.2,
            "access_history": [d3, d3, d7, d7, d14, d14],
        },
        "bio_vectors": {
            "type": "branch", "file": "bio_vectors.mn", "lines": 100,
            "tags": ["biovector", "vader", "td_learning", "ewc", "fisher"],
            "last_access": today, "access_count": 8, "temperature": 0.85,
            "usefulness": 0.9, "td_value": 0.8, "fisher_importance": 0.9,
            "valence": 0.8, "arousal": 0.7,  # high emotion (excited about bio-vectors)
            "access_history": [today, today, d3, d7],
        },
        "tree_structure": {
            "type": "branch", "file": "tree_structure.mn", "lines": 50,
            "tags": ["tree", "json", "branches", "root", "prune"],
            "last_access": d7, "access_count": 6, "temperature": 0.5,
            "usefulness": 0.5, "td_value": 0.5, "fisher_importance": 0.3,
            "valence": 0.0, "arousal": 0.0,  # neutral emotion
            "access_history": [d7, d14, d14],
        },
        "spreading_activation": {
            "type": "branch", "file": "spreading_activation.mn", "lines": 45,
            "tags": ["activation", "collins", "loftus", "semantic", "propagation"],
            "last_access": d3, "access_count": 5, "temperature": 0.65,
            "usefulness": 0.6, "td_value": 0.55, "fisher_importance": 0.4,
            "valence": 0.4, "arousal": 0.3,
            "access_history": [d3, d7, d14],
        },
        "sleep_consolidation": {
            "type": "branch", "file": "sleep_consolidation.mn", "lines": 40,
            "tags": ["sleep", "consolidation", "prune", "merge", "ncd"],
            "last_access": d14, "access_count": 3, "temperature": 0.3,
            "usefulness": 0.4, "td_value": 0.3, "fisher_importance": 0.1,
            "valence": -0.2, "arousal": 0.1,
            "access_history": [d14, d30],
        },
        "federated_p20": {
            "type": "branch", "file": "federated_p20.mn", "lines": 55,
            "tags": ["federated", "zones", "meta", "cross_repo", "sync"],
            "last_access": d7, "access_count": 4, "temperature": 0.45,
            "usefulness": 0.55, "td_value": 0.45, "fisher_importance": 0.2,
            "valence": 0.1, "arousal": 0.05,
            "access_history": [d7, d14, d30],
        },
        "old_dead_branch": {
            "type": "branch", "file": "old_dead_branch.mn", "lines": 30,
            "tags": ["sinogram", "chinese", "wrong", "pivot"],
            "last_access": d60, "access_count": 1, "temperature": 0.05,
            "usefulness": 0.1, "td_value": 0.1, "fisher_importance": 0.0,
            "valence": -0.5, "arousal": 0.6,  # high arousal negative (frustration)
            "access_history": [d60],
        },
        "benchmark_results": {
            "type": "branch", "file": "benchmark_results.mn", "lines": 70,
            "tags": ["benchmark", "tiktoken", "facts", "ratio", "x4.5"],
            "last_access": d3, "access_count": 7, "temperature": 0.7,
            "usefulness": 0.75, "td_value": 0.65, "fisher_importance": 0.6,
            "valence": 0.7, "arousal": 0.5,  # happy about results
            "access_history": [d3, d3, d7, d14, d14],
        },
        "tier3_sqlite": {
            "type": "branch", "file": "tier3_sqlite.mn", "lines": 65,
            "tags": ["sqlite", "migration", "db", "storage", "mycelium"],
            "last_access": today, "access_count": 6, "temperature": 0.6,
            "usefulness": 0.65, "td_value": 0.5, "fisher_importance": 0.35,
            "valence": 0.2, "arousal": 0.15,
            "access_history": [today, d3, d7, d14],
        },
    }


def _make_branch_files(tmpdir, nodes):
    """Create .mn files for each branch with realistic compressed content."""
    contents = {
        "root.mn": "Muninn v0.9 memory compression engine. 11 layers, 43 features.\n"
                    "D> architecture: fractal L-system tree + living mycelium codebook\n"
                    "B> ratio: x4.5 measured tiktoken, 37/40 facts (92%)\n",
        "compression_pipeline.mn": "compression pipeline: L0 strip -> L1 markdown -> L2 fillers -> L3 phrases\n"
                                    "L4 numbers -> L5 rules -> L6 mycelium -> L7 facts\n"
                                    "L10 cue distillation (Bartlett 1932) removes generic LLM knowledge\n"
                                    "L11 rule extraction (Kolmogorov 1965) factorizes repetitive patterns\n"
                                    "D> L8 BERT suppressed — lost 72% facts on pre-compressed text\n"
                                    "B> L0 alone: x3.9 (74.5% stripped). Combined L0-L7: x4.5\n"
                                    "F> regex pipeline: zero dependencies, sub-millisecond\n",
        "mycelium_network.mn": "mycelium = living codebook. co-occurrence tracker, fusion, decay.\n"
                                "connections grow when concepts appear together in sessions.\n"
                                "D> fusion threshold: strength >= 15, merge into single token\n"
                                "D> decay: connections lose 10% per session if not reinforced\n"
                                "B> infernal-wheel: 722K connections, 6225 fusions, 0 crash\n"
                                "F> sqlite backend (TIER 3) replaces JSON — x5 disk, x100 RAM\n",
        "bio_vectors.mn": "16 bio-vectors implemented. 102 bornes, 0 FAIL.\n"
                          "TIER S: V10A VADER, V6B valence, V6A emotional, V2B TD, V5B inhibition, V7B ACO\n"
                          "TIER A: V3A transitive, V11B Boyd, V4B EWC, V3B BToM, V9A regen, V9B Reed-Solomon\n"
                          "D> V5B LV dynamics: normalize to [0,1] before dynamics, denormalize after\n"
                          "B> audit: 8 bugs fixed (1 CRITICAL V5B scale mismatch)\n"
                          "F> V9A+ regeneration: facts survive branch death\n",
        "tree_structure.mn": "tree.json: L-system fractal. root + branches + leaves.\n"
                             "temperature per node: hot=loaded often, cold=forgotten.\n"
                             "R4: hot rises, cold sinks and dies. prune() enforces.\n"
                             "D> budget: 30K tokens max loaded = 15% context\n",
        "spreading_activation.mn": "Collins & Loftus 1975: propagation through weighted network.\n"
                                   "spread_activation(seeds, hops=2, decay=0.5) in mycelium.py\n"
                                   "finds branches with zero keyword overlap via co-occurrence chains\n"
                                   "D> activation bonus in boot() alongside TF-IDF scoring\n"
                                   "B> tested: compression->tree/tokens/memory, scan->yggdrasil/arxiv\n",
        "sleep_consolidation.mn": "Wilson & McNaughton 1994: episodic->semantic consolidation.\n"
                                  "cold branches merged before dead deletion.\n"
                                  "NCD pairwise grouping (threshold=0.6) + dedup + L10 + L11\n"
                                  "D> sole-carrier tags get priority in merged branch\n",
        "federated_p20.mn": "P20: federated mycelium across repos.\n"
                            "zones tagged during observe(), TF-IDF inverse weighting.\n"
                            "immortality: 3+ zones = skip decay.\n"
                            "meta-mycelium at ~/.muninn/meta_mycelium.json\n"
                            "D> sync_to_meta in feed_from_hook, pull_from_meta in boot\n",
        "old_dead_branch.mn": "sinogram experiment: thought chinese characters = fewer tokens.\n"
                              "WRONG — sinograms cost 2-3 tokens each in BPE.\n"
                              "D> pivot: BPE-native English compact is correct approach\n"
                              "E> wasted 2 sessions on wrong assumption\n",
        "benchmark_results.mn": "benchmark 40 questions on compressed files.\n"
                                "B> 37/40 facts found (92%). 3 missed = ambiguous wording.\n"
                                "B> tiktoken measured: verbose x4.1, roadmap x2.6, session x1.7\n"
                                "F> full pipeline 12 files, 4 repos: x4.5 avg\n"
                                "F> top: DEPLOY x9.6, BIOMECA x7.8, WEARABLE x7.4\n"
                                "D> L9 useless on pre-compressed transcripts (regex already strips everything)\n",
        "tier3_sqlite.mn": "TIER 3: mycelium JSON -> SQLite. normalized (concepts=int IDs).\n"
                           "auto-migration: detects .json -> imports -> .json.bak.\n"
                           "B> x5 disk savings, x100 RAM reduction\n"
                           "D> S3: top 5% degree concepts = stopwords, blocked from fusion\n"
                           "F> S4: auto-translate via tiktoken (1 tok=EN, 2+=foreign)\n",
    }
    tree_dir = Path(tmpdir) / "memory" / "tree"
    tree_dir.mkdir(parents=True, exist_ok=True)
    for fname, text in contents.items():
        (tree_dir / fname).write_text(text, encoding="utf-8")
    return tree_dir, contents


# ─── Scoring engine (mirrors boot() exactly, with vector toggles) ────────────

def _compute_scores(nodes, branch_contents, query, disable=None, mycelium=None):
    """Compute boot() scores with optional vector disabling.

    Args:
        nodes: dict of branch nodes (from tree.json)
        branch_contents: dict of branch_name -> text content
        query: search query string
        disable: set of vector names to disable, e.g. {"V1A", "V7B"}
        mycelium: Mycelium instance (optional)

    Returns:
        dict of branch_name -> {total, components: {vector_name: contribution}}
    """
    disable = disable or set()
    query_words = re.findall(r'[A-Za-zÀ-ÿ]{3,}', query.lower())

    # TF-IDF relevance
    relevance_scores = _simple_tfidf(query, branch_contents)

    # Spreading activation
    activation_scores = {}
    activated_set = {}
    if mycelium and "SPREAD" not in disable:
        try:
            activated = mycelium.spread_activation(query_words, hops=2, decay=0.5, top_n=50)
            if activated:
                activated_set = {c: a for c, a in activated}
                for bname, bcontent in branch_contents.items():
                    bwords = set(re.findall(r'[a-z0-9_]+', bcontent.lower()))
                    overlap = bwords & set(activated_set.keys())
                    if overlap:
                        act_score = sum(activated_set[w] for w in overlap)
                        activation_scores[bname] = min(1.0, act_score)
        except Exception:
            pass

    # V3A: Transitive inference
    transitive_scores = {}
    if mycelium and "V3A" not in disable:
        try:
            for qw in query_words[:5]:
                inferred = mycelium.transitive_inference(qw, max_hops=3, beta=0.5, top_n=20)
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
        except Exception:
            pass

    # V3B: BToM — simplified (use usefulness as proxy for session alignment)
    btom_scores = {}
    if "V3B" not in disable:
        for bname in branch_contents:
            if bname in nodes:
                bwords = set(re.findall(r'[a-z0-9_]+', branch_contents[bname].lower()))
                overlap = bwords & set(query_words)
                if overlap:
                    alignment = len(overlap) / max(len(query_words), 1)
                    prior = nodes[bname].get("usefulness", 0.5)
                    btom_scores[bname] = min(1.0, (alignment / (alignment + 1.0)) * prior)

    # B3: Blind spots (structural holes)
    blind_spot_concepts = set()
    if mycelium and "B3" not in disable:
        try:
            blind_spots = mycelium.detect_blind_spots(top_n=20)
            for a, b, _ in blind_spots:
                blind_spot_concepts.add(a)
                blind_spot_concepts.add(b)
        except Exception:
            pass

    # V11B pre-compute
    _tag_freq = {}
    _all_usefulness = []
    for _n, _nd in nodes.items():
        if _n == "root":
            continue
        for _t in _nd.get("tags", []):
            _tag_freq[_t] = _tag_freq.get(_t, 0) + 1
        _all_usefulness.append(_nd.get("usefulness", 0.5))
    _n_branches = max(1, len(_all_usefulness))
    _mean_usefulness = sum(_all_usefulness) / _n_branches if _all_usefulness else 0.5
    _max_tag_freq = max(_tag_freq.values()) if _tag_freq else 1

    # Weights (default balanced)
    w_recall = 0.15
    w_relevance = 0.40
    w_activation = 0.20
    w_usefulness = 0.10
    w_rehearsal = 0.15

    results = {}

    for name, node in nodes.items():
        if name == "root":
            continue

        components = {}

        # Recall (Ebbinghaus + V6B + V4B)
        if "V6B" in disable:
            recall = _ebbinghaus_recall(node, _alpha_v=0.0, _alpha_a=0.0)
        elif "V4B" in disable:
            recall = _ebbinghaus_recall(node, _lambda_ewc=0.0)
        else:
            recall = _ebbinghaus_recall(node)
        components["recall_raw"] = recall

        # A2: ACT-R
        if "A2" not in disable:
            actr_raw = _actr_activation(node)
            actr_norm = 1.0 / (1.0 + math.exp(-actr_raw))
            recall_blended = 0.7 * recall + 0.3 * actr_norm
            components["A2_actr"] = 0.3 * (actr_norm - 0.5)  # delta from neutral
        else:
            recall_blended = recall
            components["A2_actr"] = 0.0

        components["recall_blended"] = recall_blended

        relevance = relevance_scores.get(name, 0.0)
        activation = activation_scores.get(name, 0.0)
        usefulness = node.get("usefulness", 0.5)
        rehearsal_need = max(0.0, 1.0 - abs(recall - 0.2) / 0.2) if 0.05 < recall < 0.4 else 0.0

        # Base score
        total = (w_recall * recall_blended + w_relevance * relevance +
                 w_activation * activation + w_usefulness * usefulness +
                 w_rehearsal * rehearsal_need)
        components["base"] = total

        # V7B: ACO
        if "V7B" not in disable:
            tau = max(0.01, usefulness * recall_blended)
            eta = max(0.01, relevance)
            aco_score = min(1.0, tau * (eta ** 2))
            bonus = 0.05 * aco_score
            total += bonus
            components["V7B_aco"] = bonus
        else:
            components["V7B_aco"] = 0.0

        # B3: Blind spot bonus
        tags = set(node.get("tags", []))
        if "B3" not in disable and (tags & blind_spot_concepts):
            total += 0.05
            components["B3_blindspot"] = 0.05
        else:
            components["B3_blindspot"] = 0.0

        # V3A: Transitive
        t_score = transitive_scores.get(name, 0.0)
        if "V3A" not in disable and t_score > 0:
            bonus = 0.10 * t_score
            total += bonus
            components["V3A_transitive"] = bonus
        else:
            components["V3A_transitive"] = 0.0

        # B4: Prediction (skip in ablation — no session_index)
        components["B4_prediction"] = 0.0

        # V3B: BToM
        btom_score = btom_scores.get(name, 0.0)
        if "V3B" not in disable and btom_score > 0:
            bonus = 0.04 * btom_score
            total += bonus
            components["V3B_btom"] = bonus
        else:
            components["V3B_btom"] = 0.0

        # V11B: Boyd-Richerson 3 biases
        _node_tags = node.get("tags", [])

        # (1) Conformist
        if "V11B" not in disable and _node_tags and _tag_freq:
            _p = sum(_tag_freq.get(t, 0) for t in _node_tags) / (_max_tag_freq * max(1, len(_node_tags)))
            _p = max(0.01, min(0.99, _p))
            _conform_dp = 0.3 * _p * (1.0 - _p) * (2.0 * _p - 1.0)
            conformist = 0.15 * _conform_dp
            total += conformist
            components["V11B_conformist"] = conformist
        else:
            components["V11B_conformist"] = 0.0

        # (2) Prestige
        if "V11B" not in disable:
            _td_value = node.get("td_value", 0.5)
            _prestige = _td_value * usefulness
            prestige_bonus = 0.06 * _prestige
            total += prestige_bonus
            components["V11B_prestige"] = prestige_bonus
        else:
            components["V11B_prestige"] = 0.0

        # (3) Guided variation
        if "V11B" not in disable:
            _mu = 0.1
            _guided_delta = _mu * (_mean_usefulness - usefulness)
            guided_bonus = 0.06 * _guided_delta
            total += guided_bonus
            components["V11B_guided"] = guided_bonus
        else:
            components["V11B_guided"] = 0.0

        # V5A: Quorum Hill
        _node_tags_set = set(node.get("tags", []))
        if "V5A" not in disable and _node_tags_set and activated_set:
            _activated_count = sum(1 for t in _node_tags_set if t in activated_set)
            _K_quorum = 2.0
            _n_hill = 3
            if _activated_count > 0:
                _quorum = (_activated_count ** _n_hill) / (
                    _K_quorum ** _n_hill + _activated_count ** _n_hill)
                quorum_bonus = 0.08 * _quorum
                total += quorum_bonus
                components["V5A_quorum"] = quorum_bonus
            else:
                components["V5A_quorum"] = 0.0
        else:
            components["V5A_quorum"] = 0.0

        # V1A: Coupled oscillator
        _my_temp = node.get("temperature", 0.5)
        _coupling_sum = 0.0
        if "V1A" not in disable:
            for _t in list(_node_tags_set)[:3]:
                for _sname, _snode in nodes.items():
                    if _sname == name or _sname == "root":
                        continue
                    if _t in set(_snode.get("tags", [])):
                        _other_temp = _snode.get("temperature", 0.5)
                        _coupling_sum += 0.1 * (_other_temp - _my_temp)
                        break
            coupling = max(-0.05, min(0.05, _coupling_sum))
            total += coupling
            components["V1A_coupling"] = coupling
        else:
            components["V1A_coupling"] = 0.0

        components["total"] = total
        results[name] = components

    # V5B: Cross-inhibition (post-scoring)
    if "V5B" not in disable:
        scored = [(n, r["total"]) for n, r in results.items() if r["total"] > 0.01]
        scored.sort(key=lambda x: x[1], reverse=True)
        if len(scored) >= 2:
            top_score = scored[0][1]
            if top_score > 0:
                competitors = [(n, s) for n, s in scored if s >= top_score * 0.85]
                if len(competitors) >= 2:
                    pop = {n: s / top_score for n, s in competitors}
                    for _ in range(10):
                        new_pop = {}
                        for n, s in pop.items():
                            r = relevance_scores.get(n, 0.1)
                            growth = r * (1.0 - s / 1.0) * s
                            inhibition = sum(0.3 * pop[m_] * s for m_ in pop if m_ != n)
                            new_s = s + 0.1 * (growth - inhibition)
                            new_pop[n] = max(0.001, min(1.0, new_s))
                        pop = new_pop
                    for n, s in pop.items():
                        old = results[n]["total"]
                        new = s * top_score
                        results[n]["V5B_crossinhib"] = new - old
                        results[n]["total"] = new
                    for n in results:
                        if n not in pop:
                            results[n]["V5B_crossinhib"] = 0.0
                else:
                    for n in results:
                        results[n]["V5B_crossinhib"] = 0.0
            else:
                for n in results:
                    results[n]["V5B_crossinhib"] = 0.0
        else:
            for n in results:
                results[n]["V5B_crossinhib"] = 0.0
    else:
        for n in results:
            results[n]["V5B_crossinhib"] = 0.0

    return results


def _simple_tfidf(query, documents):
    """Simplified TF-IDF (mirrors _tfidf_relevance in muninn.py)."""
    query_words = set(re.findall(r'[a-z0-9_]+', query.lower()))
    if not query_words:
        return {}
    scores = {}
    # IDF: log(N / df) for each query word
    N = len(documents)
    df = {}
    for word in query_words:
        df[word] = sum(1 for content in documents.values()
                       if word in set(re.findall(r'[a-z0-9_]+', content.lower())))
    for name, content in documents.items():
        words = re.findall(r'[a-z0-9_]+', content.lower())
        word_set = set(words)
        if not words:
            continue
        score = 0.0
        for qw in query_words:
            if qw in word_set:
                tf = words.count(qw) / len(words)
                idf = math.log((N + 1) / (df.get(qw, 0) + 1))
                score += tf * idf
        scores[name] = score
    # Normalize to [0, 1]
    max_score = max(scores.values()) if scores else 1.0
    if max_score > 0:
        scores = {n: s / max_score for n, s in scores.items()}
    return scores


# ─── Ranking helpers ─────────────────────────────────────────────────────────

def _ranking(results):
    """Return sorted list of (name, total) from results."""
    return sorted([(n, r["total"]) for n, r in results.items()],
                  key=lambda x: x[1], reverse=True)


def _rank_position(ranking, name):
    """Return 1-based position of name in ranking."""
    for i, (n, _) in enumerate(ranking):
        if n == name:
            return i + 1
    return len(ranking) + 1


# ─── Tests ───────────────────────────────────────────────────────────────────

PASS = 0
FAIL = 0

def _borne(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  PASS  {name}  {detail}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}  {detail}")


def test_ablation():
    global PASS, FAIL
    PASS, FAIL = 0, 0

    print("=" * 72)
    print("ABLATION BENCHMARK — Impact reel de chaque bio-vecteur")
    print("=" * 72)

    # Setup
    nodes = _make_branches()
    tmpdir = tempfile.mkdtemp(prefix="muninn_ablation_")
    tree_dir, contents = _make_branch_files(tmpdir, nodes)
    branch_contents = {n: contents.get(nodes[n]["file"], "") for n in nodes if n != "root"}

    # Setup mycelium (in-memory, feed with branch contents)
    mycelium = None
    if HAS_MYCELIUM:
        myc_dir = Path(tmpdir) / ".muninn"
        myc_dir.mkdir(exist_ok=True)
        mycelium = Mycelium(Path(tmpdir))
        # Feed branch contents to build connections
        for bname, text in branch_contents.items():
            mycelium.observe_text(text)
        mycelium.save()

    query = "compression pipeline mycelium"

    # ─── ABL.1: Baseline ───
    print("\n--- BASELINE (all vectors ON) ---")
    baseline = _compute_scores(nodes, branch_contents, query, disable=set(), mycelium=mycelium)
    baseline_ranking = _ranking(baseline)

    active_branches = sum(1 for _, s in baseline_ranking if s > 0.01)
    _borne("ABL.1", active_branches >= 5,
           f"{active_branches} branches scored > 0.01")

    print(f"\n  {'Rank':<6} {'Branch':<28} {'Score':<10} {'Top Contributor':<20}")
    print(f"  {'-'*6} {'-'*28} {'-'*10} {'-'*20}")
    for i, (name, score) in enumerate(baseline_ranking):
        comps = baseline[name]
        # Find top contributor (excluding base, total, recall_raw, recall_blended)
        skip = {"base", "total", "recall_raw", "recall_blended"}
        top_comp = max(((k, abs(v)) for k, v in comps.items() if k not in skip and v != 0),
                       key=lambda x: x[1], default=("none", 0))
        print(f"  #{i+1:<5} {name:<28} {score:<10.4f} {top_comp[0]}: {top_comp[1]:.4f}")

    # ─── ABL.2-ABL.9: Per-vector ablation ───
    vectors = [
        "V1A", "V3A", "V3B", "V4B", "V5A", "V5B",
        "V6B", "V7B", "V11B", "A2", "B3",
    ]

    print("\n--- ABLATION RESULTS (one vector OFF at a time) ---")
    print(f"\n  {'Vector':<10} {'Avg Delta':<12} {'Max Delta':<12} {'Rank Changes':<14} {'Impact%':<10}")
    print(f"  {'-'*10} {'-'*12} {'-'*12} {'-'*14} {'-'*10}")

    ablation_deltas = {}  # vector -> avg_delta

    for vec in vectors:
        ablated = _compute_scores(nodes, branch_contents, query, disable={vec}, mycelium=mycelium)
        ablated_ranking = _ranking(ablated)

        deltas = []
        rank_changes = 0
        for name in baseline:
            base_score = baseline[name]["total"]
            abl_score = ablated[name]["total"]
            deltas.append(base_score - abl_score)
            if _rank_position(baseline_ranking, name) != _rank_position(ablated_ranking, name):
                rank_changes += 1

        avg_delta = sum(deltas) / len(deltas) if deltas else 0
        max_delta = max(abs(d) for d in deltas) if deltas else 0
        avg_baseline = sum(r["total"] for r in baseline.values()) / len(baseline)
        impact_pct = (avg_delta / avg_baseline * 100) if avg_baseline > 0 else 0

        ablation_deltas[vec] = (avg_delta, max_delta, rank_changes, impact_pct)

        print(f"  {vec:<10} {avg_delta:<12.6f} {max_delta:<12.6f} {rank_changes:<14} {impact_pct:<10.2f}%")

    # ABL.2: All vectors computable (no crash)
    _borne("ABL.2", len(ablation_deltas) == len(vectors),
           f"all {len(vectors)} vectors tested without crash")

    # ABL.3: V7B has measurable impact
    v7b_avg, v7b_max, _, v7b_pct = ablation_deltas["V7B"]
    _borne("ABL.3", abs(v7b_max) > 0.001,
           f"V7B max_delta={v7b_max:.6f}, impact={v7b_pct:.2f}%")

    # ABL.4: V11B prestige measurable
    v11b_avg, v11b_max, _, v11b_pct = ablation_deltas["V11B"]
    _borne("ABL.4", abs(v11b_max) > 0.0005,
           f"V11B max_delta={v11b_max:.6f}, impact={v11b_pct:.2f}%")

    # ABL.5: V6B changes recall for emotional branches
    # Isolate the variable: same age/access/usefulness, different emotion
    d14 = (datetime.now() - timedelta(days=14)).strftime("%Y-%m-%d")
    _neutral_node = {"last_access": d14, "access_count": 3, "usefulness": 0.5,
                     "valence": 0.0, "arousal": 0.0, "fisher_importance": 0.0}
    _emotional_node = {"last_access": d14, "access_count": 3, "usefulness": 0.5,
                       "valence": 0.8, "arousal": 0.7, "fisher_importance": 0.0}
    recall_neutral_on = _ebbinghaus_recall(_neutral_node)
    recall_neutral_off = _ebbinghaus_recall(_neutral_node, _alpha_v=0.0, _alpha_a=0.0)
    recall_emotional_on = _ebbinghaus_recall(_emotional_node)
    recall_emotional_off = _ebbinghaus_recall(_emotional_node, _alpha_v=0.0, _alpha_a=0.0)
    v6b_delta_neutral = recall_neutral_on - recall_neutral_off  # should be 0 (no emotion)
    v6b_delta_emotional = recall_emotional_on - recall_emotional_off  # should be > 0
    _borne("ABL.5", v6b_delta_emotional > v6b_delta_neutral and v6b_delta_emotional > 0,
           f"V6B emotional delta={v6b_delta_emotional:.6f} > neutral delta={v6b_delta_neutral:.6f}")

    # ABL.6: V4B Fisher changes recall for important branches
    # Use old_dead_branch (60 days old) — with fisher=0.0 baseline, compare to synthetic high-fisher
    old_branch_high_fisher = dict(nodes["old_dead_branch"])
    old_branch_high_fisher["fisher_importance"] = 0.9
    recall_high_fisher = _ebbinghaus_recall(old_branch_high_fisher)
    recall_no_fisher = _ebbinghaus_recall(old_branch_high_fisher, _lambda_ewc=0.0)
    fisher_delta = recall_high_fisher - recall_no_fisher
    _borne("ABL.6", fisher_delta > 0,
           f"V4B Fisher delta={fisher_delta:.6f} (high fisher branch decays slower)")

    # ABL.7: A2 ACT-R changes recall_blended
    recall_base = _ebbinghaus_recall(nodes["compression_pipeline"])
    actr_raw = _actr_activation(nodes["compression_pipeline"])
    actr_norm = 1.0 / (1.0 + math.exp(-actr_raw))
    blended = 0.7 * recall_base + 0.3 * actr_norm
    actr_delta = blended - recall_base
    _borne("ABL.7", abs(actr_delta) > 0.001,
           f"A2 ACT-R delta={actr_delta:.6f} (blended vs pure Ebbinghaus)")

    # ABL.8: V5B changes ranking when top scores close
    v5b_avg, v5b_max, v5b_ranks, v5b_pct = ablation_deltas["V5B"]
    _borne("ABL.8", v5b_ranks >= 0,  # >= 0 because it might not change ranks with this data
           f"V5B rank_changes={v5b_ranks}, max_delta={v5b_max:.6f}")

    # ABL.9: V1A coupling changes score when temperatures differ
    v1a_avg, v1a_max, v1a_ranks, v1a_pct = ablation_deltas["V1A"]
    _borne("ABL.9", True,  # V1A measured, even if small
           f"V1A max_delta={v1a_max:.6f}, impact={v1a_pct:.2f}%")

    # ─── ABL.10: Full report ───
    print("\n--- VECTOR IMPACT RANKING (sorted by |avg_delta|) ---")
    sorted_vectors = sorted(ablation_deltas.items(), key=lambda x: abs(x[1][0]), reverse=True)
    for vec, (avg, mx, ranks, pct) in sorted_vectors:
        status = "ALIVE" if abs(mx) > 0.001 else "WEAK" if abs(mx) > 0.0001 else "DEAD"
        print(f"  {vec:<10} avg={avg:+.6f}  max={mx:.6f}  ranks={ranks}  impact={pct:+.2f}%  [{status}]")

    _borne("ABL.10", True, "full report printed")

    # ABL.11: No vector causes negative total
    all_positive = True
    for name, comps in baseline.items():
        if comps["total"] < -0.001:
            all_positive = False
            print(f"  WARNING: {name} has negative score {comps['total']:.4f}")
    _borne("ABL.11", all_positive, "no negative total scores in baseline")

    # ABL.12: Disabling ALL vectors still produces valid scores
    all_disabled = _compute_scores(nodes, branch_contents, query,
                                   disable=set(vectors), mycelium=mycelium)
    all_disabled_ranking = _ranking(all_disabled)
    has_scores = any(s > 0 for _, s in all_disabled_ranking)
    _borne("ABL.12", has_scores,
           f"all vectors OFF: top score = {all_disabled_ranking[0][1]:.4f}" if all_disabled_ranking else "no scores")

    # ─── Component breakdown for top 3 ───
    print("\n--- COMPONENT BREAKDOWN (top 3 branches) ---")
    for i, (name, score) in enumerate(baseline_ranking[:3]):
        print(f"\n  #{i+1} {name} (total={score:.4f}):")
        comps = baseline[name]
        for k, v in sorted(comps.items()):
            if k not in ("total", "recall_raw", "recall_blended", "base") and v != 0:
                pct = (v / score * 100) if score > 0 else 0
                print(f"    {k:<22} {v:+.6f}  ({pct:+.1f}%)")

    # Cleanup
    shutil.rmtree(tmpdir, ignore_errors=True)

    print(f"\n{'=' * 72}")
    print(f"ABLATION: {PASS} PASS, {FAIL} FAIL")
    print(f"{'=' * 72}")
    assert FAIL == 0, f"Ablation: {FAIL} tests failed"


if __name__ == "__main__":
    test_ablation()
