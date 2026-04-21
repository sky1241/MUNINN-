"""Simulate: with all 5 fixes, how many gaps remain per cube?"""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

from engine.core.cube import subdivide_file, extract_ast_hints, normalize_content, enrich_hints_with_file_context

f = os.path.join(os.path.dirname(__file__), "cube_corpus", "server.go")
with open(f, "r") as fh:
    content = fh.read()
cubes = subdivide_file(content=content, file_path=f, target_tokens=112)

already_sha = {2,4,5,9,10,12,14,15,16,18,19,21,23,25,27,28,34,35,36,37,
               40,41,42,46,47,49,50,53,55,56,64,66,69,71,73,75,79}
failed = sorted(set(range(len(cubes))) - already_sha)

print("=== SIMULATION: gaps after ALL fixes ===\n")

cat0 = []
cat12 = []
cat35 = []
cat6p = []

for ci in failed:
    tc = cubes[ci]
    orig = normalize_content(tc.content)
    ol = orig.split("\n")
    n = len(ol)
    hints = extract_ast_hints(tc)
    hints["_raw_content"] = tc.content
    hints = enrich_hints_with_file_context(hints, content)

    # Build anchor map
    anchor_map = {}
    if hints.get("first_line"): anchor_map[0] = hints["first_line"]
    if hints.get("last_line"): anchor_map[n-1] = hints["last_line"]
    if hints.get("anchors"):
        for ln, lt in hints["anchors"]:
            idx = ln - 1
            if 0 <= idx < n: anchor_map[idx] = lt

    # Constant forcing
    for const_line in hints.get("constant_lines", []):
        cs = const_line.strip()
        vm = re.match(r"\s*(\w+)\s*=", cs)
        if vm:
            vn = vm.group(1)
            for idx in range(n):
                if idx not in anchor_map and vn in ol[idx]:
                    anchor_map[idx] = const_line

    # Struct field forcing
    for idx in range(n):
        if idx not in anchor_map:
            line = ol[idx]
            if "`" in line and ("json:" in line or "xml:" in line or "yaml:" in line):
                anchor_map[idx] = line

    gaps = [i for i in range(n) if i not in anchor_map]
    ng = len(gaps)

    if ng == 0: cat0.append(ci)
    elif ng <= 2: cat12.append(ci)
    elif ng <= 5: cat35.append(ci)
    else: cat6p.append(ci)

    prob = f"{100*(0.9**ng):.0f}%" if ng > 0 else "100%"
    gap_lines = ", ".join(f"L{g+1}" for g in gaps[:5])
    if len(gaps) > 5: gap_lines += f"... +{len(gaps)-5}"
    print(f"  cube {ci:>2}: {n} lines, {len(anchor_map)} anchors, {ng} gaps, P~{prob} [{gap_lines}]")

print(f"\n=== RESUME ===")
print(f"  0 gaps (SHA auto):     {len(cat0)} — {cat0}")
print(f"  1-2 gaps (SHA ~81%+):  {len(cat12)} — {cat12}")
print(f"  3-5 gaps (SHA ~59%+):  {len(cat35)} — {cat35}")
print(f"  6+ gaps (SHA <53%):    {len(cat6p)} — {cat6p}")

easy = len(cat0) + len(cat12)
med = len(cat35)
print(f"\nPrediction: 37 + ~{easy} easy + ~{med//2} medium = ~{37+easy+med//2}/80 ({100*(37+easy+med//2)//80}%)")
