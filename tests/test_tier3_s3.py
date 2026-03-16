"""TIER 3 S3: Universal degree filter tests."""
import os
import shutil
import tempfile
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from engine.core.mycelium import Mycelium


def make_temp():
    return tempfile.mkdtemp(prefix="tier3_s3_")


def test_s3_1_high_degree_detected():
    """Concept connected to everything is detected as high-degree."""
    d = make_temp()
    try:
        m = Mycelium(d)
        words = [f"concept{i}" for i in range(60)]
        # Organic connections
        for i in range(len(words)):
            for j in range(i + 1, min(i + 4, len(words))):
                m.observe([words[i], words[j]])
        # Noise word connected to all (use English to avoid S4 translation)
        noise = "stuffnoise"
        for w in words:
            m.observe([noise, w])

        high = m._get_high_degree_concepts()
        assert noise in high, f"{noise} should be high-degree, got {high}"
    finally:
        shutil.rmtree(d)


def test_s3_2_retroactive_cleanup():
    """Existing fusions from high-degree concepts are removed retroactively."""
    d = make_temp()
    try:
        m = Mycelium(d)
        words = [f"concept{i}" for i in range(60)]
        for i in range(len(words)):
            for j in range(i + 1, min(i + 4, len(words))):
                m.observe([words[i], words[j]])
        noise = "surtout"
        for w in words:
            for _ in range(6):
                m.observe([noise, w])
        # Force retroactive check (invalidate cached high-degree set first)
        m._high_degree_cache = None
        m._check_fusions()

        # Check fusions in DB if available, else in-memory dict
        if m._db is not None:
            db_fusions = m._db.get_all_fusions()
            noise_fusions = [k for k in db_fusions if noise in k]
        else:
            noise_fusions = [k for k in m.data["fusions"] if noise in k]
        assert len(noise_fusions) == 0, f"Expected 0 noise fusions, got {len(noise_fusions)}"
    finally:
        shutil.rmtree(d)


def test_s3_3_small_graph_no_filter():
    """Small graphs (<50 connections) don't trigger the filter."""
    d = make_temp()
    try:
        m = Mycelium(d)
        for _ in range(6):
            m.observe(["alpha", "beta"])
        high = m._get_high_degree_concepts()
        assert len(high) == 0, "Small graph should not filter anything"
        if m._db is not None:
            db_fusions = m._db.get_all_fusions()
            assert any("alpha" in k and "beta" in k for k in db_fusions), \
                f"alpha|beta fusion missing from DB fusions"
        else:
            assert "alpha|beta" in m.data["fusions"]
    finally:
        shutil.rmtree(d)


def test_s3_4_legit_fusions_preserved():
    """Normal fusions between non-stopword concepts survive the filter."""
    d = make_temp()
    try:
        m = Mycelium(d)
        words = [f"concept{i}" for i in range(60)]
        for i in range(len(words)):
            for j in range(i + 1, min(i + 4, len(words))):
                m.observe([words[i], words[j]])
        # Create a legit pair with enough co-occurrences
        for _ in range(10):
            m.observe(["sqlite", "database"])
        noise = "pouvait"
        for w in words:
            for _ in range(6):
                m.observe([noise, w])
        m._check_fusions()

        if m._db is not None:
            db_fusions = m._db.get_all_fusions()
            assert any("database" in k and "sqlite" in k for k in db_fusions), \
                "Legit fusion should survive in DB"
        else:
            assert "database|sqlite" in m.data["fusions"], "Legit fusion should survive"
    finally:
        shutil.rmtree(d)


def test_s3_5_universal():
    """Filter works on any language (no hardcoded word list)."""
    d = make_temp()
    try:
        m = Mycelium(d)
        words = [f"term{i}" for i in range(60)]
        for i in range(len(words)):
            for j in range(i + 1, min(i + 4, len(words))):
                m.observe([words[i], words[j]])
        # Noise word (untranslatable, tests degree detection not language)
        noise = "xyznoiseword"
        for w in words:
            for _ in range(6):
                m.observe([noise, w])

        high = m._get_high_degree_concepts()
        assert noise in high, f"Any noise word should be detected, got {high}"
    finally:
        shutil.rmtree(d)
