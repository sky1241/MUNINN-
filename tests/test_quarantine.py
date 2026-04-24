"""Tests for Cube Quarantine — record corrupted blocks before healing."""
import json
import os
import sys
import tempfile
import threading
import hashlib
import pytest

from cube import Cube, record_quarantine


@pytest.fixture
def quarantine_file():
    """Create a temporary quarantine JSONL file path."""
    tmp = tempfile.NamedTemporaryFile(suffix=".jsonl", delete=False, dir=tempfile.gettempdir())
    tmp.close()
    os.unlink(tmp.name)  # record_quarantine creates it
    yield tmp.name
    if os.path.exists(tmp.name):
        os.unlink(tmp.name)


def _make_cube(content="def hello(): pass", file_origin="src/main.py",
               line_start=1, line_end=5):
    """Create a test Cube with a mismatched sha256 (simulates corruption)."""
    return Cube(
        id=f"{file_origin}:L{line_start}-L{line_end}:level0",
        content=content,
        sha256="aaaa_expected_hash_before_corruption",  # original hash != current content
        file_origin=file_origin,
        line_start=line_start,
        line_end=line_end,
        level=0,
        token_count=10,
    )


def test_record_quarantine_creates_jsonl(quarantine_file):
    """record_quarantine() creates the JSONL file with one entry."""
    cube = _make_cube()
    entry = record_quarantine(quarantine_file, cube, "def hello(): pass  # rebuilt", False, 0.15)
    assert os.path.exists(quarantine_file)
    with open(quarantine_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert len(lines) == 1
    data = json.loads(lines[0])
    assert data['cube_id'] == cube.id
    assert data['file_origin'] == 'src/main.py'
    assert data['ncd_score'] == 0.15
    assert entry == data


def test_corrupted_content_saved_before_reconstruction(quarantine_file):
    """The corrupted content is saved, not the reconstruction."""
    corrupted = "import evil; evil.run()"
    reconstructed = "def hello(): pass"
    cube = _make_cube(content=corrupted)
    record_quarantine(quarantine_file, cube, reconstructed, False, 0.25)

    with open(quarantine_file, 'r', encoding='utf-8') as f:
        data = json.loads(f.readline())
    assert data['corrupted_content'] == corrupted
    assert data['reconstructed_content'] == reconstructed


def test_hashes_differ_in_entry(quarantine_file):
    """expected_sha256 and found_sha256 are different (corruption detected)."""
    cube = _make_cube(content="MODIFIED CODE")
    record_quarantine(quarantine_file, cube, "original code", False, 0.2)

    with open(quarantine_file, 'r', encoding='utf-8') as f:
        data = json.loads(f.readline())
    assert data['expected_sha256'] == "aaaa_expected_hash_before_corruption"
    found = hashlib.sha256("MODIFIED CODE".encode()).hexdigest()
    assert data['found_sha256'] == found
    assert data['expected_sha256'] != data['found_sha256']


def test_thread_safe_concurrent_writes(quarantine_file):
    """100 concurrent writes don't corrupt the JSONL file."""
    cube = _make_cube()
    errors = []

    def write_entry(i):
        try:
            record_quarantine(quarantine_file, cube, f"rebuilt_{i}", False, 0.1 + i * 0.001)
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=write_entry, args=(i,)) for i in range(100)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    with open(quarantine_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert len(lines) == 100
    # Every line is valid JSON
    for line in lines:
        data = json.loads(line)
        assert 'cube_id' in data


def test_jsonl_parseable_after_multiple_entries(quarantine_file):
    """File remains valid JSONL after N sequential entries."""
    for i in range(20):
        cube = _make_cube(content=f"code_v{i}", file_origin=f"file_{i}.py",
                          line_start=i * 10, line_end=i * 10 + 5)
        record_quarantine(quarantine_file, cube, f"rebuilt_v{i}", False, 0.1 * (i + 1))

    with open(quarantine_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    assert len(lines) == 20
    entries = [json.loads(line) for line in lines]
    # Verify all entries have unique cube_ids
    ids = [e['cube_id'] for e in entries]
    assert len(set(ids)) == 20
    # Verify chronological order (timestamps increasing)
    timestamps = [e['timestamp'] for e in entries]
    assert timestamps == sorted(timestamps)
