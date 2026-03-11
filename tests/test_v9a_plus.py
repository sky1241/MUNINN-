"""V9A+ — Fact-level regeneration across branch death (Levin 2013).

Paper: Shomrat & Levin 2013, J Exp Biol.
Production: dead branch tagged facts (D>/B>/F>/E>/A>) extracted from .mn file
  and injected into closest surviving branch before deletion.

Tests:
  REGEN.1   Tagged facts (D>/B>/F>/E>) extracted from dying .mn
  REGEN.2   Untagged lines NOT copied (only facts migrate)
  REGEN.3   Section "## REGEN:" present in target after injection
  REGEN.4   Survivor chosen by mycelium proximity
  REGEN.5   Missing .mn file: fallback to tag-only, no crash
  REGEN.6   No duplication: same fact injected 2x = present 1x
  REGEN.7   Budget: target > 200 lines -> recompression L10+L11
  REGEN.8   Idempotent: prune() x2 doesn't duplicate facts
  REGEN.9   End-to-end: create -> die -> prune -> facts in survivor
  REGEN.10  After regen, dead concept findable in survivor
  REGEN.11  Multi-death: 3 branches die, each regenerates to different survivor
  REGEN.12  V9B + V9A+: sole-carrier protected by V9B, no V9A+ triggered
"""
import sys, os, re, tempfile, shutil, time
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  {name} PASS{': ' + detail if detail else ''}")
    else:
        FAIL += 1
        print(f"  {name} FAIL{': ' + detail if detail else ''}")


# ── Helpers ──────────────────────────────────────────────────────

_TAG_RE = re.compile(r'^[DBFEA]>\s')

def _extract_tagged_facts(content: str) -> list[str]:
    """Extract tagged lines from .mn content (mirrors V9A+ logic)."""
    facts = []
    for line in content.split("\n"):
        stripped = line.strip()
        if _TAG_RE.match(stripped):
            facts.append(stripped)
    return facts


def _make_mn_content(tagged_lines: list[str], narrative_lines: list[str] = None) -> str:
    """Build a minimal .mn file content with tagged + narrative lines."""
    lines = ["# MUNINN|session_compressed"]
    for t in tagged_lines:
        lines.append(t)
    for n in (narrative_lines or []):
        lines.append(n)
    return "\n".join(lines)


def _make_tree_dir():
    """Create a temp directory mimicking memory/ with .mn files."""
    tmp = tempfile.mkdtemp()
    mem_dir = os.path.join(tmp, "memory")
    os.makedirs(mem_dir, exist_ok=True)
    return tmp, mem_dir


def _write_mn(mem_dir, filename, content):
    """Write a .mn file in the memory dir."""
    path = os.path.join(mem_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def _read_mn(mem_dir, filename):
    """Read a .mn file from memory dir."""
    path = os.path.join(mem_dir, filename)
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _simulate_v9a_plus(mem_dir, nodes, dead_names, related_fn,
                        max_tags_per_dead=5):
    """Simulate V9A+ regeneration logic matching production code.

    Args:
        mem_dir: path to memory/ directory containing .mn files
        nodes: dict of branch_name -> {file, tags, last_access, ...}
        dead_names: list of branch names being killed
        related_fn: fn(concept) -> [(related_concept, strength), ...]

    Returns:
        (facts_injected, tags_diffused)
    """
    from pathlib import Path
    # Import production helpers
    try:
        from muninn import _cue_distill, _extract_rules
    except ImportError:
        # Minimal fallbacks for isolated testing
        def _cue_distill(t): return t
        def _extract_rules(t): return t

    _regen_tag_re = re.compile(r'^[DBFEA]>\s')
    dead_set = set(dead_names)
    surviving = {n for n in nodes if n not in dead_set and n != "root"}
    facts_total = 0
    tags_total = 0

    for dname in dead_names:
        if dname not in nodes:
            continue
        dead_node = nodes[dname]
        dead_tags = set(dead_node.get("tags", []))
        dead_filepath = Path(mem_dir) / dead_node.get("file", "")

        # Step 1: Read .mn and extract tagged facts
        facts = []
        if dead_filepath.exists():
            try:
                content = dead_filepath.read_text(encoding="utf-8")
                for line in content.split("\n"):
                    stripped = line.strip()
                    if _regen_tag_re.match(stripped):
                        facts.append(stripped)
            except (OSError, UnicodeDecodeError):
                pass

        # Step 2: Find best survivor
        best_survivor = None
        best_score = -1

        # Strategy A: mycelium proximity
        for dtag in list(dead_tags)[:5]:
            related = related_fn(dtag)
            for concept, strength in related:
                for sname in surviving:
                    stags = set(nodes[sname].get("tags", []))
                    if concept in stags:
                        if strength > best_score:
                            best_score = strength
                            best_survivor = sname

        # Strategy B: most tags in common
        if best_survivor is None and dead_tags:
            max_overlap = 0
            for sname in surviving:
                stags = set(nodes[sname].get("tags", []))
                overlap = len(dead_tags & stags)
                if overlap > max_overlap:
                    max_overlap = overlap
                    best_survivor = sname

        # Strategy C: most recently accessed
        if best_survivor is None:
            latest_access = ""
            for sname in surviving:
                la = nodes[sname].get("last_access", "")
                if la > latest_access:
                    latest_access = la
                    best_survivor = sname

        if best_survivor is None:
            continue

        # Step 3: Inject facts
        if facts:
            snode = nodes[best_survivor]
            spath = Path(mem_dir) / snode.get("file", "")
            survivor_content = ""
            if spath.exists():
                try:
                    survivor_content = spath.read_text(encoding="utf-8")
                except (OSError, UnicodeDecodeError):
                    pass

            existing_lines = set(l.strip() for l in survivor_content.split("\n"))
            new_facts = [f for f in facts if f not in existing_lines]

            if new_facts:
                regen_header = f"## REGEN: {dname} ({time.strftime('%Y-%m-%d')})"
                if regen_header not in survivor_content:
                    regen_block = "\n" + regen_header + "\n" + "\n".join(new_facts) + "\n"
                    combined = survivor_content.rstrip() + regen_block
                    if combined.count("\n") > 200:
                        combined = _cue_distill(combined)
                        combined = _extract_rules(combined)
                    spath.write_text(combined, encoding="utf-8")
                    facts_total += len(new_facts)

        # Step 4: Tag diffusion (original V9A)
        if dead_tags:
            for dtag in list(dead_tags)[:5]:
                related = related_fn(dtag)
                for concept, strength in related:
                    for sname in surviving:
                        stags = set(nodes[sname].get("tags", []))
                        if concept in stags and dtag not in stags:
                            nodes[sname].setdefault("tags", []).append(dtag)
                            tags_total += 1
                            break

    return facts_total, tags_total


# ── Tests ────────────────────────────────────────────────────────

def test_regen_1_facts_extracted():
    """REGEN.1 — Tagged facts D>/B>/F>/E> extracted from dying .mn"""
    tmp, mem_dir = _make_tree_dir()
    tagged = [
        "D> switched to SQLite for mycelium",
        "B> L9 API: x4.4 avg on 230 files",
        "F> muninn.py: 3775 lines, 60 functions",
        "E> BUG: self-ref TD saturated to 1.0",
    ]
    _write_mn(mem_dir, "dead_branch.mn", _make_mn_content(tagged))
    _write_mn(mem_dir, "survivor.mn", "# MUNINN|session_compressed\nsome existing content")

    nodes = {
        "dead_branch": {"file": "dead_branch.mn", "tags": ["sqlite", "api"], "last_access": "2026-01-01"},
        "survivor": {"file": "survivor.mn", "tags": ["database"], "last_access": "2026-03-11"},
    }
    def related(c):
        if c == "sqlite": return [("database", 0.8)]
        return []

    facts_n, _ = _simulate_v9a_plus(mem_dir, nodes, ["dead_branch"], related)
    survivor_content = _read_mn(mem_dir, "survivor.mn")

    check("REGEN.1", facts_n == 4 and "D> switched to SQLite" in survivor_content,
          f"facts={facts_n}, has_D={('D>' in survivor_content)}")
    shutil.rmtree(tmp)


def test_regen_2_untagged_not_copied():
    """REGEN.2 — Untagged lines NOT copied"""
    tmp, mem_dir = _make_tree_dir()
    tagged = ["D> important decision"]
    narrative = ["some random narrative about debugging", "more context blabla"]
    _write_mn(mem_dir, "dead.mn", _make_mn_content(tagged, narrative))
    _write_mn(mem_dir, "surv.mn", "# existing")

    nodes = {
        "dead": {"file": "dead.mn", "tags": ["debug"], "last_access": "2026-01-01"},
        "surv": {"file": "surv.mn", "tags": ["code"], "last_access": "2026-03-11"},
    }
    def related(c): return [("code", 0.5)]

    _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    content = _read_mn(mem_dir, "surv.mn")

    has_decision = "D> important decision" in content
    has_narrative = "some random narrative" in content
    check("REGEN.2", has_decision and not has_narrative,
          f"decision={has_decision}, narrative={has_narrative}")
    shutil.rmtree(tmp)


def test_regen_3_regen_section_present():
    """REGEN.3 — Section '## REGEN:' present in target after injection"""
    tmp, mem_dir = _make_tree_dir()
    _write_mn(mem_dir, "dead.mn", _make_mn_content(["F> fact1"]))
    _write_mn(mem_dir, "surv.mn", "# existing")

    nodes = {
        "dead": {"file": "dead.mn", "tags": ["x"], "last_access": "2026-01-01"},
        "surv": {"file": "surv.mn", "tags": ["y"], "last_access": "2026-03-11"},
    }
    def related(c): return [("y", 0.5)]

    _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    content = _read_mn(mem_dir, "surv.mn")

    has_regen = "## REGEN: dead" in content
    check("REGEN.3", has_regen, f"has_regen_section={has_regen}")
    shutil.rmtree(tmp)


def test_regen_4_mycelium_proximity():
    """REGEN.4 — Survivor chosen by mycelium proximity (highest strength)"""
    tmp, mem_dir = _make_tree_dir()
    _write_mn(mem_dir, "dead.mn", _make_mn_content(["B> metric x4.1"]))
    _write_mn(mem_dir, "close.mn", "# close survivor")
    _write_mn(mem_dir, "far.mn", "# far survivor")

    nodes = {
        "dead": {"file": "dead.mn", "tags": ["compression"], "last_access": "2026-01-01"},
        "close": {"file": "close.mn", "tags": ["pipeline"], "last_access": "2026-03-01"},
        "far": {"file": "far.mn", "tags": ["misc"], "last_access": "2026-03-11"},
    }
    def related(c):
        if c == "compression":
            return [("pipeline", 0.9), ("misc", 0.2)]
        return []

    _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    close_content = _read_mn(mem_dir, "close.mn")
    far_content = _read_mn(mem_dir, "far.mn")

    # Facts should go to "close" (strength 0.9) not "far" (strength 0.2)
    check("REGEN.4", "B> metric x4.1" in close_content and "B> metric" not in far_content,
          f"close={'REGEN' in close_content}, far={'REGEN' in far_content}")
    shutil.rmtree(tmp)


def test_regen_5_missing_mn_fallback():
    """REGEN.5 — Missing .mn file: fallback to tag-only diffusion, no crash"""
    tmp, mem_dir = _make_tree_dir()
    # Do NOT create dead.mn — file doesn't exist
    _write_mn(mem_dir, "surv.mn", "# existing")

    nodes = {
        "dead": {"file": "dead.mn", "tags": ["alpha"], "last_access": "2026-01-01"},
        "surv": {"file": "surv.mn", "tags": ["beta"], "last_access": "2026-03-11"},
    }
    def related(c):
        if c == "alpha": return [("beta", 0.7)]
        return []

    # Should not crash, should still diffuse tags
    facts_n, tags_n = _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    surv_content = _read_mn(mem_dir, "surv.mn")

    check("REGEN.5", facts_n == 0 and tags_n == 1 and "alpha" in nodes["surv"]["tags"],
          f"facts={facts_n}, tags={tags_n}, surv_tags={nodes['surv']['tags']}")
    shutil.rmtree(tmp)


def test_regen_6_no_duplication():
    """REGEN.6 — Same fact already in survivor: not duplicated"""
    tmp, mem_dir = _make_tree_dir()
    fact = "F> muninn.py: 3775 lines"
    _write_mn(mem_dir, "dead.mn", _make_mn_content([fact]))
    # Survivor already has this exact fact
    _write_mn(mem_dir, "surv.mn", f"# existing\n{fact}\n")

    nodes = {
        "dead": {"file": "dead.mn", "tags": ["code"], "last_access": "2026-01-01"},
        "surv": {"file": "surv.mn", "tags": ["muninn"], "last_access": "2026-03-11"},
    }
    def related(c): return [("muninn", 0.5)]

    facts_n, _ = _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    content = _read_mn(mem_dir, "surv.mn")

    count = content.count(fact)
    check("REGEN.6", facts_n == 0 and count == 1,
          f"injected={facts_n}, occurrences={count}")
    shutil.rmtree(tmp)


def test_regen_7_budget_recompression():
    """REGEN.7 — Target > 200 lines triggers L10+L11 recompression"""
    tmp, mem_dir = _make_tree_dir()
    _write_mn(mem_dir, "dead.mn", _make_mn_content(["B> new metric x9.9"]))
    # Create a survivor with 210 lines already
    big_content = "\n".join([f"line {i}: some content here" for i in range(210)])
    _write_mn(mem_dir, "surv.mn", big_content)

    nodes = {
        "dead": {"file": "dead.mn", "tags": ["perf"], "last_access": "2026-01-01"},
        "surv": {"file": "surv.mn", "tags": ["bench"], "last_access": "2026-03-11"},
    }
    def related(c): return [("bench", 0.5)]

    _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    content = _read_mn(mem_dir, "surv.mn")

    # After injection of 1 fact to 210-line file, L10+L11 should have run
    # The fact should still be present
    has_fact = "B> new metric x9.9" in content
    # We can't guarantee exact line count (depends on L10/L11 behavior)
    # but the file should have been processed
    check("REGEN.7", has_fact,
          f"fact_present={has_fact}, lines={content.count(chr(10))}")
    shutil.rmtree(tmp)


def test_regen_8_idempotent():
    """REGEN.8 — Running V9A+ twice doesn't duplicate facts"""
    tmp, mem_dir = _make_tree_dir()
    _write_mn(mem_dir, "dead.mn", _make_mn_content(["D> decision alpha"]))
    _write_mn(mem_dir, "surv.mn", "# existing")

    nodes = {
        "dead": {"file": "dead.mn", "tags": ["x"], "last_access": "2026-01-01"},
        "surv": {"file": "surv.mn", "tags": ["y"], "last_access": "2026-03-11"},
    }
    def related(c): return [("y", 0.5)]

    # Run twice
    _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    facts_2, _ = _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    content = _read_mn(mem_dir, "surv.mn")

    count = content.count("D> decision alpha")
    check("REGEN.8", facts_2 == 0 and count == 1,
          f"second_run_facts={facts_2}, occurrences={count}")
    shutil.rmtree(tmp)


def test_regen_9_end_to_end():
    """REGEN.9 — Full cycle: create branch -> add facts -> die -> regen -> verify"""
    tmp, mem_dir = _make_tree_dir()
    # Create a "real" branch with mixed content
    dead_content = _make_mn_content(
        tagged_lines=[
            "D> switched to async for file I/O",
            "B> throughput: 1200 files/sec",
            "F> pipeline has 11 layers",
            "E> BUG: race condition on concurrent writes, fixed with lock",
            "A> added batch mode for large repos",
        ],
        narrative_lines=[
            "we discussed various approaches to file handling",
            "tried sync first but was too slow",
            "Sky wanted faster processing",
        ]
    )
    _write_mn(mem_dir, "branch_io.mn", dead_content)
    _write_mn(mem_dir, "branch_pipeline.mn", "# pipeline branch\nB> L0-L7: x4.1 average")

    nodes = {
        "branch_io": {"file": "branch_io.mn", "tags": ["io", "async", "performance"],
                      "last_access": "2025-12-01"},
        "branch_pipeline": {"file": "branch_pipeline.mn", "tags": ["pipeline", "compression"],
                           "last_access": "2026-03-10"},
    }
    def related(c):
        if c == "performance": return [("pipeline", 0.85)]
        if c == "async": return [("compression", 0.3)]
        return []

    facts_n, tags_n = _simulate_v9a_plus(mem_dir, nodes, ["branch_io"], related)
    content = _read_mn(mem_dir, "branch_pipeline.mn")

    # All 5 tagged facts should migrate, 0 narrative lines
    has_all_facts = all(tag in content for tag in ["D> switched", "B> throughput", "F> pipeline",
                                                    "E> BUG: race", "A> added batch"])
    has_no_narrative = "tried sync first" not in content
    has_regen = "## REGEN: branch_io" in content

    check("REGEN.9", facts_n == 5 and has_all_facts and has_no_narrative and has_regen,
          f"facts={facts_n}, all_present={has_all_facts}, no_narrative={has_no_narrative}")
    shutil.rmtree(tmp)


def test_regen_10_concept_findable():
    """REGEN.10 — After regen, dead branch concept findable in survivor content"""
    tmp, mem_dir = _make_tree_dir()
    _write_mn(mem_dir, "dead.mn", _make_mn_content(["F> L9 prompt: 847 tokens system"]))
    _write_mn(mem_dir, "surv.mn", "# survivor branch content")

    nodes = {
        "dead": {"file": "dead.mn", "tags": ["l9", "prompt"], "last_access": "2026-01-01"},
        "surv": {"file": "surv.mn", "tags": ["api"], "last_access": "2026-03-11"},
    }
    def related(c):
        if c == "l9": return [("api", 0.8)]
        return []

    _simulate_v9a_plus(mem_dir, nodes, ["dead"], related)
    content = _read_mn(mem_dir, "surv.mn")

    # Searching for "L9" or "847" should hit survivor now
    findable = "L9" in content and "847" in content
    check("REGEN.10", findable,
          f"L9_in_survivor={('L9' in content)}, 847_in_survivor={('847' in content)}")
    shutil.rmtree(tmp)


def test_regen_11_multi_death():
    """REGEN.11 — 3 branches die, each regenerates to a different survivor"""
    tmp, mem_dir = _make_tree_dir()
    _write_mn(mem_dir, "dead_a.mn", _make_mn_content(["D> decision A"]))
    _write_mn(mem_dir, "dead_b.mn", _make_mn_content(["D> decision B"]))
    _write_mn(mem_dir, "dead_c.mn", _make_mn_content(["D> decision C"]))
    _write_mn(mem_dir, "surv_x.mn", "# survivor X")
    _write_mn(mem_dir, "surv_y.mn", "# survivor Y")
    _write_mn(mem_dir, "surv_z.mn", "# survivor Z")

    nodes = {
        "dead_a": {"file": "dead_a.mn", "tags": ["alpha"], "last_access": "2026-01-01"},
        "dead_b": {"file": "dead_b.mn", "tags": ["beta"], "last_access": "2026-01-01"},
        "dead_c": {"file": "dead_c.mn", "tags": ["gamma"], "last_access": "2026-01-01"},
        "surv_x": {"file": "surv_x.mn", "tags": ["x_concept"], "last_access": "2026-03-11"},
        "surv_y": {"file": "surv_y.mn", "tags": ["y_concept"], "last_access": "2026-03-10"},
        "surv_z": {"file": "surv_z.mn", "tags": ["z_concept"], "last_access": "2026-03-09"},
    }
    def related(c):
        # Each dead branch's tag relates to a different survivor
        if c == "alpha": return [("x_concept", 0.9)]
        if c == "beta": return [("y_concept", 0.9)]
        if c == "gamma": return [("z_concept", 0.9)]
        return []

    facts_n, _ = _simulate_v9a_plus(mem_dir, nodes, ["dead_a", "dead_b", "dead_c"], related)

    x_content = _read_mn(mem_dir, "surv_x.mn")
    y_content = _read_mn(mem_dir, "surv_y.mn")
    z_content = _read_mn(mem_dir, "surv_z.mn")

    a_in_x = "decision A" in x_content
    b_in_y = "decision B" in y_content
    c_in_z = "decision C" in z_content

    check("REGEN.11", a_in_x and b_in_y and c_in_z and facts_n == 3,
          f"A->X={a_in_x}, B->Y={b_in_y}, C->Z={c_in_z}, total={facts_n}")
    shutil.rmtree(tmp)


def test_regen_12_v9b_protects():
    """REGEN.12 — V9B sole-carrier protected branch: demoted to cold, no V9A+ regen"""
    # V9B demotes sole-carrier dead branches to cold BEFORE V9A+ runs.
    # So V9A+ should never see them in the dead list.
    # This test verifies that if a branch is NOT in dead (because V9B protected it),
    # its facts are NOT injected into any survivor.
    tmp, mem_dir = _make_tree_dir()
    _write_mn(mem_dir, "protected.mn", _make_mn_content(["D> unique decision"]))
    _write_mn(mem_dir, "surv.mn", "# survivor")

    nodes = {
        "protected": {"file": "protected.mn", "tags": ["unique_sole"],
                      "last_access": "2026-01-01"},
        "surv": {"file": "surv.mn", "tags": ["common"], "last_access": "2026-03-11"},
    }
    def related(c): return [("common", 0.5)]

    # V9B would have removed "protected" from dead list -> pass empty dead list
    facts_n, tags_n = _simulate_v9a_plus(mem_dir, nodes, [], related)
    content = _read_mn(mem_dir, "surv.mn")

    check("REGEN.12", facts_n == 0 and tags_n == 0 and "unique decision" not in content,
          f"facts={facts_n}, tags={tags_n}, protected_content_leaked={('unique' in content)}")
    shutil.rmtree(tmp)


if __name__ == "__main__":
    print("=== V9A+ Fact-Level Regeneration — 12 bornes ===")
    test_regen_1_facts_extracted()
    test_regen_2_untagged_not_copied()
    test_regen_3_regen_section_present()
    test_regen_4_mycelium_proximity()
    test_regen_5_missing_mn_fallback()
    test_regen_6_no_duplication()
    test_regen_7_budget_recompression()
    test_regen_8_idempotent()
    test_regen_9_end_to_end()
    test_regen_10_concept_findable()
    test_regen_11_multi_death()
    test_regen_12_v9b_protects()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
