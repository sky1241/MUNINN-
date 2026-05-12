"""P3.2 split (2026-05-10) — `prune` + 3 helpers extracted from muninn_tree.py.

Consolidates the cold/hot/dead lifecycle code:
- `_sleep_consolidate` (was muninn_tree.py:2473-2629)
- `_light_prune` (was muninn_tree.py:2729-2770)
- `_auto_backup_tree` (was muninn_tree.py:2773-2794)
- `prune` (was muninn_tree.py:2797-3211)

Re-exported via `from muninn_tree_prune import …` at end of muninn_tree.py.
External code keeps importing `from muninn_tree import prune,
_sleep_consolidate, _light_prune, _auto_backup_tree`. No standalone shim
in muninn/ (see test_chunk_d11_shim_drift.py engine_only).

NOTE on `_sleep_consolidate` cross-module call: muninn_feed.py imports it
via `_m._sleep_consolidate` (proxy) — still works since muninn_tree.py
re-exports it at the end (which makes it reachable on the muninn package).
"""
import json
import re
import sys
import time
from pathlib import Path

from muninn_tree import (
    _m,
    _atomic_text_write,
    _days_since,
    _ebbinghaus_recall,
    _safe_read_mn,
    compute_hash,
    load_tree,
    refresh_tree_metadata,
    save_tree,
)


def _sleep_consolidate(cold_branches: list[tuple[str, dict]], nodes: dict,
                       ncd_threshold: float = 0.6) -> list[tuple[str, str]]:
    """Consolidate similar cold branches into single dense branches.

    Like the brain during sleep: episodic memories (sessions) get merged
    into semantic memory (general rules). Uses NCD to find similar branches,
    then merges + re-compresses with the existing pipeline (dedup,
    contradiction resolution, L10, L11). Zero API cost.

    Args:
        cold_branches: list of (name, node_dict) for cold branches
        nodes: full tree nodes dict (for in-place mutation)
        ncd_threshold: max NCD distance to consider branches similar (0-1)

    Returns:
        list of (merged_name, merged_content) for newly created branches
    """
    if len(cold_branches) < 2:
        return []

    # P8: Cap to top-20 coldest branches by recall score to avoid O(n^2) NCD
    MAX_NCD_BRANCHES = 20
    if len(cold_branches) > MAX_NCD_BRANCHES:
        cold_branches = sorted(cold_branches,
                               key=lambda x: _ebbinghaus_recall(x[1]))[:MAX_NCD_BRANCHES]

    # 1. Read all cold branch contents
    contents = {}
    for name, node in cold_branches:
        filepath = _m.TREE_DIR / node["file"]
        try:
            contents[name] = filepath.read_text(encoding="utf-8")
        except (FileNotFoundError, OSError):
            pass

    if len(contents) < 2:
        return []

    # 2. Compute NCD pairwise and group similar branches
    names = list(contents.keys())
    merged_into = {}  # name -> group_leader
    groups = {}  # leader -> [members]

    for i in range(len(names)):
        if names[i] in merged_into:
            continue
        leader = names[i]
        groups[leader] = [leader]
        for j in range(i + 1, len(names)):
            if names[j] in merged_into:
                continue
            # Check similarity against ALL existing group members, not just leader
            all_similar = all(
                _m._ncd(contents[m], contents[names[j]]) < ncd_threshold
                for m in groups[leader]
            )
            if all_similar:
                groups[leader].append(names[j])
                merged_into[names[j]] = leader

    # 3. Consolidate each group with 2+ members
    results = []
    for leader, members in groups.items():
        if len(members) < 2:
            continue

        # Concatenate all branch contents
        combined = "\n".join(contents[m] for m in members)

        # Line-level dedup (exact + near)
        seen_lines = set()
        deduped = []
        for line in combined.split("\n"):
            stripped = line.strip()
            if not stripped:
                continue
            if stripped in seen_lines:
                continue
            seen_lines.add(stripped)
            deduped.append(line)
        combined = "\n".join(deduped)

        # Run through existing compression pipeline (free, no API)
        combined = _m._resolve_contradictions(combined)
        combined = _m._cue_distill(combined)
        combined = _m._extract_rules(combined)

        # Name the consolidated branch (strip existing _consolidated suffix to avoid stacking)
        base_leader = re.sub(r'(_consolidated)+$', '', leader)
        merged_name = f"{base_leader}_consolidated"

        # Write the consolidated file
        merged_file = f"{merged_name}.mn"
        merged_path = _m.TREE_DIR / merged_file
        _atomic_text_write(merged_path, combined)

        # Collect tags from all merged branches
        all_tags = set()
        for m in members:
            node = nodes.get(m, {})
            all_tags.update(node.get("tags", []))

        # Prioritize sole-carrier tags (V9B protection: don't lose unique concepts)
        # Count how many OTHER branches (not in this merge group) carry each tag
        _other_branches = {n: nd for n, nd in nodes.items()
                          if n not in members and n != "root" and nd.get("type") == "branch"}
        _sole_tags = []  # tags only carried by members of this merge
        _common_tags = []
        for t in sorted(all_tags):
            carried_elsewhere = any(t in _ob.get("tags", []) for _ob in _other_branches.values())
            if not carried_elsewhere:
                _sole_tags.append(t)
            else:
                _common_tags.append(t)
        # Sole-carrier tags first, then fill remaining slots with common tags
        _final_tags = _sole_tags + [t for t in _common_tags if t not in _sole_tags]

        # Create consolidated node in tree
        nodes[merged_name] = {
            "type": "branch",
            "file": merged_file,
            "lines": len(combined.split("\n")),
            "max_lines": 150,
            "tags": _final_tags[:max(10, len(_sole_tags))],  # keep ALL sole-carriers even if >10
            "temperature": 0.1,  # warm enough to not get immediately pruned
            "access_count": max(nodes.get(m, {}).get("access_count", 0) for m in members),  # X9: max not sum, prevents immortalization
            "last_access": max(nodes.get(m, {}).get("last_access", time.strftime("%Y-%m-%d")) for m in members),
            "created": time.strftime("%Y-%m-%d"),
            "usefulness": round(max(nodes.get(m, {}).get("usefulness", 0.5) for m in members), 3),
            "td_value": round(max(nodes.get(m, {}).get("td_value", 0.5) for m in members), 4),
            "fisher_importance": round(max(nodes.get(m, {}).get("fisher_importance", 0.0) for m in members), 4),
        }

        # Add as child of root
        if "children" in nodes.get("root", {}):
            nodes["root"]["children"].append(merged_name)

        # Remove old branches
        for m in members:
            node = nodes.get(m)
            if node:
                old_path = _m.TREE_DIR / node["file"]
                if old_path.exists():
                    try:
                        old_path.unlink()
                    except OSError:
                        pass
            if m in nodes.get("root", {}).get("children", []):
                nodes["root"]["children"].remove(m)
            nodes.pop(m, None)

        orig_lines = sum(len(contents[m].split("\n")) for m in members)
        results.append((merged_name, combined))
        print(f"  CONSOLIDATED {len(members)} branches -> {merged_name}: "
              f"{orig_lines} -> {len(combined.split(chr(10)))} lines")

    return results


def _light_prune():
    """B15: Fast auto-prune for hooks — kills dead + dust only.

    No L9 recompression, no sleep consolidation, no H1/H2 dreams.
    Just Ebbinghaus recall check + B14 dust removal + file cleanup.
    Runs in < 1s even on 2000+ branches.
    """
    tree = load_tree()
    nodes = tree["nodes"]
    refresh_tree_metadata(tree)

    branches = {n: d for n, d in nodes.items() if n != "root"}
    if not branches:
        return 0

    removed = 0
    for name in list(branches.keys()):
        node = branches[name]
        recall = _ebbinghaus_recall(node)
        lines = node.get("lines", 0)
        temp = node.get("temperature", 0)

        # Dead: forgotten (R < 0.05) OR dust (<=3 lines and cold)
        is_dead = recall < 0.05
        is_dust = lines <= 3 and temp < 0.3

        if is_dead or is_dust:
            # Delete file
            branch_file = _m.TREE_DIR / node.get("file", "")
            if branch_file.exists():
                branch_file.unlink()
            # Remove from tree
            del nodes[name]
            root_children = nodes.get("root", {}).get("children", [])
            if name in root_children:
                root_children.remove(name)
            removed += 1

    if removed > 0:
        save_tree(tree)
        print(f"  LIGHT PRUNE: removed {removed} dead/dust branches ({len(nodes)-1} remaining)", file=sys.stderr)
    return removed


def _auto_backup_tree():
    """A7: Auto-backup tree before destructive prune.

    Creates .muninn/backups/prune_before_<timestamp>.tar.gz
    """
    if not _m._REPO_PATH:
        return
    backup_dir = _m._REPO_PATH / ".muninn" / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"prune_before_{ts}.tar.gz"
    try:
        import tarfile
        with tarfile.open(str(backup_path), "w:gz") as tar:
            tar.add(str(_m.TREE_DIR), arcname="tree")
        print(f"  A7: Tree backed up to {backup_path.name}", file=sys.stderr)
        # Keep only last 5 backups
        backups = sorted(backup_dir.glob("prune_before_*.tar.gz"))
        for old in backups[:-5]:
            old.unlink()
    except Exception as e:
        print(f"  A7: Backup failed: {e}", file=sys.stderr)


def prune(dry_run: bool = True, include_dreams: bool = False):
    """R4: promote hot, demote cold, kill dead. Uses temperature score.

    H.3 (2026-05-12): when `include_dreams=True`, also invoke Sleep
    Consolidation (`mycelium.dream()`, Wilson & McNaughton 1994) after the
    tree prune. Off by default to avoid surprise inserts in mycelium.db on
    every routine prune.
    """
    tree = load_tree()
    nodes = tree["nodes"]
    refresh_tree_metadata(tree)

    # A7: Auto-backup before destructive prune
    if not dry_run:
        _auto_backup_tree()

    branches = {n: d for n, d in nodes.items() if n != "root"}
    if not branches:
        print("  No branches to prune.")
        return

    print(f"=== MUNINN PRUNE (R4) === {'[DRY RUN]' if dry_run else ''}")
    print(f"  Branches: {len(branches)}")
    print()

    # V9B: Reed-Solomon redundancy (Reed & Solomon 1960)
    # Compute concept redundancy: how many branches carry each concept.
    # Branches that are sole carriers (redundancy=1) of concepts get protection.
    # d_min >= n-k+1: minimum distance determines correction capability.
    _concept_carriers = {}  # concept -> set of branch names
    for bname, bnode in branches.items():
        for tag in bnode.get("tags", []):
            _concept_carriers.setdefault(tag, set()).add(bname)
    # Fragile concepts: carried by only 1 branch (redundancy=1, no error correction)
    _fragile_branches = set()  # branches that are sole carriers
    for concept, carriers in _concept_carriers.items():
        if len(carriers) == 1:
            _fragile_branches.update(carriers)

    # I2: Competitive Suppression (Perelson 1989)
    # Similar branches suppress each other's recall — the weaker one dies faster.
    # recall_eff_i = recall_i - alpha * sum(NCD_sim(i,j) * recall_j) for NCD < 0.4
    _i2_alpha = 0.1
    _branch_recalls = {}
    for bname, bnode in branches.items():
        _branch_recalls[bname] = _ebbinghaus_recall(bnode)
    # I2: Only apply competitive suppression to non-hot branches (recall < 0.4).
    # Hot branches won't be pruned anyway — O(n²) NCD on all branches is catastrophic
    # (486s on 2106 branches = 4.4M zlib calls). Pre-filter to at-risk branches only.
    _suppression = {b: 0.0 for b in branches}
    _atrisk = [b for b in branches if _branch_recalls[b] < 0.4]
    if 2 <= len(_atrisk) <= 500:  # skip if too few or too many (safety cap)
        _branch_content = {}
        for bname in _atrisk:
            bnode = branches[bname]
            fpath = _m.TREE_DIR / bnode.get("file", "")
            if fpath.is_file():
                try:
                    _branch_content[bname] = fpath.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    _branch_content[bname] = ""
        _atrisk_names = list(_branch_content.keys())
        for i in range(len(_atrisk_names)):
            bi = _atrisk_names[i]
            if not _branch_content.get(bi):
                continue
            for j in range(i + 1, len(_atrisk_names)):
                bj = _atrisk_names[j]
                if not _branch_content.get(bj):
                    continue
                ncd = _m._ncd(_branch_content[bi], _branch_content[bj])
                if ncd < 0.4:  # very similar
                    sim = 1.0 - ncd
                    _suppression[bi] += sim * _branch_recalls.get(bj, 0)
                    _suppression[bj] += sim * _branch_recalls.get(bi, 0)
    # Apply suppression to effective recall
    _effective_recall = {}
    for bname in branches:
        _effective_recall[bname] = max(0.0,
            _branch_recalls[bname] - _i2_alpha * _suppression[bname])

    # I3: Negative Selection (Forrest 1994)
    # Detect anomalous branches by comparing to median profile.
    # Anomalies (too long, zero facts, extreme density) get demoted to cold.
    _i3_anomalies = set()
    if len(branches) >= 3:
        import statistics
        _line_counts = []
        _fact_ratios = []
        for bname, bnode in branches.items():
            lc = bnode.get("lines", 0)
            # Compute fact ratio from tags in content
            fpath = _m.TREE_DIR / bnode.get("file", "")
            tagged = 0
            total = max(1, lc)
            if fpath.is_file():
                try:
                    text = fpath.read_text(encoding="utf-8")
                    for tl in text.split("\n"):
                        st = tl.strip()
                        if st and st[:2] in ("D>", "B>", "F>", "E>", "A>"):
                            tagged += 1
                    lc = len(text.split("\n"))
                    total = max(1, lc)
                except (OSError, UnicodeDecodeError):
                    pass
            _line_counts.append(lc)
            _fact_ratios.append(tagged / total)

        _med_lines = statistics.median(_line_counts) if _line_counts else 10
        _med_facts = statistics.median(_fact_ratios) if _fact_ratios else 0.3

        for idx, (bname, bnode) in enumerate(branches.items()):
            lc = _line_counts[idx] if idx < len(_line_counts) else 0
            fr = _fact_ratios[idx] if idx < len(_fact_ratios) else 0
            dist = 0.0
            if _med_lines > 0:
                dist += abs(lc - _med_lines) / max(_med_lines, 1)
            if _med_facts > 0:
                dist += abs(fr - _med_facts) / max(_med_facts, 0.01)
            elif fr == 0:
                pass  # zero facts when median is also zero = not anomalous
            if dist > 2.0:
                _i3_anomalies.add(bname)

    hot, cold, dead = [], [], []

    for name, node in branches.items():
        temp = node.get("temperature", 0)
        acc = node.get("access_count", 0)
        recall = _effective_recall[name]  # I2: use suppressed recall
        days_ago = _days_since(node.get("last_access", time.strftime("%Y-%m-%d")))

        # I3: Anomalous branches get demoted to cold regardless of recall
        if name in _i3_anomalies and recall >= 0.15:
            cold.append((name, days_ago))
            print(f"  I3 ANOMALY {name}: R={recall:.2f} demoted to cold (abnormal profile)")
            continue

        # Spaced repetition thresholds (Settles 2016):
        # R > 0.4 = hot (strong recall), R < 0.05 = dead (forgotten)
        # 0.05 <= R < 0.15 = cold (fading, candidate for re-compression)
        if recall >= 0.4:
            hot.append((name, temp))
            print(f"  HOT  {name}: R={recall:.2f} t={temp:.2f} h={7*(2**min(acc,10)):.0f}d acc={acc}")
        elif recall < 0.05:
            # V9B: Protect fragile branches (sole carriers of unique concepts)
            if name in _fragile_branches:
                cold.append((name, days_ago))  # demote to cold instead of dead
                print(f"  V9B  {name}: R={recall:.3f} PROTECTED (sole carrier) -> cold")
            else:
                dead.append((name, days_ago))
                print(f"  DEAD {name}: R={recall:.3f} t={temp:.2f} cold {days_ago}d")
        elif recall < 0.15:
            cold.append((name, days_ago))
            print(f"  COLD {name}: R={recall:.2f} t={temp:.2f} cold {days_ago}d")
        else:
            print(f"  OK   {name}: R={recall:.2f} t={temp:.2f} acc={acc}")

    # B14: Dust branch cleanup — branches with <= 3 lines are noise
    # (minimum viable content = 4+ lines, below that no useful information)
    dust = []
    for name, node in list(branches.items()):
        if name in dict(dead):
            continue  # already dead, will be handled below
        if name in _fragile_branches:
            continue  # V9B: sole carriers protected even if small
        lines = node.get("lines", 0)
        if lines <= 3 and node.get("temperature", 0) < 0.3:
            dust.append(name)
    if dust:
        for name in dust:
            # Move from cold/hot to dead
            dead.append((name, _days_since(nodes[name].get("last_access", time.strftime("%Y-%m-%d")))))
            # Remove from cold list if present
            cold[:] = [(n, d) for n, d in cold if n != name]
        print(f"  B14 DUST: {len(dust)} branches <= 3 lines -> dead ({', '.join(dust[:10])})")

    recompressed = 0
    if not dry_run:
        # Optimal Forgetting: re-compress cold branches with L9
        # Cold branches get deeper compression before potential deletion
        for name, days in cold:
            if name not in nodes:
                continue  # H1 fix: may have been removed by _sleep_consolidate
            node = nodes[name]
            filepath = _m.TREE_DIR / node["file"]
            if not filepath.exists():
                continue
            # A2: skip cold-branch recompression if .mn truncated → no crash
            content = _safe_read_mn(filepath)
            if content is None:
                continue
            original_lines = len(content.split("\n"))
            # Apply L9 (LLM compression) if branch is large enough
            compressed = _m._llm_compress(content, context=f"cold-branch:{name}")
            if compressed != content:
                _atomic_text_write(filepath, compressed)
                new_lines = len(compressed.split("\n"))
                node["lines"] = new_lines
                recompressed += 1
                print(f"  RE-COMPRESSED {name}: {original_lines} -> {new_lines} lines")

        # H10: Snapshot tree before sleep consolidation (for rollback)
        _pre_consolidate_snapshot = json.dumps(tree, indent=2, ensure_ascii=False)

        # Sleep Consolidation (Wilson & McNaughton 1994)
        # Merge similar cold branches into single dense branches
        cold_branch_data = [(name, nodes[name]) for name, _ in cold if name in nodes]
        try:
            consolidated = _sleep_consolidate(cold_branch_data, nodes)
        except Exception as e:
            # H10: Rollback tree to pre-consolidation state
            print(f"  H10 ROLLBACK: consolidation failed ({e}), restoring tree snapshot")
            tree.update(json.loads(_pre_consolidate_snapshot))
            consolidated = 0

        # MYCELIUM DECAY — clean dead connections during prune (like the tree)
        # decay() was never called before, causing unbounded growth (14.9M edges, 1.3GB).
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m_decay = Mycelium(_m._REPO_PATH or Path("."))
            dead_edges = m_decay.decay()
            if dead_edges > 0:
                m_decay.save()
                print(f"  MYCELIUM DECAY: {dead_edges} dead connections removed")
            else:
                print(f"  MYCELIUM DECAY: 0 dead (all connections healthy)")
            m_decay.close()
        except Exception as e:
            print(f"  MYCELIUM DECAY skipped: {e}", file=sys.stderr)

        # H1: Mode trip — psilocybine exploration during sleep
        # Create dream connections between distant clusters (BARE Wave model)
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(_m._REPO_PATH or Path("."))
            trip_result = m.trip(intensity=0.5, max_dreams=15)
            if trip_result["created"] > 0:
                m.save()
                print(f"  H1 TRIP: {trip_result['created']} dream connections "
                      f"(entropy {trip_result['entropy_before']:.2f} -> "
                      f"{trip_result['entropy_after']:.2f})")
            # H2: Dream/synthesis — generate insights during sleep
            dream_insights = m.dream()
            if dream_insights:
                print(f"  H2 DREAM: {len(dream_insights)} insights generated")
                for ins in dream_insights[:3]:
                    print(f"    [{ins['type']}] {ins['text'][:80]}")
            m.close()
        except Exception as e:
            print(f"  H1/H2 skipped: {e}", file=sys.stderr)

        # V9A+: Fact-level regeneration (Shomrat & Levin 2013)
        # Before deleting dead branches, extract tagged facts (D>/B>/F>/E>/A>)
        # from the dying .mn file and inject them into the closest surviving branch.
        # The content survives, not just the tag labels.
        _regen_tag_re = re.compile(r'^[DBFEA]>\s')
        _regen_facts_total = 0
        _regen_tags_total = 0
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m_regen = Mycelium(_m._REPO_PATH or Path("."))
            # H1 fix: compute surviving from CURRENT nodes (after sleep_consolidate)
            dead_set = {n for n, _ in dead}
            surviving = {n for n in nodes if n != "root" and n not in dead_set}
            # Pre-cache survivor tags to avoid repeated set() construction (M3 fix)
            _surv_tags = {s: set(nodes[s].get("tags", [])) for s in surviving}

            for name, days in dead:
                if name not in nodes:
                    continue
                try:
                    dead_node = nodes[name]
                    dead_tags = set(dead_node.get("tags", []))
                    dead_file = dead_node.get("file", "")
                    if not dead_file:
                        continue  # M1 fix: no file key
                    dead_filepath = _m.TREE_DIR / dead_file

                    # --- Step 1: Read .mn file and extract tagged facts ---
                    facts = []
                    if dead_filepath.is_file():
                        try:
                            content = dead_filepath.read_text(encoding="utf-8")
                            for line in content.split("\n"):
                                stripped = line.strip()
                                if _regen_tag_re.match(stripped):
                                    facts.append(stripped)
                        except (OSError, UnicodeDecodeError):
                            pass  # fallback to tag-only diffusion

                    # --- Step 2: Find best surviving branch ---
                    best_survivor = None
                    best_score = -1

                    # Strategy A: mycelium proximity
                    for dtag in list(dead_tags)[:5]:
                        related = m_regen.get_related(dtag, top_n=10)
                        for concept, strength in related:
                            for sname in surviving:
                                if sname not in nodes:
                                    continue  # H2 fix: skip stale refs
                                if concept in _surv_tags.get(sname, set()):
                                    if strength > best_score:
                                        best_score = strength
                                        best_survivor = sname

                    # Strategy B: most tags in common
                    if best_survivor is None and dead_tags:
                        max_overlap = 0
                        for sname in surviving:
                            if sname not in nodes:
                                continue
                            overlap = len(dead_tags & _surv_tags.get(sname, set()))
                            if overlap > max_overlap:
                                max_overlap = overlap
                                best_survivor = sname

                    # Strategy C: most recently accessed surviving branch
                    if best_survivor is None:
                        latest_access = ""
                        for sname in surviving:
                            if sname not in nodes:
                                continue
                            la = nodes[sname].get("last_access", "")
                            if la > latest_access:
                                latest_access = la
                                best_survivor = sname

                    if best_survivor is None:
                        continue  # no survivors at all

                    # --- Step 3: Inject facts into survivor .mn ---
                    if facts:
                        surv_file = nodes[best_survivor].get("file", "")
                        if not surv_file:
                            continue  # M1 fix
                        survivor_filepath = _m.TREE_DIR / surv_file
                        survivor_content = ""
                        if survivor_filepath.is_file():
                            try:
                                survivor_content = survivor_filepath.read_text(encoding="utf-8")
                            except (OSError, UnicodeDecodeError):
                                pass

                        # Dedup: don't inject facts already present in survivor
                        existing_lines = set(l.strip() for l in survivor_content.split("\n"))
                        new_facts = [f for f in facts if f not in existing_lines]

                        if new_facts:
                            # Build REGEN section
                            regen_header = f"## REGEN: {name} ({time.strftime('%Y-%m-%d')})"
                            # Idempotency: if this REGEN header exists, skip
                            if regen_header not in survivor_content:
                                regen_block = "\n" + regen_header + "\n" + "\n".join(new_facts) + "\n"
                                combined = survivor_content.rstrip() + regen_block

                                # Budget check: if > 200 lines, recompress with L10+L11
                                if combined.count("\n") > 200:
                                    combined = _m._cue_distill(combined)
                                    combined = _m._extract_rules(combined)

                                _atomic_text_write(survivor_filepath, combined)
                                _regen_facts_total += len(new_facts)
                                # Update hash + line count so boot() P34 integrity check passes
                                nodes[best_survivor]["hash"] = compute_hash(survivor_filepath)
                                nodes[best_survivor]["lines"] = combined.count("\n") + 1

                    # --- Step 4: Tag diffusion (original V9A logic, always runs) ---
                    if dead_tags:
                        for dtag in list(dead_tags)[:5]:
                            related = m_regen.get_related(dtag, top_n=5)
                            for concept, strength in related:
                                for sname in surviving:
                                    if sname not in nodes:
                                        continue
                                    stags = _surv_tags.get(sname, set())
                                    if concept in stags and dtag not in stags:
                                        nodes[sname].setdefault("tags", []).append(dtag)
                                        _surv_tags[sname].add(dtag)  # update cache
                                        _regen_tags_total += 1
                                        break

                except (KeyError, TypeError, OSError) as e:
                    print(f"  V9A+ regen skipped for {name}: {e}", file=sys.stderr)
                    continue  # M7 fix: per-branch error handling

            if _regen_facts_total > 0 or _regen_tags_total > 0:
                print(f"  V9A+ REGEN: {_regen_facts_total} facts + "
                      f"{_regen_tags_total} tags diffused to survivors")
            m_regen.close()
        except Exception as e:
            import traceback
            print(f"  V9A+ regen failed: {e}", file=sys.stderr)
            traceback.print_exc(file=sys.stderr)

        for name, days in dead:
            if name not in nodes:
                continue  # may have been consolidated already
            node = nodes[name]
            filepath = _m.TREE_DIR / node["file"]
            if filepath.exists():
                try:
                    filepath.unlink()
                except OSError as e:
                    print(f"  WARNING: could not delete {_m._safe_path(filepath)}: {e}", file=sys.stderr)
                    continue  # don't remove node if file still exists
            del nodes[name]
            if name in nodes.get("root", {}).get("children", []):
                nodes["root"]["children"].remove(name)
            print(f"  DELETED {name}")

        save_tree(tree)

    print(f"\n  Summary: {len(hot)} hot, {len(cold)} cold "
          f"({recompressed if not dry_run else '?'} recompressed, "
          f"{len(consolidated) if not dry_run else '?'} consolidated), {len(dead)} dead")

    # H.3 (2026-05-12): Sleep Consolidation pass (Wilson & McNaughton 1994).
    # 561 LOC of mycelium_dream.py were dormant before this wire.
    # NB: do NOT re-import `_m` here — it's imported at module level
    # (line 24). A local re-import would shadow the global for the entire
    # function and trigger UnboundLocalError at line 450 (`_m.TREE_DIR`).
    if include_dreams and not dry_run:
        try:
            from mycelium import Mycelium
            repo = _m._REPO_PATH or Path.cwd()
            myc = Mycelium(repo)
            try:
                insights = myc.dream()
                print(f"\n  Dream pass: {len(insights)} insight(s) "
                      f"generated (see .muninn/insights.json)")
            finally:
                try:
                    myc.save()
                except Exception:
                    pass
                myc.close()
        except Exception as exc:
            # dream() pass is best-effort — never break prune on failure
            print(f"  Dream pass skipped: {type(exc).__name__}: {exc}")
    elif include_dreams and dry_run:
        print("\n  Dream pass requires --force (dry_run blocks DB writes).")
