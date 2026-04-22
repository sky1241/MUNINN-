"""Audit complet des 33 cubes failed — analyse pourquoi chaque cube echoue."""
import sys, os, re
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from engine.core.cube import subdivide_file, extract_ast_hints, normalize_content, enrich_hints_with_file_context

f = os.path.join(os.path.dirname(__file__), "cube_corpus", "server.go")
with open(f, "r", encoding="utf-8") as fh:
    content = fh.read()
cubes = subdivide_file(content=content, file_path=f, target_tokens=112)

# 47 SHA confirmed from transcript parsing
sha_set = {0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,21,24,28,29,30,
           33,35,36,37,39,40,43,46,49,50,51,53,55,62,63,64,67,71,72,75,78,79}
failed = sorted(set(range(len(cubes))) - sha_set)


def build_anchor_map(tc, hints, ol, n):
    anchor_map = {}
    if hints.get("first_line"):
        anchor_map[0] = hints["first_line"]
    if hints.get("last_line"):
        anchor_map[n - 1] = hints["last_line"]
    if hints.get("anchors"):
        for ln, lt in hints["anchors"]:
            idx = ln - 1
            if 0 <= idx < n:
                anchor_map[idx] = lt
    # Constant forcing
    for const_line in hints.get("constant_lines", []):
        cs_norm = re.sub(r"\s+", " ", const_line.strip())
        for idx in range(n):
            if idx not in anchor_map:
                line_norm = re.sub(r"\s+", " ", ol[idx].strip())
                if cs_norm and cs_norm == line_norm:
                    anchor_map[idx] = ol[idx]
    # Struct field forcing
    for idx in range(n):
        if idx not in anchor_map:
            line = ol[idx]
            if "`" in line and ("json:" in line or "xml:" in line or "yaml:" in line):
                anchor_map[idx] = line
    return anchor_map


def categorize_line(stripped):
    if not stripped:
        return "BLANK_LINE"
    if stripped in ("}", "};", "){", "})", "})"):
        return "CLOSING_BRACE"
    if stripped.startswith("//") or stripped.startswith("/*") or stripped.startswith("*"):
        return "COMMENT"
    if stripped.startswith("return ") or stripped == "return":
        return "RETURN"
    if "if " in stripped or "else " in stripped or stripped == "} else {" or stripped == "else {":
        return "CONTROL_FLOW"
    if "for " in stripped or "range " in stripped:
        return "LOOP"
    if stripped.startswith("case ") or stripped.startswith("default:"):
        return "SWITCH_CASE"
    if ":=" in stripped or stripped.startswith("var "):
        return "VAR_DECL"
    if "fmt." in stripped or "log." in stripped:
        return "LOG_PRINT"
    if ".Lock()" in stripped or ".Unlock()" in stripped or stripped.startswith("defer "):
        return "SYNC_DEFER"
    if "!= nil" in stripped or "== nil" in stripped:
        return "NIL_CHECK"
    if stripped.endswith("{"):
        return "BLOCK_OPEN"
    if "func " in stripped:
        return "FUNC_DECL"
    if "=" in stripped and ":=" not in stripped:
        return "ASSIGNMENT"
    if "." in stripped and "(" in stripped:
        return "METHOD_CALL"
    return "LOGIC"


def diagnose_root(gap_categories, n_gaps):
    cat_counts = {}
    for _, _, cat in gap_categories:
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    gap_text = " ".join(l for _, l, _ in gap_categories)
    has_string = bool(re.search(r'"[^"]{5,}"', gap_text))

    if n_gaps == 0:
        return "ALL ANCHORED"
    if all(c == "BLANK_LINE" for _, _, c in gap_categories):
        return "BLANK LINES ONLY — gofmt devrait fixer"
    if cat_counts.get("BLANK_LINE", 0) >= n_gaps * 0.5:
        return "MAJORITE BLANKS — placement de lignes vides"
    if cat_counts.get("CLOSING_BRACE", 0) + cat_counts.get("BLOCK_OPEN", 0) >= n_gaps * 0.4:
        return "STRUCTURE — modele se trompe sur les accolades"
    if cat_counts.get("VAR_DECL", 0) + cat_counts.get("ASSIGNMENT", 0) >= n_gaps * 0.4:
        return "VARIABLES — modele invente mauvais noms"
    if cat_counts.get("METHOD_CALL", 0) >= n_gaps * 0.3:
        return "METHODES — modele hallucine des appels"
    if cat_counts.get("CONTROL_FLOW", 0) + cat_counts.get("NIL_CHECK", 0) >= n_gaps * 0.3:
        return "CONTROL FLOW — if/else/err non deductible"
    if cat_counts.get("COMMENT", 0) >= n_gaps * 0.3:
        return "COMMENTAIRES — texte libre non deductible"
    if cat_counts.get("RETURN", 0) >= n_gaps * 0.2:
        return "RETURN — modele se trompe sur la valeur de retour"
    if cat_counts.get("SYNC_DEFER", 0) >= n_gaps * 0.2:
        return "SYNC/DEFER — pattern mutex/defer"
    if cat_counts.get("LOG_PRINT", 0) >= n_gaps * 0.2:
        return "LOG — messages string non deductibles"
    if has_string:
        return "STRING LITERALS — texte libre dans les gaps"
    return "LOGIQUE MIXTE — types de gaps divers"


print(f"=== AUDIT COMPLET — {len(failed)} CUBES FAILED ===\n")

all_roots = {}
all_gap_cats = {}
total_gaps_global = 0

for ci in failed:
    tc = cubes[ci]
    orig = normalize_content(tc.content)
    ol = orig.split("\n")
    n = len(ol)
    hints = extract_ast_hints(tc)
    hints["_raw_content"] = tc.content
    hints = enrich_hints_with_file_context(hints, content)
    anchor_map = build_anchor_map(tc, hints, ol, n)

    gaps = [(i, ol[i]) for i in range(n) if i not in anchor_map]
    n_gaps = len(gaps)
    total_gaps_global += n_gaps

    gap_categories = [(idx, line, categorize_line(line.strip())) for idx, line in gaps]
    for _, _, cat in gap_categories:
        all_gap_cats[cat] = all_gap_cats.get(cat, 0) + 1

    root = diagnose_root(gap_categories, n_gaps)
    all_roots[root] = all_roots.get(root, 0) + 1

    cat_counts = {}
    for _, _, cat in gap_categories:
        cat_counts[cat] = cat_counts.get(cat, 0) + 1
    top_cats = sorted(cat_counts.items(), key=lambda x: -x[1])
    top_str = ", ".join(f"{c}:{nn}" for c, nn in top_cats[:3])

    print(f"{'=' * 70}")
    print(f"CUBE {ci:>2} | {n} lines | {len(anchor_map)} anchors | {n_gaps} gaps")
    print(f"  ROOT CAUSE: {root}")
    print(f"  Categories: {top_str}")
    h_ids = hints.get("identifiers", [])
    h_str = hints.get("strings", [])
    h_fun = hints.get("functions", [])
    h_con = hints.get("constant_lines", [])
    h_imp = hints.get("deduced_imports", [])
    print(f"  Hints: idents={len(h_ids)}, strings={len(h_str)}, "
          f"funcs={len(h_fun)}, consts={len(h_con)}, imports={len(h_imp)}")

    # Show what identifiers ARE available
    if h_ids:
        print(f"  Available idents: {', '.join(h_ids[:10])}")
    if h_str:
        print(f"  Available strings: {h_str[:3]}")

    print(f"  Gap lines:")
    for idx, line, cat in gap_categories:
        marker = ">>" if cat != "BLANK_LINE" else ".."
        trunc = line[:70]
        print(f"    L{idx + 1:>2} [{cat:>15}] {marker} {trunc}")
    print()


# ========== SUMMARY ==========
print(f"\n{'=' * 70}")
print(f"RAPPORT FINAL — {len(failed)} cubes failed, {total_gaps_global} gap lines total")
print(f"{'=' * 70}")

print(f"\n--- ROOT CAUSES ---")
for root, count in sorted(all_roots.items(), key=lambda x: -x[1]):
    print(f"  {count:>2}x  {root}")

print(f"\n--- GAP LINE CATEGORIES ---")
for cat, count in sorted(all_gap_cats.items(), key=lambda x: -x[1]):
    pct = 100 * count / total_gaps_global if total_gaps_global else 0
    bar = "#" * int(pct / 2)
    print(f"  {cat:>15}: {count:>3} ({pct:4.1f}%) {bar}")

# Actionable recommendations
print(f"\n--- RECOMMANDATIONS ---")
blank_pct = 100 * all_gap_cats.get("BLANK_LINE", 0) / total_gaps_global
method_pct = 100 * all_gap_cats.get("METHOD_CALL", 0) / total_gaps_global
logic_pct = 100 * (all_gap_cats.get("LOGIC", 0) + all_gap_cats.get("CONTROL_FLOW", 0) +
                    all_gap_cats.get("NIL_CHECK", 0)) / total_gaps_global
var_pct = 100 * all_gap_cats.get("VAR_DECL", 0) / total_gaps_global
assign_pct = 100 * all_gap_cats.get("ASSIGNMENT", 0) / total_gaps_global

print(f"  1. BLANK LINES ({blank_pct:.0f}%): gofmt normalise, sinon forcer comme anchors")
print(f"  2. METHOD CALLS ({method_pct:.0f}%): scanner le fichier pour les patterns d'appel")
print(f"  3. LOGIC+FLOW ({logic_pct:.0f}%): irreductible sans plus de contexte")
print(f"  4. VAR DECL ({var_pct:.0f}%): extraire les declarations depuis le scope englobant")
print(f"  5. ASSIGNMENTS ({assign_pct:.0f}%): extraire les patterns d'affectation")
