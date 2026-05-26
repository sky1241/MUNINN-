"""R3-003 regression: corrupt config.json logs warning, doesn't crash."""
import json
import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "engine" / "core"))


def test_corrupt_config_json_logs_warning(tmp_path, caplog, monkeypatch):
    config_dir = tmp_path / ".muninn"
    config_dir.mkdir()
    config_path = config_dir / "config.json"
    config_path.write_text("{ invalid json !!!", encoding="utf-8")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: tmp_path))

    from muninn_secrets import purge_secrets_db

    with caplog.at_level(logging.WARNING):
        purge_secrets_db(tmp_path)

    assert any("corrupt config.json" in r.message for r in caplog.records), \
        f"expected 'corrupt config.json' warning, got: {[r.message for r in caplog.records]}"
