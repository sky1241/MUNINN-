"""Test M4: Last chunk silently dropped in grow_branches fallback.

Bug: In the no-header fallback path, last chunk with <5 lines
(body.count("\\n") >= 4 fails) is silently dropped.

Fix: Lower threshold to >= 1.
"""
import sys, tempfile, time, json
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent / "engine" / "core"
sys.path.insert(0, str(ENGINE))

def test_m4_last_chunk_preserved():
    """Small last chunk should not be dropped."""
    import muninn

    tmp = Path(tempfile.mkdtemp())
    try:
        tree_dir = tmp / ".muninn" / "tree"
        tree_dir.mkdir(parents=True)

        tree = {
            "version": 2,
            "nodes": {
                "root": {
                    "type": "root", "file": "root.mn", "lines": 3,
                    "max_lines": 100, "tags": ["test"],
                    "temperature": 0.8, "access_count": 1,
                    "last_access": time.strftime("%Y-%m-%d"),
                    "created": time.strftime("%Y-%m-%d"),
                    "children": []
                }
            }
        }
        (tree_dir / "root.mn").write_text("# Root\noverview\n", encoding="utf-8")

        tree_path = tmp / "memory" / "tree.json"
        tree_path.parent.mkdir(parents=True, exist_ok=True)
        with open(tree_path, "w") as f:
            json.dump(tree, f)

        # Create .mn with NO headers but enough lines to trigger fallback
        # chunk_size = max(5, 12 // 4) = 5
        # Chunks: [0:5], [5:10], [10:12] <- last chunk has only 2 lines
        # Use distinct structures to avoid _resolve_contradictions treating them as duplicates
        topics = ["database", "network", "security", "frontend", "backend",
                  "testing", "deploy", "monitoring", "cache", "queue",
                  "logging", "metrics"]
        lines = []
        for i, topic in enumerate(topics):
            lines.append(f"B> {topic} implementation uses config_{i}")
        mn_content = "\n".join(lines)
        mn_path = tmp / ".muninn" / "sessions" / "test.mn"
        mn_path.parent.mkdir(parents=True, exist_ok=True)
        mn_path.write_text(mn_content, encoding="utf-8")

        old_tree_dir = getattr(muninn, 'TREE_DIR', None)
        old_tree_meta = getattr(muninn, 'TREE_META', None)
        muninn.TREE_DIR = tree_dir
        muninn.TREE_META = tree_path

        try:
            created = muninn.grow_branches_from_session(mn_path)
            print(f"  Branches created: {created}")

            # Check all content is present
            all_branch_content = ""
            for f in tree_dir.glob("b*.mn"):
                all_branch_content += f.read_text(encoding="utf-8")

            # The last 2 lines (logging, metrics) should NOT be lost
            has_logging = "logging" in all_branch_content
            has_metrics = "metrics" in all_branch_content
            print(f"  logging preserved: {has_logging}")
            print(f"  metrics preserved: {has_metrics}")

            assert has_logging, "Last chunk content (logging) was silently dropped!"
            assert has_metrics, "Last chunk content (metrics) was silently dropped!"

        finally:
            if old_tree_dir is not None:
                muninn.TREE_DIR = old_tree_dir
            if old_tree_meta is not None:
                muninn.TREE_META = old_tree_meta

        print("  PASS")
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    print("## M4 — Last chunk dropped in grow_branches")
    test_m4_last_chunk_preserved()
