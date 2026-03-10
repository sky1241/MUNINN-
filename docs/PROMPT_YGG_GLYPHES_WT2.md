# Mission Yggdrasil #2 — Scan par GLYPHES (WT2) des formules invisibles

## Contexte

Premier scan fait (scan_muninn.py): 172K paires, 128 anti-signaux P5, bon boulot.
MAIS: 3 formules Muninn sont passees sous le radar parce que leurs concepts OpenAlex
sont trop petits pour le z-score Uzzi (activite insuffisante des deux cotes).

Ces 3 formules:
- **F5**: Exponential Moving Average (EMA) — concept idx 5237
- **F8**: Co-occurrence decay — concept idx 8467
- **F9**: Novelty detection / Predictive coding — concept idx 28203 / 32258

Le scan par CONCEPTS (WT1) ne peut pas les trouver. Il faut scanner par GLYPHES (WT2).

**IMPORTANT: NE CHERCHE PAS SUR INTERNET. Utilise WT2 + bipartite + glyph_registry.**

---

## Les glyph_ids dont tu as besoin

J'ai deja fait le lookup dans glyph_registry.json pour toi:

```python
# Glyphes Muninn — IDs confirmes depuis glyph_registry.json
GLYPHS = {
    "alpha":   90,   # \alpha — coefficient EMA, significance level
    "tau":     109,  # \tau — time constant, decay
    "sum":     451,  # \sum — sommation
    "in":      442,  # \in — appartenance (x in set)
    "geq":     535,  # \geq — greater or equal (seuil)
    "leq":     534,  # \leq — less or equal
    "cdot":    631,  # \cdot — multiplication, dot product
    "pm":      21,   # \pm — plus or minus
    "minus":   4,    # - (signe moins, glyph_id=4 = hyphen-minus)
    "plus":    5,    # + (glyph_id=5)
    "lparen":  2,    # ( parenthese gauche
    "rparen":  3,    # ) parenthese droite
    "exp_2":   None, # 2^x — pas un glyph unique, c'est "2" + superscript
}

# Signatures de formules (combinaisons de glyphs dans un meme papier)
F5_EMA = {90, 631, 5, 4}         # alpha, cdot, +, - (S = alpha*x + (1-alpha)*S)
F8_DECAY = {109, 535, 631}       # tau, geq, cdot (w = w * 2^(-1/tau), seuil >= 3)
F9_NOVELTY = {451, 442, 4}       # sum, in, minus (sum(novel) - sum(known))
```

---

## Le script — copie-colle et execute

```python
"""
scan_muninn_glyphs.py — Scan WT2 par combinaisons de glyphes
Cherche les papiers qui utilisent les memes structures math que Muninn F5/F8/F9
"""
import json, gzip, os, sqlite3
from collections import Counter, defaultdict
from pathlib import Path

BASE = Path(r"C:\Users\ludov\Desktop\ygg\yggdrasil-engine")
WT2_DIR = BASE / "data" / "scan" / "wt2_chunks"
DB_PATH = BASE / "data" / "bible" / "wt3.db"
CONCEPT_INDEX = BASE / "data" / "core" / "concept_index.json"

# ══════════════════════════════════════════════════════════
# 1. GLYPH IDS (confirmes depuis glyph_registry.json)
# ══════════════════════════════════════════════════════════
FORMULAS = {
    "F5_EMA": {
        "name": "Exponential Moving Average",
        "equation": "S_t = alpha * x_t + (1 - alpha) * S_{t-1}",
        # alpha + multiplication + addition + soustraction
        "required": {90, 631},      # alpha ET cdot = forte signature EMA
        "optional": {5, 4, 2, 3},   # +, -, (, )
        "min_optional": 1,          # au moins 1 optionnel en plus
    },
    "F8_DECAY": {
        "name": "Co-occurrence decay with threshold",
        "equation": "w_{t+1} = w_t * 2^{-1/tau}, immortal if |Z| >= 3",
        # tau + seuil >= = forte signature decay avec condition
        "required": {109, 535},     # tau ET geq
        "optional": {631, 4, 534},  # cdot, -, leq
        "min_optional": 0,
    },
    "F9_NOVELTY": {
        "name": "Novelty scoring (sum positive - sum negative)",
        "equation": "novelty = sum(novel) - sum(known) with indicator",
        # sum + appartenance + soustraction = scoring avec indicatrice
        "required": {451, 442},     # sum ET in
        "optional": {4, 535, 534},  # -, geq, leq (seuils)
        "min_optional": 1,
    },
}

# ══════════════════════════════════════════════════════════
# 2. SCAN BIPARTITE (quels concepts utilisent ces glyphes?)
# ══════════════════════════════════════════════════════════
print("=" * 60)
print("PHASE 1: Bipartite scan (glyph -> concepts)")
print("=" * 60)

conn = sqlite3.connect(str(DB_PATH))
cursor = conn.cursor()

# Charge concept index pour les noms
try:
    with open(CONCEPT_INDEX, "r") as f:
        concept_names = json.load(f)
except Exception:
    concept_names = {}

all_glyph_ids = set()
for formula in FORMULAS.values():
    all_glyph_ids |= formula["required"]
    all_glyph_ids |= formula["optional"]

for gid in sorted(all_glyph_ids):
    cursor.execute(
        "SELECT concept_id, weight FROM bipartite WHERE glyph_id = ? ORDER BY weight DESC LIMIT 20",
        (gid,)
    )
    rows = cursor.fetchall()
    print(f"\n  Glyph {gid}: {len(rows)} top concepts")
    for cid, w in rows[:5]:
        name = concept_names.get(str(cid), {}).get("name", f"concept_{cid}")
        print(f"    concept {cid} ({name}): weight={w:.2f}")

# ══════════════════════════════════════════════════════════
# 3. SCAN WT2 CHUNKS (papiers avec combo de glyphes)
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 2: WT2 chunk scan (papers with glyph combos)")
print("=" * 60)

results = {fname: {
    "papers": [],
    "domain_counts": Counter(),
    "concept_counts": Counter(),
} for fname in FORMULAS}

chunks = sorted(WT2_DIR.iterdir()) if WT2_DIR.exists() else []
print(f"  Scanning {len(chunks)} WT2 chunks...")

for i, chunk_dir in enumerate(chunks):
    papers_path = chunk_dir / "papers.json.gz"
    if not papers_path.exists():
        continue

    with gzip.open(papers_path, "rt") as f:
        papers = json.load(f)

    for paper_id, info in papers.items():
        glyphs = set(info.get("g", []))
        domain = info.get("d", "Unknown")
        concepts = info.get("c", [])

        for fname, formula in FORMULAS.items():
            # Check: all required glyphs present?
            if not formula["required"].issubset(glyphs):
                continue
            # Check: enough optional glyphs?
            optional_hits = len(formula["optional"] & glyphs)
            if optional_hits < formula["min_optional"]:
                continue
            # MATCH
            results[fname]["papers"].append({
                "id": paper_id,
                "domain": domain,
                "concepts": concepts,
                "glyphs_matched": sorted(formula["required"] | (formula["optional"] & glyphs)),
            })
            results[fname]["domain_counts"][domain] += 1
            for cid in concepts:
                results[fname]["concept_counts"][cid] += 1

    if (i + 1) % 50 == 0:
        print(f"  ... {i+1}/{len(chunks)} chunks")

print(f"  Done: {len(chunks)} chunks scanned")

# ══════════════════════════════════════════════════════════
# 4. RESULTATS
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 3: Results")
print("=" * 60)

for fname, formula in FORMULAS.items():
    r = results[fname]
    n = len(r["papers"])
    print(f"\n{'─' * 50}")
    print(f"  {fname}: {formula['name']}")
    print(f"  Equation: {formula['equation']}")
    print(f"  Papers matched: {n}")

    if n == 0:
        print("  (aucun match — signature trop restrictive?)")
        continue

    # Domain distribution
    print(f"\n  Domains:")
    for dom, count in r["domain_counts"].most_common(15):
        pct = 100 * count / n
        print(f"    {dom}: {count} ({pct:.1f}%)")

    # Top concepts
    print(f"\n  Top concepts:")
    for cid, count in r["concept_counts"].most_common(20):
        name = concept_names.get(str(cid), {}).get("name", f"concept_{cid}")
        print(f"    {cid} ({name}): {count} papers")

    # Non-CS/Math domains (the interesting ones)
    foreign = [(dom, c) for dom, c in r["domain_counts"].most_common()
               if dom not in ("Computer Science", "Mathematics", "CS", "Math")]
    if foreign:
        print(f"\n  DOMAINES ETRANGERS (hors CS/Math):")
        for dom, count in foreign[:10]:
            print(f"    {dom}: {count}")

    # Sample paper IDs (first 10)
    print(f"\n  Sample papers:")
    for p in r["papers"][:10]:
        print(f"    {p['id']} [{p['domain']}] glyphs={p['glyphs_matched']}")

# ══════════════════════════════════════════════════════════
# 5. CROSS-REFERENCE avec scan_muninn.json
# ══════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("PHASE 4: Cross-reference with first scan")
print("=" * 60)

scan_path = BASE / "data" / "results" / "scan_muninn_enriched.json"
if scan_path.exists():
    with open(scan_path) as f:
        first_scan = json.load(f)
    # Extract concept pairs already found
    known_concepts = set()
    if isinstance(first_scan, list):
        for entry in first_scan:
            if "concept_a" in entry and "concept_b" in entry:
                known_concepts.add((entry["concept_a"], entry["concept_b"]))
                known_concepts.add((entry["concept_b"], entry["concept_a"]))
    print(f"  Known pairs from first scan: {len(known_concepts)//2}")

    for fname in FORMULAS:
        r = results[fname]
        new_concepts = set()
        for cid, count in r["concept_counts"].most_common(50):
            # Check if this concept was in any pair from first scan
            is_new = True
            for known_a, known_b in known_concepts:
                if cid == known_a or cid == known_b:
                    is_new = False
                    break
            if is_new:
                name = concept_names.get(str(cid), {}).get("name", f"concept_{cid}")
                new_concepts.add((cid, name, count))
        if new_concepts:
            print(f"\n  {fname} — NOUVEAUX concepts (absents du 1er scan):")
            for cid, name, count in sorted(new_concepts, key=lambda x: -x[2])[:15]:
                print(f"    {cid} ({name}): {count} papers")
else:
    print("  scan_muninn_enriched.json not found — skip cross-reference")

conn.close()

# ══════════════════════════════════════════════════════════
# 6. SAVE
# ══════════════════════════════════════════════════════════
output_path = BASE / "data" / "results" / "scan_muninn_glyphs.json"
output_path.parent.mkdir(parents=True, exist_ok=True)

save_data = {}
for fname in FORMULAS:
    r = results[fname]
    save_data[fname] = {
        "total_papers": len(r["papers"]),
        "domains": dict(r["domain_counts"].most_common()),
        "top_concepts": [(cid, count) for cid, count in r["concept_counts"].most_common(50)],
        "sample_papers": r["papers"][:50],
    }

with open(output_path, "w") as f:
    json.dump(save_data, f, indent=2)
print(f"\nSaved to {output_path}")
print("Done.")
```

---

## Mode d'emploi

1. Copie le script ci-dessus dans un fichier (ou execute-le directement)
2. Il va:
   - Phase 1: Query bipartite pour chaque glyph (quels concepts?)
   - Phase 2: Scanner les 416 chunks WT2 (833K papiers)
   - Phase 3: Afficher les resultats par formule (domaines, concepts, papers)
   - Phase 4: Cross-reference avec scan_muninn_enriched.json
   - Phase 5: Sauvegarder dans data/results/scan_muninn_glyphs.json
3. Ca devrait tourner en ~2-5 minutes (416 chunks de ~12K papiers chacun)

## Ce qu'on veut que tu nous renvoies

Pour chaque formule (F5, F8, F9):
- Nombre de papiers matches
- Distribution par domaine (surtout les domaines ETRANGERS hors CS/Math)
- Top 20 concepts trouves
- Les concepts NOUVEAUX (absents du premier scan Uzzi)
- 10 paper IDs exemples par domaine etranger

Et ton interpretation: quels trous P4/P5 et quel Type A/B/C.
