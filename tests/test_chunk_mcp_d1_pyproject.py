"""
CHUNK MCP D.1 — pyproject.toml finalization for first PyPI 1.0.0 release.

D.1 prepares pyproject.toml + MANIFEST.in for `pip install muninn-memory`
from PyPI. Sky will run D.2 (TestPyPI) and D.3 (PyPI prod) manually
after this chunk.

These tests pin the structure required for a clean 1.0.0 release.
"""
import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = REPO_ROOT / "pyproject.toml"
MANIFEST = REPO_ROOT / "MANIFEST.in"


def _load_pyproject():
    """Parse pyproject.toml using stdlib tomllib (Python 3.11+)."""
    import tomllib
    return tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))


def test_d1_version_is_production_semver():
    """Version must be 1.x.y semver — production stable, no 0.x or alpha/rc.

    D.1 bumped 0.9.2 → 1.0.0 ; subsequent patch releases (1.0.1, 1.0.2, …)
    or minor bumps (1.1.0, 1.2.0, …) keep the production semver.
    Pre-release suffixes like `-rc1`, `a1`, `b2`, `.dev0` are NOT accepted
    here (use a separate test if you want a pre-release branch).
    """
    import re
    data = _load_pyproject()
    version = data["project"]["version"]
    assert re.fullmatch(r"1\.\d+\.\d+", version), (
        f"Expected production semver 1.x.y (no pre-release suffix), got {version!r}"
    )


def test_d1_dev_status_production_stable():
    """1.0.0 = production. Bump classifier from Beta to Production/Stable."""
    data = _load_pyproject()
    classifiers = data["project"]["classifiers"]
    assert "Development Status :: 5 - Production/Stable" in classifiers, (
        "1.0.0 needs Development Status :: 5 - Production/Stable classifier"
    )
    assert "Development Status :: 4 - Beta" not in classifiers, (
        "Beta classifier should be removed for 1.0.0 release"
    )


def test_d1_required_classifiers_present():
    """PyPI needs explicit OS + Python version classifiers.

    PEP 639 (setuptools 77+) deprecates the "License :: ..." classifier
    in favor of `license = "MIT"` SPDX expression in [project] — we use
    the expression form, so no License classifier is allowed here.
    """
    data = _load_pyproject()
    classifiers = data["project"]["classifiers"]
    required = [
        "Operating System :: OS Independent",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ]
    missing = [c for c in required if c not in classifiers]
    assert not missing, f"Missing required classifiers: {missing}"
    # PEP 639: license MUST be declared as SPDX expression, not classifier
    assert data["project"]["license"] == "MIT", (
        "license must be SPDX expression 'MIT' per PEP 639"
    )
    for c in classifiers:
        assert not c.startswith("License ::"), (
            f"PEP 639: remove '{c}' — license = 'MIT' SPDX expression "
            f"replaces License classifiers"
        )


def test_d1_readme_content_type_explicit():
    """Explicit content-type=text/markdown prevents PyPI rendering bugs.

    Accept either:
    - readme = {file = "README.md", content-type = "text/markdown"}
    - readme = "README.md" (implicit, but less safe)
    """
    data = _load_pyproject()
    readme = data["project"]["readme"]
    if isinstance(readme, dict):
        assert readme.get("content-type") == "text/markdown", (
            "When readme is a dict, content-type must be 'text/markdown'"
        )
        assert readme.get("file") == "README.md", (
            "readme.file must be 'README.md'"
        )
    else:
        # String form — must end with .md (PyPI infers markdown)
        assert str(readme).lower().endswith(".md"), (
            "String readme must end with .md for markdown content-type inference"
        )


def test_d1_console_script_targets_importable():
    """Every [project.scripts] entry must resolve to a callable.

    Catches broken shims (e.g. muninn.mycelium:main depending on dev-only
    engine/core/ being on sys.path — would crash at first invocation).

    Special case: muninn-mcp lives behind the [mcp] optional extra. If the
    `mcp` package isn't installed (which is normal in base CI without
    [mcp]), the import raises ImportError("muninn.mcp requires the 'mcp'
    package..."). That's intentional — not a real script breakage. We
    only fail on UNEXPECTED imports errors.
    """
    data = _load_pyproject()
    scripts = data["project"]["scripts"]
    failures = []
    for cmd_name, target in scripts.items():
        module_path, _, attr = target.partition(":")
        try:
            module = importlib.import_module(module_path)
            func = getattr(module, attr, None)
            if not callable(func):
                failures.append(f"{cmd_name}: {target} → {attr} is not callable")
        except ImportError as e:
            # Expected if the [mcp] extra isn't installed — the mcp module
            # itself raises a clear "install with [mcp]" message at import.
            msg = str(e).lower()
            if cmd_name == "muninn-mcp" and "mcp" in msg and (
                "requires" in msg or "no module named 'mcp'" in msg
            ):
                continue  # expected, optional extra not installed
            failures.append(f"{cmd_name}: {target} import failed: {e!r}")
        except Exception as e:
            failures.append(f"{cmd_name}: {target} import failed: {e!r}")
    assert not failures, (
        "Broken console scripts (will crash on `pip install` use):\n  "
        + "\n  ".join(failures)
    )


def test_d1_manifest_in_exists():
    """MANIFEST.in is required to prune muninn/.muninn/ from sdist."""
    assert MANIFEST.exists(), (
        "MANIFEST.in must exist to prune internal data dirs from sdist"
    )


def test_d1_manifest_prunes_internal_data():
    """MANIFEST.in must prune muninn/.muninn (contains edits_log + errors.json)."""
    text = MANIFEST.read_text(encoding="utf-8")
    assert "prune muninn/.muninn" in text or "muninn/.muninn" in text, (
        "MANIFEST.in must prune muninn/.muninn to avoid shipping internal data"
    )


def test_d1_manifest_global_excludes_caches():
    """MANIFEST.in should global-exclude common cache/bytecode files."""
    text = MANIFEST.read_text(encoding="utf-8")
    assert "global-exclude" in text and "__pycache__" in text, (
        "MANIFEST.in should global-exclude __pycache__ + *.pyc"
    )


def test_d1_project_urls_complete():
    """PyPI displays project URLs prominently. Need at minimum Homepage + Issues."""
    data = _load_pyproject()
    urls = data["project"].get("urls", {})
    assert "Homepage" in urls, "[project.urls] must declare Homepage"
    assert "Issues" in urls, "[project.urls] must declare Issues (PyPI displays it)"
