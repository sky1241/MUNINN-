"""
Full L9 compression test across multiple repos.
Measures compression ratio, API cost, truncation.

Usage:
    python test_l9_full.py                          # auto-detect repos
    python test_l9_full.py /path/to/repo1 /path/to/repo2  # explicit repos
    MUNINN_TEST_REPOS=repo1:/path,repo2:/path python test_l9_full.py  # env var
"""
import sys, os, time
from pathlib import Path

# Add engine to path
sys.path.insert(0, str(Path(__file__).parent.parent / "engine" / "core"))
from muninn import compress_file, token_count

# Default: test on this repo only. Override with CLI args or MUNINN_TEST_REPOS env var.
_DEFAULT_REPOS = {
    "muninn": Path(__file__).resolve().parent.parent,
}

def _resolve_repos() -> dict[str, Path]:
    """Resolve repo paths from CLI args, env var, or defaults."""
    # CLI args: paths passed directly
    if len(sys.argv) > 1:
        repos = {}
        for arg in sys.argv[1:]:
            p = Path(arg).resolve()
            repos[p.name] = p
        return repos
    # Env var: MUNINN_TEST_REPOS=name1:/path1,name2:/path2
    env = os.environ.get("MUNINN_TEST_REPOS", "")
    if env:
        repos = {}
        for entry in env.split(","):
            if ":" in entry:
                name, path = entry.split(":", 1)
                repos[name.strip()] = Path(path.strip())
        return repos
    return _DEFAULT_REPOS

REPOS = _resolve_repos()

# Skip auto-generated data, archives, secrets
SKIP_PATTERNS = [
    ".git", "node_modules",
    # HSBC: auto-generated fourier reports (600+ tiny identical files)
    "archives", "outputs", "fourier", "walkforward",
    # Secrets
    "API_LIBRARY", "GUIDE_CLES", "CONFIG_REAL", "QUICK_START",
    # infernal-wheel: chatgpt exports, csv dumps
    "chatgpt_bundle", "gpt_csv", "gpt_export",
]

def find_md_files(repo_path: Path) -> list[Path]:
    files = []
    for f in repo_path.rglob("*.md"):
        path_str = str(f)
        if any(skip in path_str for skip in SKIP_PATTERNS):
            continue
        # Skip tiny files (< 500 chars)
        try:
            if f.stat().st_size < 500:
                continue
        except OSError:
            continue
        files.append(f)
    return sorted(files)

def main():
    total_input_tokens = 0
    total_output_tokens = 0
    total_api_in = 0
    total_api_out = 0
    total_files = 0
    total_truncated = 0
    results_by_repo = {}

    for repo_name, repo_path in REPOS.items():
        if not repo_path.exists():
            print(f"\n[SKIP] {repo_name}: {repo_path} not found")
            continue

        files = find_md_files(repo_path)
        print(f"\n{'='*60}")
        print(f"  {repo_name}: {len(files)} files")
        print(f"{'='*60}")

        repo_results = []
        for f in files:
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                input_tokens = token_count(text)
                if input_tokens < 100:
                    continue

                t0 = time.time()
                compressed = compress_file(f)
                elapsed = time.time() - t0

                output_tokens = token_count(compressed)
                ratio = input_tokens / max(1, output_tokens)

                rel_path = f.relative_to(repo_path)
                print(f"  {rel_path}: {input_tokens} -> {output_tokens} tok (x{ratio:.1f}) [{elapsed:.1f}s]")

                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_files += 1

                repo_results.append({
                    "file": str(rel_path),
                    "input": input_tokens,
                    "output": output_tokens,
                    "ratio": ratio,
                    "time": elapsed,
                })
            except Exception as e:
                print(f"  [ERROR] {f.name}: {e}", file=sys.stderr)

        results_by_repo[repo_name] = repo_results

    # Summary
    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"{'='*60}")
    for repo_name, results in results_by_repo.items():
        if not results:
            continue
        repo_in = sum(r["input"] for r in results)
        repo_out = sum(r["output"] for r in results)
        repo_ratio = repo_in / max(1, repo_out)
        print(f"  {repo_name}: {len(results)} files, {repo_in} -> {repo_out} tok (x{repo_ratio:.1f})")

    overall_ratio = total_input_tokens / max(1, total_output_tokens)
    print(f"\n  TOTAL: {total_files} files, {total_input_tokens} -> {total_output_tokens} tok (x{overall_ratio:.1f})")

    # Cost estimate (Haiku pricing: $0.25/1M input, $1.25/1M output)
    # We can't track API tokens from here easily, but the stderr output shows them
    print(f"\n  Check stderr for per-file API token counts.")
    print(f"  Haiku pricing: $0.25/1M input, $1.25/1M output")

if __name__ == "__main__":
    main()
