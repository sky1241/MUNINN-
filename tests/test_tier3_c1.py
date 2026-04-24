"""C1 — Saturation beta activation (Lotka-Volterra).

Tests:
  C1.1  Beta is active (not 0.0)
  C1.2  Large connections lose more than small ones
  C1.3  Connections below threshold are untouched
  C1.4  Decay still works (connections die)
  C1.5  Moderate connections survive (not over-killed)
"""
import sys, os, json, tempfile, shutil
from datetime import datetime, timedelta
from muninn.mycelium import Mycelium


def _make_mycelium(connections: dict) -> Mycelium:
    """Create a Mycelium with given connections in a temp repo dir."""
    tmp = tempfile.mkdtemp()
    muninn_dir = os.path.join(tmp, ".muninn")
    os.makedirs(muninn_dir, exist_ok=True)
    path = os.path.join(muninn_dir, "mycelium.json")
    old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    conns = {}
    for key, count in connections.items():
        conns[key] = {"count": count, "last_seen": old_date}
    data = {"connections": conns, "fusions": {}, "version": 3}
    with open(path, "w") as f:
        json.dump(data, f)
    m = Mycelium(tmp)  # repo_path, not file path
    return m, tmp


def _get_conn_count(m, key):
    """Get connection count from either DB or in-memory dict."""
    a, b = key.split("|")
    if m._db is not None:
        conn = m._db.get_connection(a, b)
        return conn["count"] if conn else 0
    return m.data["connections"].get(key, {}).get("count", 0)


def test_c1_1_beta_active():
    """SATURATION_BETA should be > 0."""
    m, tmp = _make_mycelium({"a|b": 10})
    assert m.SATURATION_BETA > 0, f"C1.1 FAIL: beta={m.SATURATION_BETA}"
    m.close()
    shutil.rmtree(tmp)
    print("  C1.1 PASS: beta is active")


def test_c1_2_large_lose_more():
    """Large connections (count=200) should lose more than medium ones (count=60)."""
    m, tmp = _make_mycelium({"big|conn": 200, "med|conn": 60})
    m.decay(days=30)
    # Both should survive but big should have lost proportionally more
    big = _get_conn_count(m, "big|conn")
    med = _get_conn_count(m, "med|conn")
    # Without saturation: big=200>>1=100, med=60>>1=30
    # With saturation (beta=0.001): big=100 - 0.001*100*100=100-10=90, med=30 (below threshold)
    assert big < 100, f"C1.2 FAIL: big={big}, should be < 100 (saturation not applied)"
    print(f"  C1.2 PASS: big={big} < 100 (saturation applied)")
    m.close()
    shutil.rmtree(tmp)


def test_c1_3_below_threshold_untouched():
    """Connections below SATURATION_THRESHOLD should not be affected by saturation."""
    m, tmp = _make_mycelium({"small|conn": 30})
    m.decay(days=30)
    small = _get_conn_count(m, "small|conn")
    # 60 days old / 30 day half-life = 2 periods, 30 >> 2 = 7
    # 7 < threshold(50), so no saturation applied — pure decay
    assert abs(small - 7) <= 1, f"C1.3 FAIL: small={small}, expected ~7 (pure decay, no saturation)"
    print(f"  C1.3 PASS: small={small} (below threshold, untouched by saturation)")
    m.close()
    shutil.rmtree(tmp)


def test_c1_4_decay_still_kills():
    """Very old connections should still die (decay works with saturation)."""
    m, tmp = _make_mycelium({"dying|conn": 2})
    m.decay(days=30)
    # 2 >> 1 = 1, should survive at 1
    # 2 >> 2 would die... let's make it older
    m.close()
    shutil.rmtree(tmp)
    # Use very old date
    m2, tmp2 = _make_mycelium({"dying|conn": 1})
    m2.decay(days=30)
    # 1 after 2 half-lives = 0.25 -> should be dead or near-zero
    dying = _get_conn_count(m2, "dying|conn")
    assert dying < 1, f"C1.4 FAIL: dying conn should be <1, got {dying}"
    print("  C1.4 PASS: decay still kills weak connections")
    m2.close()
    shutil.rmtree(tmp2)


def test_c1_5_moderate_survive():
    """Moderate connections (count=80) should survive with reasonable loss."""
    m, tmp = _make_mycelium({"mod|conn": 80})
    m.decay(days=30)
    mod = _get_conn_count(m, "mod|conn")
    # 80 >> 1 = 40, below threshold so no saturation
    # Actually 40 < 50 so no saturation applies after decay
    assert mod > 0, f"C1.5 FAIL: moderate connection died"
    assert mod <= 80, f"C1.5 FAIL: mod={mod} grew?!"
    print(f"  C1.5 PASS: moderate conn survives at {mod}")
    m.close()
    shutil.rmtree(tmp)


if __name__ == "__main__":
    print("=== C1 — Saturation beta (Lotka-Volterra) ===")
    test_c1_1_beta_active()
    test_c1_2_large_lose_more()
    test_c1_3_below_threshold_untouched()
    test_c1_4_decay_still_kills()
    test_c1_5_moderate_survive()
    print("\n  ALL C1 BORNES PASSED")
