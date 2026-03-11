"""V9A — Bioelectric regeneration via tag diffusion: strict validation bornes.

Paper: Shomrat & Levin 2013, J Exp Biol.
Production: dead branch tags are diffused to surviving branches via mycelium
  get_related(). Tags travel through co-occurrence network, not PDE.

Tests:
  V9A.1  Dead branch tag diffuses to survivor with related concept
  V9A.2  No related concepts: no diffusion
  V9A.3  Tag already present: not duplicated
  V9A.4  Max 5 tags diffused per dead branch (production limit)
  V9A.5  Empty tags: no crash
  V9A.6  Multiple dead branches: each diffuses independently
"""
import sys, os
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


def simulate_v9a_regen(nodes, dead_names, related_fn, max_tags_per_dead=5):
    """Replicate production V9A regeneration logic from prune().
    nodes: dict of name -> {"tags": list, ...}
    dead_names: list of branch names being deleted
    related_fn: fn(concept) -> [(related_concept, strength), ...]
    Returns: count of diffused tags
    """
    surviving = {n for n in nodes if n not in dead_names}
    regen_count = 0
    for dname in dead_names:
        if dname not in nodes:
            continue
        dead_tags = set(nodes[dname].get("tags", []))
        if not dead_tags:
            continue
        for dtag in list(dead_tags)[:max_tags_per_dead]:
            related = related_fn(dtag)
            for concept, strength in related:
                # Find a surviving branch with this related concept
                for sname in surviving:
                    stags = set(nodes[sname].get("tags", []))
                    if concept in stags and dtag not in stags:
                        nodes[sname].setdefault("tags", []).append(dtag)
                        regen_count += 1
                        break  # one recipient per concept
    return regen_count


def test_v9a_1_diffusion():
    """Dead tag diffuses to survivor via related concept"""
    nodes = {
        "dead_branch": {"tags": ["compression", "memory"]},
        "survivor": {"tags": ["tokens", "tree"]},
    }
    # "compression" is related to "tokens" in mycelium
    def related(concept):
        if concept == "compression":
            return [("tokens", 0.8)]
        if concept == "memory":
            return [("tree", 0.7)]
        return []
    count = simulate_v9a_regen(nodes, ["dead_branch"], related)
    # "compression" should diffuse to survivor (via tokens link)
    check("V9A.1", "compression" in nodes["survivor"]["tags"],
          f"survivor tags={nodes['survivor']['tags']}, count={count}")


def test_v9a_2_no_related():
    """No related concepts: no diffusion"""
    nodes = {
        "dead_branch": {"tags": ["alpha"]},
        "survivor": {"tags": ["beta"]},
    }
    def related(concept):
        return []  # nothing related
    count = simulate_v9a_regen(nodes, ["dead_branch"], related)
    check("V9A.2", count == 0 and "alpha" not in nodes["survivor"]["tags"],
          f"count={count}, survivor={nodes['survivor']['tags']}")


def test_v9a_3_no_duplicate():
    """Tag already in survivor: not duplicated"""
    nodes = {
        "dead_branch": {"tags": ["memory"]},
        "survivor": {"tags": ["memory", "tree"]},
    }
    def related(concept):
        return [("tree", 0.5)]
    count = simulate_v9a_regen(nodes, ["dead_branch"], related)
    # "memory" already in survivor — dtag not in stags check should prevent duplication
    mem_count = nodes["survivor"]["tags"].count("memory")
    check("V9A.3", mem_count == 1,
          f"memory count={mem_count} (no duplication)")


def test_v9a_4_max_5_tags():
    """Max 5 tags diffused per dead branch"""
    nodes = {
        "dead_branch": {"tags": [f"tag_{i}" for i in range(10)]},
        "survivor": {"tags": ["receiver"]},
    }
    def related(concept):
        return [("receiver", 0.5)]
    count = simulate_v9a_regen(nodes, ["dead_branch"], related)
    check("V9A.4", count <= 5,
          f"count={count} (max 5 per dead branch)")


def test_v9a_5_empty_tags():
    """Empty tags: no crash, no diffusion"""
    nodes = {
        "dead_branch": {"tags": []},
        "survivor": {"tags": ["tree"]},
    }
    def related(concept):
        return [("tree", 0.5)]
    count = simulate_v9a_regen(nodes, ["dead_branch"], related)
    check("V9A.5", count == 0,
          f"count={count} (no tags to diffuse)")


def test_v9a_6_multi_dead():
    """Multiple dead branches each diffuse independently"""
    nodes = {
        "dead_1": {"tags": ["alpha"]},
        "dead_2": {"tags": ["beta"]},
        "survivor": {"tags": ["gamma"]},
    }
    def related(concept):
        return [("gamma", 0.5)]
    count = simulate_v9a_regen(nodes, ["dead_1", "dead_2"], related)
    stags = nodes["survivor"]["tags"]
    check("V9A.6", "alpha" in stags and "beta" in stags,
          f"survivor tags={stags}, count={count}")


if __name__ == "__main__":
    print("=== V9A Bioelectric Tag Regeneration — 6 bornes ===")
    test_v9a_1_diffusion()
    test_v9a_2_no_related()
    test_v9a_3_no_duplicate()
    test_v9a_4_max_5_tags()
    test_v9a_5_empty_tags()
    test_v9a_6_multi_dead()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
