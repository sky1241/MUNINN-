#!/usr/bin/env python3
"""Analyze MEMORY.md to find compression patterns."""
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
MEMORY = ROOT / "memory" / "root.mn"

text = MEMORY.read_text(encoding="utf-8")

# Most frequent words (3+ chars)
words = re.findall(r'[A-Za-zÀ-ÿ_/]{3,}', text)
wc = Counter(words)
print("=== MOTS LES PLUS FREQUENTS ===")
for w, c in wc.most_common(30):
    print(f"  {c:3d}x {w}")

# Status patterns
patterns = re.findall(r'(?:COMPLET|VALIDÉ|FIXÉ|EN COURS|PRÊT)', text)
print(f"\n=== ETATS ===")
for p, c in Counter(patterns).most_common():
    print(f"  {c:3d}x {p}")

# Inline code / paths
paths = re.findall(r'`([^`]+)`', text)
print(f"\n=== CHEMINS/CODE ({len(paths)} occurrences) ===")
for p, c in Counter(paths).most_common(15):
    print(f"  {c:3d}x {p}")

# Sessions referenced
sessions = re.findall(r'session\s+\d+', text)
print(f"\n=== SESSIONS ({len(sessions)} refs) ===")
for s, c in Counter(sessions).most_common():
    print(f"  {c:3d}x {s}")

# Repeated number patterns
numbers = re.findall(r'\d[\d,._]+', text)
print(f"\n=== NOMBRES FREQUENTS ===")
for n, c in Counter(numbers).most_common(20):
    print(f"  {c:3d}x {n}")

# Section headers
headers = re.findall(r'^##\s+(.+)$', text, re.MULTILINE)
print(f"\n=== SECTIONS ({len(headers)}) ===")
for h in headers:
    print(f"  {h}")

# Total stats
lines = text.count('\n')
chars = len(text)
print(f"\n=== STATS ===")
print(f"  Lignes: {lines}")
print(f"  Chars: {chars}")
print(f"  Mots uniques: {len(wc)}")
print(f"  Tokens estimes: {chars // 4}-{chars // 3}")
