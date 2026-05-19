"""CHUNK C13 (2026-05-19) — shared test helpers.

Three patterns established here for the first time in this repo
(audit 2026-05-19 found none existed) :

- `mock_ollama`     : patch urllib.request.urlopen to fake the
                      Ollama HTTP API (/api/tags + /api/generate).
- `pipeline_trace`  : read .muninn/pipeline_trace.jsonl as a list
                      of event dicts. Use for asserting that a
                      pipeline event fired during a test.
- (perf convention) : tests named `test_perf_*` opt-in via
                      MUNINN_RUN_PERF=1 ; they use plain
                      time.perf_counter() (no pytest-benchmark).
"""
