#!/usr/bin/env python3
"""K.1.bis (2026-05-13) — Extend the static FR→EN lexicon via Wikidata SPARQL.

Goal: pull additional FR→EN concept pairs from Wikidata (license: CC0 =
public domain, commercially safe) and merge them with the hand-curated
MIT dict at `engine/core/data/lexicons/fr_en.json`.

Strategy:
  1. Query Wikidata SPARQL endpoint for items in tech/science/general
     categories that have BOTH a French and an English label.
  2. Filter out proper nouns (people / places / organizations) by
     excluding Q5 (human), Q515 (city), Q43229 (organization), etc.
  3. Keep only pairs where FR != EN (actual translation, not loanword).
  4. Merge with existing curated dict, prioritizing curated (more reliable
     for dev-vocab semantics).
  5. Write merged output back to fr_en.json.

Usage:
  python3 scripts/build_fr_en_dict.py [--dry-run] [--limit N]

License: this script is MIT (curated by Claude session 2026-05-13).
        The data it fetches from Wikidata is CC0 (public domain).
        The merged JSON output keeps the CC0-compatible status of both.

Network requirements:
  - SPARQL endpoint: https://query.wikidata.org/sparql
  - User-Agent: requests Mozilla-style + project URL (Wikidata etiquette)
  - Rate limit: this script makes ~5 queries with LIMIT N, well below quota.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

REPO_ROOT = Path(__file__).resolve().parent.parent
LEX_PATH = REPO_ROOT / "engine" / "core" / "data" / "lexicons" / "fr_en.json"
WIKIDATA_OUT = REPO_ROOT / "engine" / "core" / "data" / "lexicons" / "fr_en_wikidata.json"
SPARQL_URL = "https://query.wikidata.org/sparql"
USER_AGENT = (
    "muninn-memory/1.2.0 K.1.bis lexicon builder "
    "(https://github.com/sky1241/MUNINN- ; contact via GitHub issues)"
)

# Seed Q-IDs: categories from which we pull subclasses/instances having
# FR + EN labels. Curated to favour generic / tech / scientific concepts
# that appear in dev conversations.
SEED_CATEGORIES = [
    ("Q11862829", "academic discipline"),
    ("Q9143",     "programming language"),
    ("Q7397",     "software"),
    ("Q19660",    "data type"),
    ("Q205663",   "process"),
    ("Q336",      "science"),
    ("Q1183543",  "device"),
    ("Q21167972", "computer file format"),
    ("Q3966",     "computer hardware"),
    ("Q5447188",  "branch of computer science"),
    ("Q4671277",  "academic major"),
    ("Q1969448",  "field of study"),
    ("Q11862829", "discipline"),
    ("Q39825",    "color"),
    ("Q11772733", "cognitive process"),
    # Q35120 (entity) retiré : trop large, timeout systématique.
]

# Filter OUT these instance-of categories (proper nouns mostly):
#   Q5      = human
#   Q515    = city
#   Q43229  = organization
#   Q4830453= business
#   Q486972 = human settlement
#   Q571    = book
#   Q11424  = film
#   Q134556 = single (song)
EXCLUDED_INSTANCE_OF = ["Q5", "Q515", "Q43229", "Q4830453", "Q486972", "Q571", "Q11424", "Q134556"]


def sparql_query(query: str, timeout: int = 60) -> dict:
    """Run a SPARQL query against Wikidata; return JSON results."""
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": USER_AGENT,
    }
    url = SPARQL_URL + "?" + urlencode({"format": "json", "query": query})
    req = Request(url, headers=headers)
    with urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_pairs_for_category(qid: str, label: str, limit: int = 200) -> list[tuple[str, str]]:
    """For a seed Q-ID, pull instances/subclasses with FR + EN labels.

    Returns list of (fr_label, en_label) tuples, both lowercased + stripped.
    """
    excluded_values = " ".join(f"wd:{q}" for q in EXCLUDED_INSTANCE_OF)
    query = f"""
    SELECT DISTINCT ?label_fr ?label_en WHERE {{
        {{ ?item wdt:P279* wd:{qid} . }}
        UNION
        {{ ?item wdt:P31  wd:{qid} . }}
        ?item rdfs:label ?label_fr FILTER(LANG(?label_fr) = "fr") .
        ?item rdfs:label ?label_en FILTER(LANG(?label_en) = "en") .
        FILTER NOT EXISTS {{
            ?item wdt:P31 ?excluded .
            VALUES ?excluded {{ {excluded_values} }}
        }}
        FILTER (STR(?label_fr) != STR(?label_en))
        FILTER (STRLEN(STR(?label_fr)) >= 3)
        FILTER (STRLEN(STR(?label_fr)) <= 30)
        FILTER (STRLEN(STR(?label_en)) <= 30)
    }} LIMIT {limit}
    """
    try:
        result = sparql_query(query)
    except Exception as exc:
        print(f"  WARNING seed {qid} ({label}): {exc}", file=sys.stderr)
        return []
    pairs = []
    for binding in result.get("results", {}).get("bindings", []):
        fr = binding["label_fr"]["value"].lower().strip()
        en = binding["label_en"]["value"].lower().strip()
        # Sanity: single token-ish (no multi-word complex labels for our use)
        if " " in fr or " " in en:
            continue
        # Letters only (no digits, no punct)
        if not re.fullmatch(r"[a-zà-ÿ'-]+", fr):
            continue
        if not re.fullmatch(r"[a-z'-]+", en):
            continue
        pairs.append((fr, en))
    return pairs


def main() -> int:
    parser = argparse.ArgumentParser(description="K.1.bis Wikidata pull")
    parser.add_argument("--dry-run", action="store_true",
                        help="Print what would be added without writing fr_en.json")
    parser.add_argument("--limit", type=int, default=200,
                        help="Max pairs per seed category (default 200)")
    args = parser.parse_args()

    print(f"K.1.bis Wikidata FR→EN pull (CC0)")
    print(f"Seed categories: {len(SEED_CATEGORIES)}")
    print(f"Limit per seed: {args.limit}")
    print()

    # Load existing curated dict
    existing = json.loads(LEX_PATH.read_text(encoding="utf-8"))
    existing_keys = {k for k in existing if not k.startswith("_")}
    print(f"Existing curated entries: {len(existing_keys)}")

    # Pull from Wikidata
    all_pairs: dict[str, str] = {}
    for qid, label in SEED_CATEGORIES:
        print(f"  Querying {qid} ({label})...", end=" ", flush=True)
        pairs = fetch_pairs_for_category(qid, label, limit=args.limit)
        print(f"{len(pairs)} pairs")
        for fr, en in pairs:
            if fr not in all_pairs:
                all_pairs[fr] = en
        time.sleep(1.0)  # be polite to Wikidata
    print()

    # Filter: keep only pairs NOT already in curated
    new_pairs = {fr: en for fr, en in all_pairs.items() if fr not in existing_keys}
    print(f"Wikidata pulled: {len(all_pairs)} unique pairs")
    print(f"After filtering (not in curated): {len(new_pairs)} new pairs")

    if not new_pairs:
        print("Nothing to add.")
        return 0

    # Save Wikidata-only output for traceability
    wikidata_out = {
        "_meta": {
            "name": "Wikidata SPARQL pull FR→EN (CC0)",
            "version": "1.0.0",
            "created": time.strftime("%Y-%m-%d"),
            "license": "CC0 (Wikidata content)",
            "seeds": [q for q, _ in SEED_CATEGORIES],
            "limit_per_seed": args.limit,
            "total_pairs": len(new_pairs),
        },
        **{fr: en for fr, en in sorted(new_pairs.items())},
    }
    if not args.dry_run:
        WIKIDATA_OUT.write_text(
            json.dumps(wikidata_out, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {WIKIDATA_OUT}")

    # Merge into existing
    merged = dict(existing)
    for fr, en in new_pairs.items():
        merged[fr] = en
    if not args.dry_run:
        # Bump meta block
        if "_meta" in merged:
            meta = merged["_meta"]
            meta["wikidata_entries"] = len(new_pairs)
            meta["total_entries"] = len(merged) - 1  # minus _meta itself
            meta["last_wikidata_pull"] = time.strftime("%Y-%m-%d")
        LEX_PATH.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(f"Merged into {LEX_PATH} (total: {len(merged) - 1} entries)")
    else:
        print(f"[DRY RUN] Would merge {len(new_pairs)} new entries (total would be: {len(merged) - 1})")

    print()
    print("Sample of new pairs added:")
    for fr, en in list(new_pairs.items())[:10]:
        print(f"  {fr} → {en}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
