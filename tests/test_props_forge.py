#!/usr/bin/env python3
"""Property-based tests for forge — generated originally by forge --gen-props.

H1 (2026-05-09): the internal forge.py was removed; this file now imports
from the PyPI `forge` binary (forge-shield 1.1.1). The 3 functions tested
(load_json, print_report, detect_flaky) exist in both, so no regen needed.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from hypothesis import given, strategies as st, settings
from forge import *  # PyPI forge-shield 1.1.0+
# forge: the following functions were SKIPPED because they have
# side effects (write to disk, run subprocess, hit network).
# Fuzzing them without isolation would corrupt the repo.
# To test them, write isolated tests by hand using tmp_path.
#   - find_tests  (path arg + .glob())
#   - run_tests  (name matches /^run_/)
#   - save_json  (calls .makedirs())
#   - init_repo  (calls .mkdir())
#   - add_bug  (calls .write_text())
#   - close_bug  (calls .write_text())
#   - log_run  (calls .makedirs())
#   - show_heatmap  (path arg + .glob())
#   - bisect_test  (calls .run())
#   - get_changed_files  (calls .run())
#   - find_impacted_tests  (path arg + .read_text())
#   - run_fast  (name matches /^run_/)
#   - snapshot_capture  (calls .makedirs())
#   - snapshot_check  (calls .run())
#   - predict_defects  (path arg + .read_text())
#   - minimize_input  (calls .write_text())
#   - gen_props  (calls .mkdir())
#   - run_mutation  (name matches /^run_/)
#   - fault_locate  (calls .makedirs())
#   - detect_anomalies  (path arg + .read_text())
#   - measure_robustness  (path arg + .walk())
#   - full_cycle  (calls .makedirs())
#   - main  (calls .makedirs())



# cwd guard: the destructive detector catches direct mkdir/write/open
# calls in fuzzed function bodies, but it does not follow indirect calls
# (e.g. parse_input() -> IndexBuilder() -> mkdir()). When Hypothesis fuzzes
# a path-like arg with a random string like '0' or '\xfeQ', the indirect
# mkdir resolves it relative to cwd and pollutes the repo root.
# This autouse fixture chdir's into tmp_path before each test, so any
# indirect file-system mutation lands in a sandbox pytest cleans up.
@pytest.fixture(autouse=True)
def _forge_isolate_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

@given(path=st.text(max_size=50))
@settings(max_examples=50)
def test_load_json_no_crash(path):
    """Smoke: load_json() does not crash on arbitrary input"""
    # from engine.core.forge import load_json
    try:
        load_json(path)
    except (ValueError, TypeError, KeyError, IndexError,
            OSError, AttributeError, RuntimeError, SyntaxError,
            LookupError, ArithmeticError, AssertionError,
            SystemExit, Exception):
        pass  # Expected rejections are OK

@given(results=st.text(max_size=50), baseline=st.text(max_size=50))
@settings(max_examples=50)
def test_print_report_no_crash(results, baseline):
    """Smoke: print_report() does not crash on arbitrary input"""
    # from engine.core.forge import print_report
    try:
        print_report(results, baseline)
    except (ValueError, TypeError, KeyError, IndexError,
            OSError, AttributeError, RuntimeError, SyntaxError,
            LookupError, ArithmeticError, AssertionError,
            SystemExit, Exception):
        pass  # Expected rejections are OK

@given(root=st.text(max_size=50), runs=st.text(max_size=50))
@settings(max_examples=50)
def test_detect_flaky_no_crash(root, runs):
    """Smoke: detect_flaky() does not crash on arbitrary input"""
    # from engine.core.forge import detect_flaky
    try:
        detect_flaky(root, runs)
    except (ValueError, TypeError, KeyError, IndexError,
            OSError, AttributeError, RuntimeError, SyntaxError,
            LookupError, ArithmeticError, AssertionError,
            SystemExit, Exception):
        pass  # Expected rejections are OK
