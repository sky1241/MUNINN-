"""Audit all 43 failed cubes — categorize why they fail."""
import sys, os, re
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))

from engine.core.cube import subdivide_file, extract_ast_hints, normalize_content

f = os.path.join(os.path.dirname(__file__), "cube_corpus", "server.go")
with open(f, "r") as fh:
    content = fh.read()
cubes = subdivide_file(content=content, file_path=f, target_tokens=112)

already_sha = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,21,24,28,29,30,
               33,35,36,37,39,40,43,46,49,50,51,53,55,62,63,64,67,71,72,75,78,79}
failed = sorted(set(range(len(cubes))) - already_sha)

print(f"=== 43 CUBES SANS SHA — AUDIT ===\n")

cats = {"IMPORTS": [], "CONSTANTS": [], "STRUCT_FIELDS": [],
        "LOGIC_SIMPLE": [], "LOGIC_COMPLEX": [], "STRING_LITERALS": []}

for ci in failed:
    tc = cubes[ci]
    orig = normalize_content(tc.content)
    ol = orig.split("\n")
    hints = extract_ast_hints(tc)

    anchor_map = {}
    if hints.get("first_line"): anchor_map[0] = hints["first_line"]
    if hints.get("last_line"): anchor_map[len(ol)-1] = hints["last_line"]
    for ln, lt in hints.get("anchors", []):
        idx = ln - 1
        if 0 <= idx < len(ol): anchor_map[idx] = lt

    gaps = [(i, ol[i]) for i in range(len(ol)) if i not in anchor_map]
    n_gaps = len(gaps)
    gap_text = " ".join(l for _, l in gaps)

    has_import = any("import" in l or "include" in l for _, l in gaps)
    has_const_num = bool(re.search(r"=\s*\d+\s*[*<]", gap_text))
    has_json_tag = "json:" in gap_text
    has_long_string = bool(re.search(r'"[^"]{10,}"', gap_text))

    if has_import:
        cat = "IMPORTS"
    elif has_const_num:
        cat = "CONSTANTS"
    elif has_json_tag:
        cat = "STRUCT_FIELDS"
    elif has_long_string:
        cat = "STRING_LITERALS"
    elif n_gaps <= 5:
        cat = "LOGIC_SIMPLE"
    else:
        cat = "LOGIC_COMPLEX"

    cats[cat].append(ci)

    # Show gap lines
    print(f"cube {ci:>2} [{cat:>15}] {n_gaps} gaps:")
    for idx, line in gaps[:4]:
        print(f"    L{idx+1}: {line[:55]}")
    if len(gaps) > 4:
        print(f"    ... +{len(gaps)-4} more")
    print()

print("=== RESUME ===")
for cat, lst in sorted(cats.items(), key=lambda x: -len(x[1])):
    if lst:
        print(f"  {cat:>15}: {len(lst)} cubes — {lst}")

impossible = len(cats["IMPORTS"]) + len(cats["CONSTANTS"])
hard = len(cats["LOGIC_COMPLEX"]) + len(cats["STRING_LITERALS"])
possible = len(cats["LOGIC_SIMPLE"]) + len(cats["STRUCT_FIELDS"])
print(f"\nIRRECONSTRUCTIBLE (imports/constantes): {impossible}/43")
print(f"DIFFICILE (logique complexe/strings):   {hard}/43")
print(f"POSSIBLE (logique simple/structs):       {possible}/43")
