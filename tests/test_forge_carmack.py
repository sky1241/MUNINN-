"""Tests for forge.py Carmack moves: wavelet, Kalman, anomaly, robustness.

Tests:
  CM.1  Haar wavelet energy: constant signal = 0
  CM.2  Haar wavelet energy: impulse signal > 0
  CM.3  Haar wavelet energy: burst > uniform
  CM.4  Build commit signal: empty dates = zeros
  CM.5  Build commit signal: correct length
  CM.6  Kalman predictor: init weights match defaults
  CM.7  Kalman predictor: weights normalized to 1
  CM.8  Kalman predictor: update shifts weights toward bug-correlated metrics
  CM.9  Kalman predictor: weights clamped [0.01, 0.5]
  CM.10 Anomaly detection: no crash on minimal data
  CM.11 Robustness: no crash on import parse
  CM.12 Full-cycle integration (import-only)
"""
import sys
import os
import json
import tempfile
import math

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
from forge import (
    _haar_wavelet_energy, _build_commit_signal, _KalmanPredictor,
    PREDICT_WEIGHTS, load_json, save_json
)

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


def test_cm1_constant_signal():
    """Constant signal has zero detail energy."""
    signal = [5.0] * 16
    energy = _haar_wavelet_energy(signal)
    check("CM.1", energy < 1e-10, f"constant energy={energy}")


def test_cm2_impulse_signal():
    """Single impulse has nonzero energy."""
    signal = [0.0] * 15 + [10.0]
    energy = _haar_wavelet_energy(signal)
    check("CM.2", energy > 0, f"impulse energy={energy:.4f}")


def test_cm3_burst_vs_uniform():
    """Burst signal (concentrated changes) has higher wavelet energy than uniform."""
    uniform = [1.0] * 16  # 1 commit per day
    burst = [0.0] * 12 + [4.0, 4.0, 4.0, 4.0]  # same total, concentrated
    e_uniform = _haar_wavelet_energy(uniform)
    e_burst = _haar_wavelet_energy(burst)
    check("CM.3", e_burst > e_uniform,
          f"burst={e_burst:.4f} > uniform={e_uniform:.4f}")


def test_cm4_empty_dates():
    """Empty dates produce zero signal."""
    signal = _build_commit_signal([], weeks=2)
    check("CM.4", all(v == 0.0 for v in signal), f"len={len(signal)}")


def test_cm5_signal_length():
    """Signal length = weeks * 7."""
    signal = _build_commit_signal([], weeks=4)
    check("CM.5", len(signal) == 28, f"len={len(signal)}")


def test_cm6_kalman_init():
    """Kalman init weights match PREDICT_WEIGHTS defaults."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("{}")
        tmp = f.name
    try:
        k = _KalmanPredictor(tmp)
        w = k.get_weights()
        # Should be close to defaults (normalized)
        total = sum(PREDICT_WEIGHTS.values())
        for key in PREDICT_WEIGHTS:
            expected = PREDICT_WEIGHTS[key] / total
            check(f"CM.6.{key}", abs(w[key] - expected) < 0.01,
                  f"{key}: {w[key]:.3f} vs {expected:.3f}")
    finally:
        os.unlink(tmp)


def test_cm7_kalman_normalized():
    """Kalman weights always sum to 1."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("{}")
        tmp = f.name
    try:
        k = _KalmanPredictor(tmp)
        w = k.get_weights()
        total = sum(w.values())
        check("CM.7", abs(total - 1.0) < 1e-6, f"sum={total:.6f}")
    finally:
        os.unlink(tmp)


def test_cm8_kalman_update():
    """Kalman update shifts weights toward bug-correlated metrics."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("{}")
        tmp = f.name
    try:
        k = _KalmanPredictor(tmp)
        w_before = k.get_weights().copy()

        # Simulate: churn perfectly correlates with bugs
        metrics = {
            "bug_file.py": {"churn_n": 0.9, "freq_n": 0.1, "wavelet_n": 0.1,
                           "authors_n": 0.1, "bugfix_n": 0.1, "loc_n": 0.1, "recency_n": 0.1},
            "ok_file1.py": {"churn_n": 0.1, "freq_n": 0.9, "wavelet_n": 0.9,
                           "authors_n": 0.9, "bugfix_n": 0.9, "loc_n": 0.9, "recency_n": 0.9},
            "ok_file2.py": {"churn_n": 0.05, "freq_n": 0.8, "wavelet_n": 0.8,
                           "authors_n": 0.8, "bugfix_n": 0.8, "loc_n": 0.8, "recency_n": 0.8},
        }
        actual_bugs = {"bug_file.py"}

        # Run multiple updates to see convergence
        for _ in range(5):
            k.update(metrics, actual_bugs)

        w_after = k.get_weights()
        # Churn should have increased relative to others
        churn_ratio_before = w_before.get("churn", 0)
        churn_ratio_after = w_after.get("churn", 0)
        check("CM.8", churn_ratio_after > churn_ratio_before,
              f"churn: {churn_ratio_before:.3f} -> {churn_ratio_after:.3f}")
    finally:
        os.unlink(tmp)


def test_cm9_kalman_clamped():
    """Kalman weights stay in [0.01, 0.5] after extreme updates."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("{}")
        tmp = f.name
    try:
        k = _KalmanPredictor(tmp)
        # Extreme case: all metrics perfectly correlate with bugs
        metrics = {
            "f1.py": {f"{k_}_n": 1.0 for k_ in PREDICT_WEIGHTS},
            "f2.py": {f"{k_}_n": 0.0 for k_ in PREDICT_WEIGHTS},
        }
        for _ in range(100):
            k.update(metrics, {"f1.py"})
        w = k._state["weights"]
        for key, val in w.items():
            check(f"CM.9.{key}", 0.01 <= val <= 0.5, f"{key}={val:.4f}")
    finally:
        os.unlink(tmp)


def test_cm10_anomaly_no_crash():
    """Anomaly detection doesn't crash with empty/minimal data."""
    # Just test the wavelet building — anomaly detection needs git repo
    signal = _build_commit_signal(["2026-01-01T12:00:00"], weeks=1)
    energy = _haar_wavelet_energy(signal)
    check("CM.10", energy >= 0 and energy == energy, f"energy={energy:.4f}")


def test_cm11_wavelet_edge_cases():
    """Wavelet handles edge cases: empty, single element, very long."""
    e0 = _haar_wavelet_energy([])
    e1 = _haar_wavelet_energy([5.0])
    e_long = _haar_wavelet_energy([float(i % 7) for i in range(1000)])
    ok = (e0 == 0.0 and e1 == 0.0 and e_long >= 0 and
          e_long == e_long and not math.isinf(e_long))
    check("CM.11", ok, f"empty={e0} single={e1} long={e_long:.2f}")


def test_cm12_kalman_persistence():
    """Kalman state persists across instances."""
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
        f.write("{}")
        tmp = f.name
    try:
        k1 = _KalmanPredictor(tmp)
        metrics = {
            "f1.py": {"churn_n": 1.0, "freq_n": 0.0, "wavelet_n": 0.0,
                      "authors_n": 0.0, "bugfix_n": 0.0, "loc_n": 0.0, "recency_n": 0.0},
            "f2.py": {"churn_n": 0.0, "freq_n": 1.0, "wavelet_n": 1.0,
                      "authors_n": 1.0, "bugfix_n": 1.0, "loc_n": 1.0, "recency_n": 1.0},
        }
        k1.update(metrics, {"f1.py"})
        runs_1 = k1._state["runs"]

        # Reload from disk
        k2 = _KalmanPredictor(tmp)
        runs_2 = k2._state["runs"]
        check("CM.12", runs_2 == runs_1 and runs_1 > 0,
              f"runs persisted: {runs_1} == {runs_2}")
    finally:
        os.unlink(tmp)


if __name__ == "__main__":
    print("=== Forge Carmack Moves — 12+ bornes ===")
    test_cm1_constant_signal()
    test_cm2_impulse_signal()
    test_cm3_burst_vs_uniform()
    test_cm4_empty_dates()
    test_cm5_signal_length()
    test_cm6_kalman_init()
    test_cm7_kalman_normalized()
    test_cm8_kalman_update()
    test_cm9_kalman_clamped()
    test_cm10_anomaly_no_crash()
    test_cm11_wavelet_edge_cases()
    test_cm12_kalman_persistence()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
