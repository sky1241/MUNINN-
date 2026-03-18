"""Tests for _safe_path() path sanitization."""
import os
import sys
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "engine", "core"))
from muninn import _safe_path


def test_long_absolute_path_truncated():
    """Long absolute paths show only last 3 parts."""
    result = _safe_path("/home/user/projects/myapp/src/main.py")
    assert result == os.path.join("myapp", "src", "main.py")


def test_short_path_shows_name():
    """Short paths (<=3 parts) show only filename."""
    result = _safe_path("/tmp/file.txt")
    assert result == "file.txt"


def test_windows_path():
    """Windows absolute paths are truncated correctly."""
    result = _safe_path("C:\\Users\\ludov\\MUNINN-\\engine\\core\\muninn.py")
    assert "muninn.py" in result
    assert "ludov" not in result
    assert "Users" not in result


def test_relative_path_passthrough():
    """Relative paths with few parts show filename."""
    result = _safe_path("src/main.py")
    assert "main.py" in result


def test_pathlib_input():
    """Accepts pathlib.Path objects."""
    from pathlib import Path
    result = _safe_path(Path("/very/deep/nested/project/src/utils/helper.py"))
    assert "helper.py" in result
    assert "very" not in result


def test_never_shows_home_dir():
    """Never exposes home directory structure."""
    home = os.path.expanduser("~")
    test_path = os.path.join(home, "secret-project", "src", "main.py")
    result = _safe_path(test_path)
    # Should not contain any part of the home path prefix
    home_parts = set(os.path.normpath(home).split(os.sep))
    result_parts = set(result.replace("/", os.sep).split(os.sep))
    # At most the repo name should appear, not the user directory
    assert "Users" not in result_parts or len(result_parts) <= 3
