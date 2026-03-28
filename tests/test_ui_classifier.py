"""Tests for B-UI-09: Auto-classification (pure logic)."""

import pytest
import json
from pathlib import Path


def test_classify_empty_scan():
    """Empty scan returns a valid family."""
    from muninn.ui.classifier import classify_repo, FAMILIES
    result = classify_repo({"nodes": []})
    assert result["family"] in FAMILIES


def test_classify_trusts_existing_family():
    """If scan already has family, trust it."""
    from muninn.ui.classifier import classify_repo
    result = classify_repo({"family": "palmier", "nodes": []})
    assert result["family"] == "palmier"


def test_extract_metrics():
    """Metrics are computed from scan nodes."""
    from muninn.ui.classifier import extract_metrics
    scan = {
        "nodes": [
            {"id": "a", "level": "R", "depth": 0, "depends": ["b", "c"]},
            {"id": "b", "level": "F", "depth": 1, "depends": ["c"]},
            {"id": "c", "level": "I", "depth": 2, "depends": []},
        ]
    }
    m = extract_metrics(scan)
    assert m.concentration > 0
    assert m.depth > 0
    assert m.breadth > 0
    assert m.dispersion > 0


def test_classify_real_scans():
    """Classify real scans and check they all return valid families."""
    from muninn.ui.classifier import classify_scan_file, FAMILIES
    from muninn.ui import _SCANS_DIR
    scan_files = list(_SCANS_DIR.glob("*.json"))
    assert len(scan_files) > 0

    for sf in scan_files:
        result = classify_scan_file(sf)
        assert result["family"] in FAMILIES, f"{sf.name}: invalid family {result['family']}"
        assert "scores" in result
        assert "metrics" in result


def test_classify_infernal_wheel():
    """infernal-wheel scan classifies to feuillu (pre-classified in scan)."""
    from muninn.ui.classifier import classify_scan_file
    from muninn.ui import _SCANS_DIR
    sf = _SCANS_DIR / "infernal-wheel.json"
    if sf.exists():
        result = classify_scan_file(sf)
        assert result["family"] == "feuillu"


def test_classify_yggdrasil():
    """yggdrasil-engine scan classifies to conifere (pre-classified in scan)."""
    from muninn.ui.classifier import classify_scan_file
    from muninn.ui import _SCANS_DIR
    sf = _SCANS_DIR / "yggdrasil-engine.json"
    if sf.exists():
        result = classify_scan_file(sf)
        assert result["family"] == "conifere"


def test_metrics_have_correct_range():
    """All metrics are in [0, 1]."""
    from muninn.ui.classifier import extract_metrics
    scan = {
        "nodes": [
            {"id": str(i), "level": "F", "depth": i, "depends": [str(i-1)] if i > 0 else []}
            for i in range(20)
        ]
    }
    m = extract_metrics(scan)
    for field in ["concentration", "depth", "breadth", "dispersion", "external_deps"]:
        val = getattr(m, field)
        assert 0.0 <= val <= 1.0, f"{field}={val} out of [0,1]"
