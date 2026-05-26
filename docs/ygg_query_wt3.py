"""
YGG QUERY TOOL — Pour Muninn
Permet de chercher dans WT3 (833K papiers, 69M co-occurrences, 65K concepts).

Usage:
    python ygg_query_wt3.py concept "epidemiology"
    python ygg_query_wt3.py title "DebtRank"
    python ygg_query_wt3.py cooc 1156 6985
    python ygg_query_wt3.py hole "Ising model" "software security"
    python ygg_query_wt3.py axes
"""
import sqlite3
import json
import sys
import os

PYTHON = r"C:\Users\ludov\AppData\Local\Programs\Python\Python313\python.exe"
DB = r"D:\ygg\yggdrasil-engine\data\wt3.db"
CONCEPTS = r"D:\ygg\yggdrasil-engine\data\scan\concepts_65k.json"

# ── Load concepts ──
def load_concepts():
    with open(CONCEPTS, "r", encoding="utf-8") as f:
        data = json.load(f)
    concepts = data.get("concepts", {})
    by_idx = {}
    by_name = {}
    for cid, info in concepts.items():
        idx = info.get("idx", -1)
        name = info.get("name", "")
        wc = info.get("works_count", 0)
        by_idx[idx] = {"id": cid, "name": name, "works_count": wc}
        by_name[name.lower()] = idx
    return by_idx, by_name

# ── Commands ──

def cmd_concept(query):
    """Cherche un concept par nom."""
    by_idx, by_name = load_concepts()
    q = query.lower()
    matches = [(idx, by_idx[idx]) for name, idx in by_name.items() if q in name]
    matches.sort(key=lambda x: -x[1]["works_count"])
    print(f"Concepts matching '{query}': {len(matches)}")
    for idx, info in matches[:20]:
        print(f"  [{idx:>5}] {info['name']:50s} ({info['works_count']:>10,} works)")
    return matches

def cmd_title(query):
    """Cherche des papiers par titre (LIKE %query%)."""
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM papers WHERE title LIKE ?", (f"%{query}%",))
    cnt = cur.fetchone()[0]
    print(f"Papers with '{query}' in title: {cnt}")
    if cnt > 0:
        cur.execute(
            "SELECT paper_id, title, year, domain FROM papers WHERE title LIKE ? ORDER BY year DESC LIMIT 20",
            (f"%{query}%",)
        )
        for r in cur.fetchall():
            print(f"  [{r[2]}] {r[3]:15s} {r[0]:30s} {str(r[1])[:80]}")
    conn.close()
    return cnt

def cmd_cooc(idx_a, idx_b):
    """Vérifie la co-occurrence entre deux concepts (par idx)."""
    by_idx, _ = load_concepts()
    a, b = int(idx_a), int(idx_b)
    name_a = by_idx.get(a, {}).get("name", "?")
    name_b = by_idx.get(b, {}).get("name", "?")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    cur.execute("""
        SELECT weight FROM cooc_global
        WHERE (concept_a=? AND concept_b=?) OR (concept_a=? AND concept_b=?)
    """, (a, b, b, a))
    row = cur.fetchone()
    w = row[0] if row else 0
    tag = "TROU" if w == 0 else ("faible" if w < 5 else ("moyen" if w < 50 else "fort"))
    print(f"Co-occurrence: [{a}] {name_a} x [{b}] {name_b} = {w:.2f} ({tag})")

    # Temporal
    cur.execute("""
        SELECT period, weight FROM cooc
        WHERE (concept_a=? AND concept_b=?) OR (concept_a=? AND concept_b=?)
        ORDER BY period
    """, (a, b, b, a))
    rows = cur.fetchall()
    if rows:
        print(f"  Timeline ({len(rows)} periods):")
        for period, weight in rows[-10:]:
            print(f"    {period}: {weight:.2f}")
    conn.close()
    return w

def cmd_hole(domain_a, domain_b):
    """Cherche le trou structurel entre deux domaines (par nom de concept)."""
    by_idx, by_name = load_concepts()
    matches_a = cmd_concept(domain_a)
    matches_b = cmd_concept(domain_b)
    if not matches_a or not matches_b:
        print("Pas assez de concepts trouvés.")
        return
    print(f"\n--- Cross co-occurrences (top 5 x top 5) ---")
    conn = sqlite3.connect(DB)
    cur = conn.cursor()
    for idx_a, info_a in matches_a[:5]:
        for idx_b, info_b in matches_b[:5]:
            cur.execute("""
                SELECT weight FROM cooc_global
                WHERE (concept_a=? AND concept_b=?) OR (concept_a=? AND concept_b=?)
            """, (idx_a, idx_b, idx_b, idx_a))
            row = cur.fetchone()
            w = row[0] if row else 0
            tag = ""
            if w == 0: tag = " << TROU"
            elif w < 5: tag = " << quasi-trou"
            print(f"  {info_a['name']:35s} x {info_b['name']:35s} = {w:>8.2f}{tag}")
    conn.close()

def cmd_axes():
    """Affiche les résultats du scan Carmack (depuis le JSON)."""
    json_path = os.path.join(os.path.dirname(__file__), "ygg_carmack_security.json")
    if not os.path.exists(json_path):
        json_path = r"D:\ygg\yggdrasil-engine\data\results\scan_carmack_security.json"
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    print("=== SCAN CARMACK SECURITY — Résumé ===")
    s = data.get("summary", {})
    print(f"  Paires testées: {s.get('cooc_pairs_tested', '?')}")
    print(f"  Trous zéro:     {s.get('true_holes_zero', '?')}")
    print(f"  Quasi-trous:    {s.get('weak_holes', '?')}")
    print(f"  Ponts forts:    {s.get('strong_bridges', '?')}")
    print(f"\n  Title searches zero: {s.get('title_zeros', '?')}")
    print(f"  Title searches rare: {s.get('title_rare', '?')}")

    print("\n=== Concepts par axe ===")
    for axe, cs in data.get("axis_concepts", {}).items():
        print(f"\n  {axe}:")
        for c in cs[:3]:
            print(f"    [{c['idx']:>5}] {c['name']:40s} ({c['works_count']:>10,} works)")

    print("\n=== Title searches ===")
    for label, info in data.get("title_searches", {}).items():
        cnt = info.get("count", "?")
        tag = ""
        if cnt == 0: tag = " << ZERO"
        elif isinstance(cnt, int) and cnt < 5: tag = " << RARE"
        print(f"  {label:40s} -> {cnt}{tag}")

# ── Main ──
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1]
    if cmd == "concept" and len(sys.argv) >= 3:
        cmd_concept(" ".join(sys.argv[2:]))
    elif cmd == "title" and len(sys.argv) >= 3:
        cmd_title(" ".join(sys.argv[2:]))
    elif cmd == "cooc" and len(sys.argv) >= 4:
        cmd_cooc(sys.argv[2], sys.argv[3])
    elif cmd == "hole" and len(sys.argv) >= 4:
        cmd_hole(sys.argv[2], sys.argv[3])
    elif cmd == "axes":
        cmd_axes()
    else:
        print(__doc__)
