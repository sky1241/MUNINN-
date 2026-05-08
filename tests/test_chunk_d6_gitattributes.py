"""CHUNK D6 — .gitattributes routes future binary commits through LFS."""
import re
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
GA = REPO / ".gitattributes"


def test_gitattributes_exists():
    assert GA.exists(), ".gitattributes missing — see CHUNK D6"


def test_png_routed_to_lfs():
    src = GA.read_text()
    assert re.search(r"\*\.png\s+.*filter=lfs", src), (
        "*.png must be routed through LFS in .gitattributes"
    )


def test_db_routed_to_lfs():
    """.db files are also large binary — must route to LFS."""
    src = GA.read_text()
    assert re.search(r"\*\.db\s+.*filter=lfs", src)


def test_python_files_text_with_lf_eol():
    src = GA.read_text()
    assert re.search(r"\*\.py\s+text", src)
    assert "eol=lf" in src


def test_constraints_txt_marked_generated():
    src = GA.read_text()
    assert "constraints.txt" in src
    assert "linguist-generated" in src
