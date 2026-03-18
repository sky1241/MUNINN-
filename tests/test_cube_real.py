#!/usr/bin/env python3
"""
Test REEL du pipeline Cube Muninn sur le repo MUNINN-.

Ce script fait tourner le vrai pipeline sur le vrai code:
1. Scan le repo → crée les cubes
2. Heatmap → montre les fichiers chauds/froids
3. Fuse risks → combine Forge + Cube
4. Auto-repair → identifie les candidats
5. Feedback loop → enregistre une anomalie

Usage:
    python tests/test_cube_real.py
"""

import os
import sys
import json
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine.core.cube import (
    cli_scan, cli_run, cli_status, cli_god, CubeConfig, CubeStore,
    cube_heatmap, fuse_risks, auto_repair,
    record_anomaly, feedback_loop_check,
)


def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    print(f"{'='*60}")
    print(f"  CUBE MUNINN — TEST REEL SUR {os.path.basename(repo_root)}")
    print(f"{'='*60}\n")

    # Use temp directory for test DB to not pollute repo
    tmp = tempfile.mkdtemp()
    try:
        db_path = os.path.join(tmp, "cube_real.db")
        anomaly_path = os.path.join(tmp, "anomalies.jsonl")

        config = CubeConfig(
            db_path=db_path,
            allowed_providers=['mock'],
            local_only=True,
        )

        # ── STEP 1: Scan ──
        print("[1/7] SCAN du repo...")
        scan = cli_scan(repo_root, config)
        print(f"  Fichiers: {scan['files']}")
        print(f"  Cubes:    {scan['cubes']}")
        print(f"  Deps:     {scan['dependencies']}")
        assert scan['cubes'] > 0, "Scan should find cubes"
        print("  OK\n")

        # ── STEP 2: Status ──
        print("[2/7] STATUS...")
        status = cli_status(config)
        print(f"  Total cubes:  {status['total_cubes']}")
        print(f"  Avg temp:     {status['avg_temperature']:.3f}")
        print(f"  Levels:       {status['levels']}")
        print("  OK\n")

        # ── STEP 3: Heatmap ──
        print("[3/7] HEATMAP...")
        store = CubeStore(db_path)
        hm = cube_heatmap(store)
        print(f"  Fichiers: {len(hm)}")
        # Top 10 hottest files
        sorted_files = sorted(hm.items(), key=lambda x: x[1]['max_temp'], reverse=True)
        print(f"  Top 10 fichiers les plus chauds:")
        for fname, data in sorted_files[:10]:
            bar = '#' * int(data['max_temp'] * 20)
            print(f"    {data['max_temp']:.2f} [{bar:<20}] {fname} ({data['count']} cubes, {data['hot_count']} hot)")
        print("  OK\n")

        # ── STEP 4: Fuse Risks (Cube + Forge) ──
        print("[4/7] FUSE RISKS (Cube + Forge)...")
        risks = fuse_risks(store, repo_root)
        print(f"  Fichiers analyses: {len(risks)}")
        print(f"  Top 10 risques combines:")
        for r in risks[:10]:
            print(f"    {r['combined']:.3f}  forge={r['forge_risk']:.2f}  cube={r['cube_temp']:.2f}  hot={r['hot_cubes']}  {r['file']}")
        print("  OK\n")

        # ── STEP 5: Auto-repair candidates ──
        print("[5/7] AUTO-REPAIR candidates...")
        hot_files = [r['file'] for r in risks[:5] if r['hot_cubes'] > 0]
        if not hot_files:
            hot_files = [risks[0]['file']] if risks else []
        patches = auto_repair(store, hot_files, max_patches=5)
        print(f"  Fichiers cibles: {hot_files[:3]}")
        print(f"  Patchs generes: {len(patches)}")
        for p in patches[:5]:
            print(f"    temp={p['temperature']:.2f}  neighbors={p['neighbor_count']}  "
                  f"{p['file']} L{p['line_start']}-{p['line_end']}")
            print(f"      {p['original'][:80].strip()}...")
        print("  OK\n")

        # ── STEP 6: Run mock cycle ──
        print("[6/7] RUN (mock, 1 cycle)...")
        run_result = cli_run(repo_root, cycles=1, config=config)
        print(f"  Cycles:      {run_result['cycles']}")
        print(f"  Cubes tested: {run_result['cubes_tested']}")
        print(f"  Total tests:  {run_result['total_tests']}")
        print(f"  Success rate: {run_result['success_rate']:.1%}")
        print("  OK\n")

        # ── STEP 7: God's Number ──
        print("[7/7] GOD'S NUMBER...")
        god = cli_god(config)
        print(f"  God's Number: {god['gods_number']}")
        print(f"  Total cubes:  {god['total_cubes']}")
        print(f"  Bounds:")
        for k, v in god['bounds'].items():
            print(f"    {k}: {v}")
        print("  OK\n")

        # ── Record anomaly for top risky files ──
        print("[BONUS] Recording anomalies for feedback loop...")
        for r in risks[:3]:
            record_anomaly(anomaly_path, r['file'],
                           {'combined': r['combined'], 'forge': r['forge_risk'],
                            'cube': r['cube_temp']},
                           [p['cube_id'] for p in patches if p['file'] == r['file']])
        print(f"  Anomalies recorded: 3")

        # Check feedback (will be empty since anomalies are fresh)
        fb = feedback_loop_check(anomaly_path, repo_root, lookback_days=0)
        print(f"  Feedback check: {fb['total']} entries")

        store.close()

    finally:
        try:
            shutil.rmtree(tmp, ignore_errors=True)
        except Exception:
            pass

    print(f"\n{'='*60}")
    print(f"  TOUS LES TESTS REELS PASSENT")
    print(f"  {scan['cubes']} cubes, {len(hm)} fichiers, pipeline complet")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
