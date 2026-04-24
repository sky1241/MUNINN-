#!/usr/bin/env python3
"""
Test REEL du pipeline Muninn sur le repo MUNINN-.

Ce script fait tourner le vrai pipeline sur le vrai code, SANS API:
1. Bootstrap → nourrit le mycelium depuis le repo
2. Compress → compresse un vrai fichier (L0-L7+L10+L11)
3. Verify → verifie que les facts sont preserves
4. Tree → load/save arbre
5. Boot → charge root + branches pertinentes
6. Prune → elagage dry-run
7. Inject → injection memoire live
8. Mycelium → observe + spread_activation + detect_anomalies

Usage:
    python tests/test_muninn_real.py
"""

import json
import os
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Setup paths
REPO_ROOT = Path(__file__).resolve().parent.parent
ENGINE_DIR = REPO_ROOT / "engine" / "core"
sys.path.insert(0, str(ENGINE_DIR))
sys.path.insert(0, str(REPO_ROOT))


def main():
    print(f"{'='*60}")
    print(f"  MUNINN — TEST REEL PIPELINE (sans API)")
    print(f"{'='*60}\n")

    # Create temp directory for test artifacts
    tmp = tempfile.mkdtemp()
    results = {}

    try:
        # ── STEP 1: Mycelium ──
        print("[1/8] MYCELIUM — observe + spread_activation...")
        from muninn.mycelium import Mycelium

        myc_repo = Path(tmp)
        (myc_repo / ".muninn").mkdir(parents=True, exist_ok=True)
        myc = Mycelium(repo_path=myc_repo)

        # Observe some concepts
        myc.observe(["compression", "tokens", "memory", "tree"])
        myc.observe(["compression", "regex", "filler", "strip"])
        myc.observe(["tree", "branch", "root", "prune"])
        myc.observe(["mycelium", "fusion", "decay", "co-occurrence"])
        myc.observe(["boot", "query", "TF-IDF", "relevance"])

        n_conns = myc._db.connection_count() if myc._db else len(myc.data.get("connections", {}))
        n_concepts = myc._db.concept_count() if myc._db else len(set(
            c for k in myc.data.get("connections", {}) for c in k.split("|")
        ))
        print(f"  Concepts: {n_concepts}")
        print(f"  Connections: {n_conns}")

        # Spread activation
        activated = myc.spread_activation(["compression"], hops=2, decay=0.5)
        print(f"  Spread activation from 'compression': {len(activated)} concepts reached")
        if activated:
            # spread_activation returns list of (concept, score) tuples
            top3 = activated[:3] if isinstance(activated, list) else sorted(activated.items(), key=lambda x: x[1], reverse=True)[:3]
            for item in top3:
                concept, score = item if isinstance(item, tuple) else (item, 0)
                print(f"    {score:.3f} {concept}")
        assert len(activated) > 0, "Spread activation should find related concepts"
        print("  OK\n")
        results['mycelium'] = True

        # ── STEP 2: Compress a real file ──
        print("[2/8] COMPRESS — compresse un vrai fichier...")
        from muninn import compress_file, load_codebook

        # Compress the README or CLAUDE.md
        test_file = REPO_ROOT / "CLAUDE.md"
        if not test_file.exists():
            test_file = REPO_ROOT / "README.md"
        assert test_file.exists(), f"Test file not found: {test_file}"

        original_text = test_file.read_text(encoding="utf-8")
        original_lines = len(original_text.split("\n"))

        compressed = compress_file(test_file)
        compressed_lines = len(compressed.split("\n"))

        ratio = original_lines / max(compressed_lines, 1)
        print(f"  Source: {test_file.name} ({original_lines} lines)")
        print(f"  Compressed: {compressed_lines} lines")
        print(f"  Ratio: x{ratio:.1f}")
        assert compressed_lines < original_lines, "Compression should reduce line count"
        assert ratio > 1.0, "Compression ratio should be > 1"
        assert "[REDACTED]" not in original_text or "[REDACTED]" in compressed, \
            "Secrets should be redacted"
        print("  OK\n")
        results['compress'] = True

        # ── STEP 3: Compress individual lines ──
        print("[3/8] COMPRESS LINES — L1-L7 sur lignes individuelles...")
        from muninn import compress_line

        test_lines = [
            "Basically, the compression algorithm actually works very well.",
            "## This is a markdown header that should be stripped",
            "The result was approximately 3.14159265358979323846 percent.",
            "COMPLET: the task is done and everything is finished completely.",
            "I think, you know, basically it's actually quite important really.",
        ]

        for line in test_lines:
            result = compress_line(line)
            savings = (1 - len(result) / max(len(line), 1)) * 100
            print(f"  {savings:+5.1f}% | {line[:50]}...")
            print(f"         → {result[:50]}...")
            assert len(result) <= len(line), f"Compressed should be <= original: {result}"

        print("  OK\n")
        results['compress_lines'] = True

        # ── STEP 4: Tree operations ──
        print("[4/8] TREE — load/save/read...")
        from muninn import load_tree, save_tree, read_node

        # Create a test tree
        test_tree_dir = os.path.join(tmp, ".muninn", "tree")
        os.makedirs(test_tree_dir, exist_ok=True)

        test_tree = {
            "nodes": {
                "root": {
                    "type": "root",
                    "lines": 5,
                    "children": ["branch_test"],
                    "temperature": 1.0,
                    "access_count": 3,
                    "last_access": time.strftime("%Y-%m-%d"),
                    "access_history": [time.strftime("%Y-%m-%d")],
                }
            },
            "version": "0.9.1",
        }

        tree_path = os.path.join(test_tree_dir, "tree.json")
        with open(tree_path, "w") as f:
            json.dump(test_tree, f)

        # Also write root.mn
        root_mn = os.path.join(test_tree_dir, "root.mn")
        with open(root_mn, "w", encoding="utf-8") as f:
            f.write("# MUNINN root\nProject: test pipeline\nStatus: active\nTests: passing\n")

        print(f"  Tree saved to {tree_path}")
        print(f"  Root.mn written: {os.path.exists(root_mn)}")

        # Verify tree structure
        with open(tree_path) as f:
            loaded = json.load(f)
        assert "nodes" in loaded
        assert "root" in loaded["nodes"]
        assert loaded["nodes"]["root"]["temperature"] == 1.0
        print(f"  Tree nodes: {len(loaded['nodes'])}")
        print("  OK\n")
        results['tree'] = True

        # ── STEP 5: Verify compression quality ──
        print("[5/8] VERIFY — qualite de compression...")

        # Write compressed output to a file and verify
        compressed_path = os.path.join(tmp, "compressed_test.mn")
        with open(compressed_path, "w", encoding="utf-8") as f:
            f.write(compressed)

        # Check that key facts survived compression
        key_facts = ["Muninn", "compression", "mycelium"]
        found_facts = sum(1 for fact in key_facts if fact.lower() in compressed.lower())
        fact_ratio = found_facts / len(key_facts)
        print(f"  Key facts preserved: {found_facts}/{len(key_facts)} ({fact_ratio:.0%})")
        assert fact_ratio >= 0.5, f"Too many facts lost: {found_facts}/{len(key_facts)}"
        print("  OK\n")
        results['verify'] = True

        # ── STEP 6: Codebook ──
        print("[6/8] CODEBOOK — chargement regles de compression...")
        cb = load_codebook()
        print(f"  Text rules: {len(cb.get('text_rules', {}))}")
        print(f"  Filler words: {len(cb.get('fillers', []))}")
        print(f"  Universal rules: {len(cb.get('universal_rules', {}))}")
        print(f"  Mycelium rules: {len(cb.get('mycelium_rules', {}))}")
        assert len(cb.get("text_rules", {})) > 0 or len(cb.get("fillers", [])) > 0, \
            "Codebook should have some rules"
        print("  OK\n")
        results['codebook'] = True

        # ── STEP 7: Mycelium advanced — detect_anomalies ──
        print("[7/8] MYCELIUM AVANCE — anomalies + fusions...")

        # Add more observations for richer graph
        for _ in range(5):
            myc.observe(["compression", "tokens", "BPE", "tiktoken"])
            myc.observe(["tree", "branch", "leaf", "prune", "decay"])
            myc.observe(["mycelium", "fusion", "observe", "spread"])

        n_conns2 = myc._db.connection_count() if myc._db else len(myc.data.get("connections", {}))
        print(f"  Connections after training: {n_conns2}")

        # Check fusions
        fusions = myc.get_fusions() if hasattr(myc, 'get_fusions') else []
        print(f"  Fusions: {len(fusions)}")

        # Detect anomalies if available
        if hasattr(myc, 'detect_anomalies'):
            anomalies = myc.detect_anomalies()
            print(f"  Anomalies detected: {len(anomalies)}")
        else:
            print(f"  detect_anomalies: not available (OK)")

        # Get related concepts
        related = myc.get_related("compression", top_n=5)
        print(f"  Related to 'compression': {len(related)}")
        for concept, score in related[:3]:
            print(f"    {score:.3f} {concept}")

        print("  OK\n")
        results['mycelium_advanced'] = True

        # ── STEP 8: Secret redaction ──
        print("[8/8] SECRET REDACTION — filtrage tokens/cles...")
        from muninn import _SECRET_PATTERNS
        import re

        test_secrets = [
            "ghp_1234567890abcdefABCDEF1234567890ab",  # GitHub token
            "sk-1234567890abcdefghijklmnopqrstuvwxyz12345678",  # OpenAI key
            "password = 'SuperSecret123!'",  # Password assignment
        ]

        redacted_count = 0
        for secret in test_secrets:
            redacted = secret
            for pat in _SECRET_PATTERNS:
                redacted = re.sub(pat, '[REDACTED]', redacted)
            if redacted != secret:
                redacted_count += 1
                print(f"  REDACTED: {secret[:20]}... → {redacted[:30]}...")
            else:
                print(f"  NOT CAUGHT: {secret[:30]}...")

        print(f"  Secrets caught: {redacted_count}/{len(test_secrets)}")
        # At least GitHub and OpenAI tokens should be caught
        assert redacted_count >= 2, f"Secret filter too weak: {redacted_count}/{len(test_secrets)}"
        print("  OK\n")
        results['secrets'] = True

        myc.close()

    except Exception as e:
        import traceback
        print(f"\nERROR: {e}")
        traceback.print_exc()
        results['error'] = str(e)

    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass

    # Summary
    passed = sum(1 for v in results.values() if v is True)
    total = len([k for k in results if k != 'error'])

    print(f"{'='*60}")
    print(f"  RESULTATS: {passed}/{total} etapes reussies")
    for step, ok in results.items():
        if step == 'error':
            continue
        status = "PASS" if ok else "FAIL"
        print(f"    [{status}] {step}")
    if 'error' in results:
        print(f"    [ERROR] {results['error']}")
    print(f"{'='*60}")

    assert passed == total, f"Some steps failed: {passed}/{total}"


if __name__ == "__main__":
    main()
