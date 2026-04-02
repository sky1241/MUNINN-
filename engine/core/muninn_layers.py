"""Muninn compression layers — L0-L11 pipeline + verify."""

import re
import sys
from pathlib import Path

from tokenizer import count_tokens, token_count


class _ModRef:
    """Lazy reference to muninn module — avoids circular import."""
    def __getattr__(self, name):
        return getattr(sys.modules['muninn'], name)
    def __setattr__(self, name, value):
        setattr(sys.modules['muninn'], name, value)

_m = _ModRef()

__all__ = ['UNIVERSAL_RULES', '_KNOWN_PATTERNS', '_L9_PROMPT', '_L9_SYSTEM', '_NOVEL_PATTERNS', '_TAG_PATTERNS', '_cue_distill', '_extract_rules', '_generate_cue', '_kicomp_filter', '_line_density', '_llm_compress', '_llm_compress_chunk', '_ncd', '_novelty_score', '_resolve_contradictions', '_safe_path', 'compress_file', 'compress_line', 'compress_section', 'decode_line', 'extract_facts', 'get_codebook', 'load_codebook', 'tag_memory_type', 'verify_compression']


# ── COMPRESSION RULES LOADER ────────────────────────────────────
# Two sources of compression rules:
# 1. Universal rules (hardcoded, BPE-native English)
# 2. Mycelium (living codebook, per-repo, grows with usage)

# Universal compression: state words -> short English (BPE-native)
UNIVERSAL_RULES = {
    # French -> English compact (1 token each)
    "COMPLET": "done", "COMPLETE": "done", "COMPLETED": "done", "completed": "done", "complet": "done",
    "VALIDE": "done", "VALIDÉ": "done", "FIXE": "done", "FIXÉ": "done",
    "EN COURS": "wip", "en cours": "wip",
    "ECHOUE": "fail", "ECHOUÉ": "fail", "FAILED": "fail",
    "EN ATTENTE": "todo", "PENDING": "todo",
    "DÉCISION": "decided", "DECISION": "decided",
    # Markdown stripping
    "## ": "", "**": "", "- ": "",
}

# ── L9 PROMPT (single source of truth) ──────────────────────────
# Research-backed design (Chain of Density, anti-summarization framing):
# - "EXTRACT+RESTATE" not "compress" (avoids summarization prior)
# - temperature=0 (factual precision over creative paraphrase)
# - Few-shot example (teaches by showing, not telling)
# - "identify all facts first" (CoD-inspired enumeration before output)
# - stop_reason check (detects silent truncation)
# - max_tokens * 3/4 (pre-compressed text needs more room than raw)
_L9_SYSTEM = (
    "You extract and restate facts for LLM memory. "
    "A future LLM loads your output as its ONLY context. "
    "NEVER add information not in the input. "
    "When unsure whether to keep or drop: KEEP."
)
_L9_PROMPT = (
    "EXTRACT every fact from the input. RESTATE each in minimal tokens.\n"
    "Drop ONLY: filler adverbs, transitions, repetition, greetings, boilerplate.\n\n"
    "KEEP (non-negotiable): numbers+units, names, identifiers, "
    "decisions+WHY, errors+fixes, code signatures.\n"
    "Tables/lists: preserve structure, compress cell text.\n"
    "Prose: 1 fact/line, use -> = | ~ as connectors, ## headers to group.\n\n"
    "EXAMPLE:\n"
    "IN: The dashboard uses a 12px base font with 1.5rem line height. "
    "Charts render at 60fps on devices with more than 256KB cache. "
    "The Garmin API v3.2 provides heart rate data with 95% accuracy at rest.\n"
    "OUT: dashboard: 12px base, 1.5rem line-height | charts 60fps if cache>256KB "
    "| Garmin API v3.2: HR 95% accuracy@rest\n\n"
    "PROCESS: first mentally identify ALL facts/entities, then write output "
    "covering every one. No preamble.\n\n"
)
def load_codebook(repo_path: Path = None) -> dict:
    """Load compression rules: universal + mycelium (if available)."""
    text_rules = dict(UNIVERSAL_RULES)

    # Load mycelium compression rules (living codebook)
    mycelium_rules = {}
    learned_fillers = []
    learned_abbreviations = {}
    if repo_path:
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(repo_path)
            mycelium_rules = m.get_compression_rules()
            learned_fillers = m.get_learned_fillers()
            learned_abbreviations = m.get_learned_abbreviations()
        except (ImportError, Exception) as e:
            if not isinstance(e, ImportError):
                print(f"WARNING: mycelium load failed: {e}", file=sys.stderr)

    return {
        "text_rules": text_rules,
        "mycelium_rules": mycelium_rules,
        "learned_fillers": learned_fillers,
        "learned_abbreviations": learned_abbreviations,
    }

def _safe_path(filepath) -> str:
    """Sanitize path for display — never show absolute paths.

    Shows max 2 parent directories for context without exposing full tree.
    '/home/user/projects/myapp/src/main.py' -> 'myapp/src/main.py'
    """
    p = Path(filepath)
    parts = p.parts
    if len(parts) <= 3:
        return str(p.name)
    return str(Path(*parts[-3:]))


def get_codebook():
    # globals on _m
    if _m._CB is None or _m._CB_REPO != _m._REPO_PATH:
        _m._CB = load_codebook(_m._REPO_PATH)
        _m._CB_REPO = _m._REPO_PATH
    return _m._CB


# ── KICOMP DENSITY FILTER ────────────────────────────────────────

def _line_density(line: str) -> float:
    """Score a line's information density (0.0 = noise, 1.0 = dense fact).

    Heuristic inspired by KIComp (Expert Systems 2025).
    High density: numbers, key=value, identifiers, short lines with data.
    Low density: filler, repetition, generic statements.
    """
    if not line.strip():
        return 0.0

    score = 0.0
    s = line.strip()

    # Headers always kept (structural)
    if s.startswith("===") or s.startswith("#"):
        return 1.0

    # Tagged lines get base score from tag
    tag_scores = {"D>": 0.9, "B>": 0.8, "E>": 0.7, "F>": 0.8, "A>": 0.7}
    for tag, tscore in tag_scores.items():
        if s.startswith(tag):
            score = max(score, tscore)
            break

    # Numbers boost density (facts, metrics, dates)
    num_count = len(re.findall(r'\d+', s))
    score += min(0.3, num_count * 0.1)

    # Key=value patterns are dense
    kv_count = len(re.findall(r'[a-zA-Z]+=\S+', s))
    score += min(0.2, kv_count * 0.1)

    # Short lines with data are denser than long narrative
    if len(s) < 80 and num_count > 0:
        score += 0.1

    # Identifiers (commit hashes, file paths, function names)
    if re.search(r'[a-f0-9]{7,}|[\w/]+\.\w{1,4}|\w+\(\)', s):
        score += 0.1

    # Long lines without numbers = probably narrative filler
    if len(s) > 120 and num_count == 0:
        score = min(score, 0.1)  # M1 fix: CAP (not floor) long narrative

    return min(1.0, score)


def _kicomp_filter(text: str, max_tokens: int) -> str:
    """Drop lowest-density lines until text fits in token budget.

    Preserves structural lines (headers, separators) and high-density facts.
    Based on: KIComp (Expert Systems 2025) — information density scoring.
    V6 fix: uses per-line token estimates instead of re-encoding entire text
    per dropped line (was 35s / 1116 calls, now O(n) single pass).
    """
    total_tokens = token_count(text)
    if total_tokens <= max_tokens:
        return text

    lines = text.split("\n")
    # Estimate tokens per line using len//3 (compressed text has shorter words,
    # so BPE produces more tokens per char than the usual len//4 estimate).
    line_tokens = [max(1, len(line) // 3) for line in lines]

    scored = [(i, line, _line_density(line)) for i, line in enumerate(lines)]

    # Sort by density ascending (lowest first = first to drop)
    droppable = [(i, line, d) for i, line, d in scored
                 if d < 0.9 and not line.strip().startswith("===") and not line.startswith("#")]
    droppable.sort(key=lambda x: x[2])

    # Drop lowest-density lines until estimated tokens fit budget
    # Use 95% target to compensate for len//4 underestimation
    target = int(max_tokens * 0.95)
    dropped = set()
    running_tokens = total_tokens
    for idx, _, _ in droppable:
        if running_tokens <= target:
            break
        dropped.add(idx)
        running_tokens -= line_tokens[idx]

    remaining = [(i, line) for i, line in enumerate(lines) if i not in dropped]
    current = "\n".join(line for _, line in remaining)

    # One final accurate count
    final_tokens = token_count(current)

    # Second pass with accurate per-line token counts if still over budget
    # Raise density threshold to 0.98 — willing to drop more to respect budget
    if final_tokens > max_tokens and remaining:
        remaining_scored = []
        for i, line in remaining:
            d = _line_density(line)
            tag = line.strip()[:2]
            if d < 0.98 and tag not in ("D>", "B>", "F>", "E>", "A>") and not line.strip().startswith("===") and not line.startswith("#"):
                remaining_scored.append((i, line, d, token_count(line)))
        remaining_scored.sort(key=lambda x: x[2])  # lowest density first
        for idx, _, _, ltok in remaining_scored:
            if final_tokens <= max_tokens:
                break
            dropped.add(idx)
            final_tokens -= ltok
        current = "\n".join(line for i, line in enumerate(lines) if i not in dropped)
        final_tokens = token_count(current)

    # Final pass: if still over, trim lines from the end (least important position)
    if final_tokens > max_tokens:
        final_lines = current.split("\n")
        while len(final_lines) > 1 and final_tokens > max_tokens:
            removed = final_lines.pop()
            final_tokens -= token_count(removed)
        current = "\n".join(final_lines)
        final_tokens = token_count(current)

    if dropped:
        print(f"  KIComp: dropped {len(dropped)} low-density lines "
              f"(budget: {max_tokens} tokens, final: {final_tokens} tokens)", file=sys.stderr)

    return current


# ── NCD SIMILARITY ───────────────────────────────────────────────

def _ncd(a: str, b: str) -> float:
    """Normalized Compression Distance — semantic similarity via zlib.

    NCD(a,b) = (C(a+b) - min(C(a), C(b))) / max(C(a), C(b))
    Returns 0.0 (identical) to 1.0 (completely different).
    Based on: Cilibrasi & Vitanyi 2005.
    """
    if a == b:
        return 0.0
    if not a or not b:
        return 1.0
    import zlib
    ab = a.encode("utf-8")
    bb = b.encode("utf-8")
    ca = len(zlib.compress(ab))
    cb = len(zlib.compress(bb))
    cab = len(zlib.compress(ab + bb))
    return (cab - min(ca, cb)) / max(ca, cb) if max(ca, cb) > 0 else 0.0


def compress_line(line) -> str:
    """Compress a single line using all compression layers.

    Layer 1: Markdown stripping
    Layer 2: Filler word removal (articles, prepositions, connectors)
    Layer 3: Common phrase collapsing
    Layer 4: Number compression (150,000 -> 150K)
    Layer 5: Universal text rules
    Layer 6: Mycelium fusion stripping
    Layer 7: Key-value extraction from natural language
    """
    if not line:
        return line or ""
    if not isinstance(line, str):
        line = str(line) if line is not None else ""
    # P14/P25: tagged lines (D>/B>/F>/E>/A>) are already classified — skip compression
    if len(line) >= 2 and line[:2] in ("B>", "E>", "F>", "D>", "A>"):
        return line
    cb = get_codebook()
    result = line

    # L1: Strip markdown formatting
    result = re.sub(r"^#{1,4}\s+", "", result)
    result = result.replace("**", "")
    result = re.sub(r"^-\s+", "", result)
    result = result.replace("`", "")

    # L2 pre-pass: protect fillers that carry meaning between numbers/math
    # "2 of the 5" must not become "2 5", "log of n" must stay
    _PROTECTED = re.findall(
        r'\d+\s+(?:of|to|in|at|by|for)\s+(?:the\s+)?\d+',
        result, flags=re.IGNORECASE
    )
    _MATH_PROTECTED = re.findall(
        r'(?:log|sum|product|ratio|percentage)\s+of\b',
        result, flags=re.IGNORECASE
    )
    # P24: Protect causal connectors — "because X" carries the WHY
    _CAUSAL_PROTECTED = re.findall(
        r'(?:because|since|therefore|so that|due to|parce que?|car|donc|puisque)\s+\S+',
        result, flags=re.IGNORECASE
    )
    # Replace protected spans with placeholders
    _placeholders = {}
    for i, span in enumerate(_PROTECTED + _MATH_PROTECTED + _CAUSAL_PROTECTED):
        placeholder = f"__PROT{i}__"
        _placeholders[placeholder] = span
        result = result.replace(span, placeholder, 1)

    # X11: L3 BEFORE L2 — phrase collapsing must run before filler removal,
    # otherwise L2 strips words like "in", "to", "of" that are part of L3 patterns
    # (e.g. "in order to" -> "to" becomes broken if "in" and "to" are removed first)

    # L3: Common phrase collapsing
    _PHRASES = [
        (r"take\s+into\s+account", "consider"),
        (r"take\s+account", "consider"),
        (r"in\s+order\s+to", "to"),
        (r"as\s+a\s+result\s+of", "from"),
        (r"not properly closing", "not closing"),
        (r"was not", "!"),
        (r"instead of growing unboundedly", "stable"),
        (r"per frame", "/frame"),
        (r"per time frame", "/frame"),
        (r"per commit", "/commit"),
        (r"per second", "/s"),
        (r"one per", "1/"),
        (r"runs on", "on"),
        (r"well under", "<"),
        (r"no accuracy loss", "acc=same"),
        (r"all passing", "pass"),
        (r"not found", "missing"),
        (r"not properly", "badly"),
        (r"Fixed by", "fix:"),
        (r"Optimized", "opt"),
        (r"Implemented", "impl"),
        (r"Decided to use", "use"),
        (r"Considering", "maybe"),
        (r"Migrated", "moved"),
        (r"Total parameters", "params"),
        (r"Total test count", "tests"),
        (r"Test coverage", "cov"),
        (r"Inference time", "infer"),
        (r"Total latency", "latency"),
        (r"Memory usage", "mem"),
        (r"Target latency", "target"),
        (r"each recording", "each"),
        (r"continuous use", "runtime"),
        (r"overall", "avg"),
        (r"critical path", "crit"),
    ]
    for pattern, replacement in _PHRASES:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

    # L3b: Learned abbreviations from mycelium (strong fusions -> shorter form)
    _result_lower = result.lower()
    for long_form, short_form in cb.get("learned_abbreviations", {}).items():
        if long_form in _result_lower:
            result = re.sub(rf"\b{re.escape(long_form)}\b", short_form, result,
                          count=1, flags=re.IGNORECASE)
            _result_lower = result.lower()

    # L2: Filler word removal — these carry zero information in memory notes
    _FILLER = [
        # Articles & determiners (case-insensitive safe ones)
        r"\bthe\b",
        r"\ble\b", r"\bla\b", r"\bles\b", r"\bun\b", r"\bune\b", r"\bdes\b",
        # Connectors & filler verbs
        r"\bwas\b", r"\bwere\b", r"\bis\b", r"\bare\b", r"\bbeen\b",
        r"\bwhich\b", r"\bthat\b", r"\bthis\b",
        r"\bby\b", r"\bof\b", r"\bfor\b", r"\bin\b", r"\bon\b", r"\bat\b",
        r"\bto\b", r"\bwith\b", r"\bfrom\b", r"\binto\b",
        r"\band\b", r"\bbut\b", r"\bor\b",
        # Verbose phrases (longest first)
        r"\bapproximately\b", r"\bcurrently\b", r"\bproperly\b",
        r"\bcorresponds to\b", r"\binstead of\b",
        r"\bbased on\b", r"\bin order to\b",
        r"\bnow\b", r"\balso\b", r"\bjust\b", r"\bstill\b",
        # Common verbal tics
        r"\bbasically\b", r"\bactually\b", r"\bessentially\b",
        r"\bobviously\b", r"\bsimply\b", r"\breally\b", r"\bprobably\b",
        # French fillers
        r"\best\b", r"\bqui\b", r"\bque\b", r"\bdans\b", r"\bavec\b",
        r"\bpour\b", r"\bplus\b", r"\btout\b", r"\bmais\b",
    ]
    for filler in _FILLER:
        result = re.sub(filler, "", result, flags=re.IGNORECASE)
    # "a"/"an": case-sensitive, only as English articles (before a word, not standalone "a" in math/code)
    result = re.sub(r"\ba (?=[a-z])", "", result)
    result = re.sub(r"\ban (?=[a-z])", "", result)

    # L2b: Learned fillers from mycelium (words in 10+ connections, never fused)
    for filler_word in cb.get("learned_fillers", []):
        result = re.sub(rf"\b{re.escape(filler_word)}\b", "", result, flags=re.IGNORECASE)

    # L2 post-pass: restore protected spans
    for placeholder, original_span in _placeholders.items():
        result = result.replace(placeholder, original_span)

    # L4: Compress large numbers
    def shorten_number(m):
        n = int(m.group(0).replace(",", ""))
        if n >= 1_000_000:
            return f"{n / 1_000_000:.0f}M" if n % 1_000_000 == 0 else f"{n / 1_000_000:.1f}M"
        if n >= 1_000:
            return f"{n / 1_000:.0f}K" if n % 1_000 == 0 else f"{n / 1_000:.1f}K"
        return str(n)

    result = re.sub(r"\d{1,3}(?:,\d{3})+", shorten_number, result)

    # L5: Apply text rules (longest first to avoid partial matches)
    # Use word-boundary regex to prevent substring corruption
    # (e.g. "completed" must NOT become "doneed" from rule "complete"->"done")
    for pattern in sorted(cb["text_rules"].keys(), key=len, reverse=True):
        escaped = re.escape(pattern)
        # Only use \b around patterns that start/end with word characters
        if not pattern:
            continue
        prefix = r'\b' if re.match(r'\w', pattern[0]) else ''
        suffix = r'\b' if re.match(r'\w', pattern[-1]) else ''
        result = re.sub(rf'{prefix}{escaped}{suffix}', cb["text_rules"][pattern], result)

    # L6: Mycelium-aware compression: strong fusions = predictable pairs.
    # Only drop shorter concept if it appears exactly once AND near the other.
    strong_fusions = {k: v for k, v in cb["mycelium_rules"].items()
                      if v.get("strength", 0) >= 10}
    result_lower = result.lower()
    for key, rule in strong_fusions.items():
        concepts = rule.get("concepts", [])
        if len(concepts) != 2:
            continue
        a, b = concepts
        if a in result_lower and b in result_lower:
            drop = b if len(b) <= len(a) else a
            keep = a if drop == b else b
            # Only drop if the concept appears exactly once (not used independently)
            drop_count = len(re.findall(rf'\b{re.escape(drop)}\b', result_lower))
            if drop_count == 1:
                # Only drop if within 5 words of the kept concept
                pattern = rf'\b{re.escape(keep)}\b.{{0,40}}\b{re.escape(drop)}\b|\b{re.escape(drop)}\b.{{0,40}}\b{re.escape(keep)}\b'
                if re.search(pattern, result_lower):
                    result = re.sub(rf'\s+\b{re.escape(drop)}\b', '', result,
                                  count=1, flags=re.IGNORECASE)
                    result_lower = result.lower()

    # L7: Extract key=value patterns from natural language
    # "accuracy: 94.2%" -> "acc=94.2%"
    # "takes 45ms" -> "45ms"
    result = re.sub(r"[Aa]ccuracy\s*[:=]?\s*", "acc=", result)
    result = re.sub(r"[Ll]atency\s*[:=]?\s*", "lat=", result)
    result = re.sub(r"[Cc]overage\s*[:=]?\s*", "cov=", result)
    result = re.sub(r"takes\s+", "", result)
    result = re.sub(r"around\s+", "~", result)
    result = re.sub(r"approximately\s+", "~", result)
    result = re.sub(r"stays stable\s+", "stable ", result)

    # Clean up: collapse multiple spaces, strip
    result = re.sub(r"\s{2,}", " ", result).strip()
    # Remove trailing/leading punctuation artifacts
    result = re.sub(r"^\s*[,;]\s*", "", result)
    result = re.sub(r"\s+[,;]\s*$", "", result)

    return result


def extract_facts(text: str) -> list[str]:
    """Extract key facts from natural language text.

    Pulls out: numbers+units, percentages, key=value pairs, commits,
    dates, filenames, technical terms. Drops narrative filler.
    """
    if not text:
        return []
    facts = []

    # Numbers with units (45ms, 2.3 TB, 4096 samples, etc.)
    for m in re.finditer(r'(\d+[\d.,]*)\s*(ms|MB|GB|TB|Hz|fps|GPUs?|hours?|minutes?|seconds?|samples?|bins?|frames?|parameters?|million|K|M)\b', text):
        val, unit = m.group(1), m.group(2)
        # Shorten units
        unit_map = {"hours": "h", "hour": "h", "minutes": "min", "seconds": "s",
                    "second": "s", "samples": "smp", "sample": "smp",
                    "parameters": "params", "million": "M", "GPUs": "GPU",
                    "bins": "bins", "frames": "frames"}
        unit = unit_map.get(unit, unit)
        facts.append(f"{val}{unit}")

    # Percentages (94.2%, 87%)
    for m in re.finditer(r'(\d+\.?\d*)\s*%', text):
        facts.append(f"{m.group(1)}%")

    # key: value patterns (only if value wasn't already captured as number+unit)
    existing_nums = {f.split("=")[-1].rstrip("%") for f in facts}
    for m in re.finditer(r'([A-Za-z][\w\s]*?):\s*(\d[\d.,]*\s*\w+)', text):
        key = m.group(1).strip().lower().replace(" ", "_")
        val = m.group(2).strip()
        # Skip if the numeric part is already in facts
        num_part = re.match(r'[\d.,]+', val)
        if num_part and any(num_part.group(0) in f for f in facts):
            continue
        if len(key) <= 20 and key not in ("the", "a", "an", "to", "in", "on"):
            facts.append(f"{key}={val}")

    # x-ratios (x4.1, x9.6, x143)
    for m in re.finditer(r'\bx(\d+\.?\d*)\b', text):
        facts.append(f"x{m.group(1)}")

    # Dates (2026-03-11, 2025/12/01)
    for m in re.finditer(r'\b(\d{4}[-/]\d{2}[-/]\d{2})\b', text):
        facts.append(m.group(1))

    # Version numbers (v0.9.1, Python 3.13) — skip if preceded by $ (dollar amount)
    for m in re.finditer(r'\bv?(\d+\.\d+(?:\.\d+)?)\b', text):
        val = m.group(1)
        if val not in [f.rstrip('%') for f in facts]:  # avoid dupes with percentages
            if m.start() > 0 and text[m.start() - 1] == '$':
                continue  # skip dollar amounts — captured below
            facts.append(f"v{val}" if text[m.start()] == 'v' else val)

    # Dollar costs ($0.21, $1.50)
    for m in re.finditer(r'\$(\d+\.?\d*)', text):
        facts.append(f"${m.group(1)}")

    # Commit hashes (require at least one letter to avoid pure-digit false positives)
    for m in re.finditer(r'\b([a-f0-9]{7,12})\b', text):
        val = m.group(1)
        if re.search(r'[a-f]', val):  # must contain a hex letter, not just digits
            facts.append(val)

    # Filenames and paths
    for m in re.finditer(r'\b[\w/]+\.(?:py|rs|ts|js|json|yaml|yml|toml|md|gz|npz|npy)\b', text):
        facts.append(m.group(0))

    # Cohen's d
    for m in re.finditer(r"Cohen's\s+d\s*=\s*([\d.]+)", text):
        facts.append(f"d={m.group(1)}")

    # p-values
    for m in re.finditer(r"p\s*=\s*([\d.e-]+)", text):
        facts.append(f"p={m.group(1)}")

    return list(dict.fromkeys(facts))  # deduplicate preserving order


# ── MEMORY TYPE TAGGER ─────────────────────────────────────────
# Tags compressed lines with their memory type for prioritized retrieval.
# D> = decision, B> = bug/fix, F> = fact/metric, A> = architecture, E> = error

_TAG_PATTERNS = [
    ("B>", re.compile(
        r"(?i)(bug|fix|patch|crash|broke|broken|repair|hotfix|regression|"
        r"workaround|corrig[eé]|r[eé]par[eé])"
    )),
    ("E>", re.compile(
        r"(?i)(error|exception|traceback|failed|failure|TypeError|ValueError|"
        r"KeyError|IndexError|ImportError|AttributeError|SyntaxError|"
        r"FileNotFoundError|RuntimeError|erreur|echou[eé])"
    )),
    ("F>", re.compile(
        r"(?i)(x\d+\.?\d*|ratio|benchmark|token|percent|%|\d+\.\d+[sx]|"
        r"mesur[eé]|metric|gain|score|accuracy|retention|cost\s*[:=]|"
        r"latency|throughput|p\d{2,3}|req/s|\d+ms|\d+s\b|perf)"
    )),
    ("D>", re.compile(
        r"(?i)(decid|decision|chose|pivot|switch|adopt|drop|keep|use instead|"
        r"go with|won't|will use|prefer|opted|choix|on garde|on vire|on prend)"
    )),
    ("A>", re.compile(
        r"(?i)(architect|structure|design|pattern|pipeline|module|"
        r"refactor|abstract|interface|class\s+\w|inherit|compos)"
    )),
]


def tag_memory_type(line: str) -> str:
    """Classify a compressed line by memory type. Returns tagged line or original."""
    if not line:
        return line or ""
    # Don't double-tag
    if len(line) >= 2 and line[:2] in ("B>", "E>", "F>", "D>", "A>"):
        return line
    for tag, pattern in _TAG_PATTERNS:
        if pattern.search(line):
            return f"{tag}{line}"
    return line


def compress_section(header: str, lines: list[str]) -> str:
    cb = get_codebook()
    text_rules = cb["text_rules"]

    # Extract state — uses universal symbols only
    state = "?"
    state_words = {
        "COMPLET": "✓", "COMPLETE": "✓", "DONE": "✓",
        "VALIDE": "✓", "VALIDÉ": "✓", "FIXE": "✓", "FIXÉ": "✓",
        "EN COURS": "⟳", "IN PROGRESS": "⟳",
        "PRÊT": "◉", "READY": "◉",
        "FAILED": "✗", "ECHOUE": "✗", "ECHOUÉ": "✗",
    }
    for pattern, code in sorted(state_words.items(), key=lambda x: len(x[0]), reverse=True):
        if pattern in header.upper():
            state = code
            # Strip state word with dash prefix (e.g. "— COMPLETE")
            header = re.sub(
                rf"\s*[—\-]+\s*{re.escape(pattern)}", "",
                header, flags=re.IGNORECASE
            )
            # Also strip state word at end without dash (e.g. "x4.5 VALIDE")
            header = re.sub(
                rf"\s+{re.escape(pattern)}\s*$", "",
                header, flags=re.IGNORECASE
            )
            break

    # Extract session/version markers
    session = ""
    m = re.search(r"\(session\s+(\d+)", header, re.IGNORECASE)
    if m:
        session = f"@s{m.group(1)}"
        header = re.sub(r"\s*\(session\s+\d+.*?\)", "", header, flags=re.IGNORECASE)

    # Extract date from header
    dm = re.search(r"(\d{4}-\d{2}-\d{2})", header)
    if dm:
        session = f"@{dm.group(1)}" if not session else session
        header = re.sub(r"\s*[—\-]+\s*\d{4}-\d{2}-\d{2}", "", header)

    header = re.sub(r"^#+\s*", "", header).strip()

    for pattern in sorted(text_rules.keys(), key=len, reverse=True):
        header = re.sub(rf'\b{re.escape(pattern)}\b', text_rules[pattern], header)

    compressed_header = f"{state}{header}{session}"

    # Detect sub-sections (### headers within the section)
    subsections = []
    current_sub_header = None
    current_sub_lines = []

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("### ") or stripped.startswith("## "):
            if current_sub_header:
                subsections.append((current_sub_header, current_sub_lines))
            current_sub_header = re.sub(r"^#{1,4}\s+", "", stripped)
            current_sub_lines = []
        else:
            current_sub_lines.append(stripped)

    if current_sub_header:
        subsections.append((current_sub_header, current_sub_lines))

    # If we have subsections, compress each one as a fact-line
    if subsections:
        result = compressed_header + ":"
        for sub_h, sub_lines in subsections:
            sub_text = "\n".join(sub_lines)
            facts = extract_facts(sub_text)

            # Compress sub-header
            sub_h_compressed = compress_line(sub_h)

            # Detect state in sub-header
            sub_state = ""
            for pattern, code in state_words.items():
                if pattern in sub_h.upper():
                    sub_state = code
                    sub_h_compressed = re.sub(
                        rf"\s*[—\-]+\s*{re.escape(pattern)}", "",
                        sub_h_compressed, flags=re.IGNORECASE
                    )
                    break

            if facts:
                fact_str = "|".join(facts[:8])  # cap at 8 facts per subsection
                result += f"\n  {sub_state}{sub_h_compressed}:{fact_str}"
            else:
                # Fall back to line-by-line compression
                compressed_lines = [compress_line(l) for l in sub_lines if l.strip()]
                compressed_lines = [l for l in compressed_lines if l]
                if compressed_lines:
                    result += f"\n  {sub_state}{sub_h_compressed}:{compressed_lines[0]}"
                    for cl in compressed_lines[1:3]:  # max 3 detail lines
                        result += f"\n    {cl}"
        return result

    # No subsections: compress line by line with fact extraction
    body = []
    for line in lines:
        if not line.strip():
            continue
        cl = compress_line(line)
        if cl:
            body.append(cl)

    if sum(len(b) for b in body) < 120:
        return f"{compressed_header}:{('|'.join(body))}"
    else:
        result = compressed_header + ":"
        for b in body:
            result += f"\n  {b}"
        return result


def _resolve_contradictions(text: str) -> str:
    """Resolve numeric contradictions — last-writer-wins.

    When the same entity has different numeric values at different points,
    keep only the LATEST value. Prevents stale facts from persisting.
    Based on: Stanford NLP 2008 (Finding Contradictions in Text).

    Example: "ratio x7.4" then later "ratio x4.1" → keeps only "ratio x4.1"
    """
    if not text:
        return text or ""
    lines = text.split("\n")
    # Strategy: two lines "contradict" if they are identical EXCEPT for the numbers.
    # Replace all numbers with a placeholder, then group by this "skeleton".
    # Within each group, keep only the LAST line (most recent = most correct).
    num_val = re.compile(
        r'[x×]?\d+(?:[.,]\d+)?(?:%|K|M|ms|s|px|x|GB|MB|KB|tokens?|lines?|tok)?'
    )

    skeleton_last = {}  # skeleton -> (line_text, line_index)
    contradictions = {}  # skeleton -> set of line indices to remove
    for i, line in enumerate(lines):
        if line.startswith("#") or line.startswith("?FACTS") or not line.strip():
            continue
        # Build skeleton: replace all numbers with placeholder, then lowercase
        skel = num_val.sub("_NUM_", line).strip().lower()
        skel = re.sub(r'\s+', ' ', skel)
        # Only track lines that HAVE numbers (no numbers = no contradiction possible)
        if "_num_" not in skel:
            continue
        if skel in skeleton_last:
            old_text, old_idx = skeleton_last[skel]
            if old_text != line:
                # Guard: numbered list items (1. X, 2. X) are NOT contradictions.
                # Detect: skeleton starts with _NUM_ + list marker, lines are near-consecutive.
                is_list_item = (
                    (re.match(r'^_num_[\.\)]\s', skel)       # numbered: 1. X, 2) X
                     or re.match(r'^[-*]\s', line.strip()))   # bullet: - X, * X
                    and abs(i - old_idx) <= 5  # within 5 lines of each other
                )
                if not is_list_item:
                    # Same structure, different numbers = contradiction
                    if skel not in contradictions:
                        contradictions[skel] = set()
                    contradictions[skel].add(old_idx)
        skeleton_last[skel] = (line, i)

    if not contradictions:
        return text

    # Collect all line indices to remove
    remove_indices = set()
    for indices in contradictions.values():
        remove_indices.update(indices)

    # Only remove lines where the ENTIRE line is about the contradicted fact
    # (don't remove lines that contain other important info)
    # Safety: only remove if line is short (< 100 chars) — long lines likely have other content
    safe_removes = set()
    for idx in remove_indices:
        if len(lines[idx].strip()) < 100:
            safe_removes.add(idx)

    if not safe_removes:
        return text

    result_lines = [line for i, line in enumerate(lines) if i not in safe_removes]
    removed = len(safe_removes)
    print(f"  Contradiction resolution: {removed} stale lines removed "
          f"({len(contradictions)} entities updated)", file=sys.stderr)

    return "\n".join(result_lines)


# ── L10: CUE DISTILLATION ─────────────────────────────────────────
# Theory: Method of Loci (500 BC) + Schema Theory (Bartlett 1932)
# + Predictive Coding (Rao & Ballard 1999).
# The LLM already knows ~80% of what we store (APIs, syntax, patterns).
# Only store NOVEL facts (numbers, decisions, commits) + minimal CUES
# for generic knowledge that the LLM can reconstruct from memory.

# Regex patterns for detecting novel (project-specific) content
_NOVEL_PATTERNS = [
    re.compile(r'\d{4}[-/]\d{2}[-/]\d{2}'),                    # dates
    re.compile(r'\b[a-f0-9]{7,40}\b'),                             # X13: commit hashes (word boundary to avoid false positives)
    re.compile(r'x\d+\.?\d*'),                                   # ratios (x4.1, x19.4)
    re.compile(r'\$\d+'),                                        # costs ($0.024)
    re.compile(r'\d+\.?\d*[KMBkm](?:\b|$)'),                    # quantities (348M, 65K)
    re.compile(r'\d+%'),                                         # percentages
    re.compile(r'v\d+\.\d+'),                                    # versions (v0.9)
    re.compile(r'P\d{1,2}\b'),                                   # project phases (P13)
    re.compile(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+'),                 # CamelCase identifiers
    re.compile(r'(?<!\b[ei])[\w/\\]{2,}\.\w{1,4}\b'),             # file paths (skip e.g/i.e)
    re.compile(r'Sharpe|BLEU|F1|accuracy|precision|recall', re.I),  # metrics names
]

# Patterns indicating generic/known knowledge (LLM can reconstruct)
_KNOWN_PATTERNS = [
    re.compile(r'^(?:according to|as per|following|based on)\b', re.I),
    re.compile(r'^(?:the|a|an)\s+(?:standard|default|typical|common|recommended)\b', re.I),
    re.compile(r'\bMaterial Design\b|\bWCAG\b|\bApple HIG\b', re.I),
    re.compile(r'\bguidelines?\s+(?:state|recommend|suggest)\b', re.I),
    re.compile(r'\bbest practices?\b', re.I),
]


def _novelty_score(line: str) -> float:
    """Score how NOVEL a line is (0.0=generic knowledge, 1.0=unique fact).

    High novelty: project-specific numbers, dates, commits, decisions.
    Low novelty: framework docs, standard patterns, API descriptions.
    """
    if not line:
        return 0.0
    s = line.strip()
    if not s:
        return 0.0

    # Headers and tagged lines are structural/novel — always keep
    if s.startswith("#") or s.startswith("===") or s.startswith("?"):
        return 1.0
    for tag in ("D>", "B>", "E>", "F>", "A>"):
        if s.startswith(tag):
            return 0.9

    # Code comments and code lines — keep as-is (context-dependent)
    if s.startswith("//") or s.startswith("/*") or s.startswith("*"):
        return 0.8
    # Code patterns (braces, imports, XML)
    if re.match(r'^[\.\{\}</@]', s) or s.startswith("import ") or s.startswith("val "):
        return 0.8

    score = 0.0

    # Novel indicators: project-specific content
    for pat in _NOVEL_PATTERNS:
        matches = pat.findall(s)
        if matches:
            score += 0.15 * len(matches)

    # Known indicators: generic framework knowledge
    for pat in _KNOWN_PATTERNS:
        if pat.search(s):
            score -= 0.3

    # Ratio of numbers to words — high ratio = data-dense = novel
    words = s.split()
    if words:
        num_tokens = sum(1 for w in words if re.search(r'\d', w))
        num_ratio = num_tokens / len(words)
        score += num_ratio * 0.3

    # Key=value density — structured data is novel
    kv_count = len(re.findall(r'\w+=\S+', s))
    score += min(0.3, kv_count * 0.1)

    # Pipe-separated values — dense fact lines
    if s.count('|') >= 2:
        score += 0.2

    # Long text without any numbers or identifiers = likely generic
    if len(s) > 100 and not re.search(r'\d', s):
        score = min(score, 0.15)

    # Floor: lines with dates, commits, or ratios are ALWAYS novel (factual data).
    # Prevents these from being mangled by _generate_cue() below threshold.
    if re.search(r'\d{4}[-/]\d{2}[-/]\d{2}|[a-f0-9]{7,40}|x\d+\.?\d*', s):
        score = max(score, 0.35)

    return max(0.0, min(1.0, score))


def _generate_cue(line: str) -> str:
    """Compress a KNOWN line into a minimal retrieval cue (2-10 tokens).

    Extracts the key concept identifier that will trigger the LLM's
    parametric memory to reconstruct the full knowledge.
    """
    s = line.strip()

    # If line has a key: value format, keep just key + any numbers
    kv_match = re.match(r'^(\w[\w_]*)\s*[:=]\s*(.+)', s)
    if kv_match:
        key = kv_match.group(1)
        value = kv_match.group(2)
        # Keep numbers WITH surrounding context (word before + after number)
        nums_with_ctx = re.findall(r'(?:\w+\s+)?\d+[\.\d]*\s*(?:[a-zA-Z%]+)?', value)
        # Keep CamelCase identifiers (API names, class names)
        identifiers = re.findall(r'[A-Z][a-z]+(?:[A-Z][a-z]+)+', value)
        # Keep proper nouns (capitalized words that aren't sentence starters)
        proper_nouns = re.findall(r'(?:^|[\s,])((?:[A-Z][\w]*\s*){1,3})', value)
        proper_nouns = [p.strip() for p in proper_nouns if len(p.strip()) > 2]
        kept = [n.strip() for n in nums_with_ctx[:4]] + identifiers[:2] + proper_nouns[:2]
        if kept:
            # Deduplicate while preserving order
            seen = set()
            unique = []
            for k in kept:
                if k.lower() not in seen:
                    seen.add(k.lower())
                    unique.append(k)
            return f"{key}: {', '.join(unique)}"
        # No numbers or identifiers — just the key as cue
        return key

    # If line has pipe-separated entries, keep first identifier + count
    if '|' in s:
        parts = [p.strip() for p in s.split('|')]
        # Extract just the key names
        keys = []
        for p in parts:
            km = re.match(r'^(\w[\w_]*)', p)
            if km:
                keys.append(km.group(1))
        if keys:
            return ' | '.join(keys[:5])

    # Fallback: extract the most specific noun phrases (capitalized words + adjacent)
    important = re.findall(r'[A-Z][\w]*(?:\s+[A-Z][\w]*)*', s)
    # Also grab any numbers with context
    nums = re.findall(r'(?:\w+\s+)?\d+[\.\d]*\s*(?:[a-zA-Z%]+)?', s)
    all_parts = important[:3] + [n.strip() for n in nums[:3]]
    if all_parts:
        return ' | '.join(all_parts)

    # Last resort: first N words (enough for the LLM to reconstruct)
    words = s.split()
    return ' '.join(words[:min(8, len(words))])


def _cue_distill(text: str, threshold: float = 0.35) -> str:
    """L10: Cue Distillation — replace generic knowledge with minimal cues.

    Lines with novelty_score < threshold are compressed to retrieval cues.
    Lines with novelty_score >= threshold are kept verbatim (novel facts).

    Theory: Predictive Coding (Rao & Ballard 1999) — only store prediction errors.
    The LLM's parametric memory already contains generic knowledge.
    """
    if not text:
        return text or ""
    lines = text.split("\n")
    result = []
    cued = 0
    kept = 0

    for line in lines:
        s = line.strip()
        if not s:
            result.append(line)
            continue

        score = _novelty_score(s)

        if score >= threshold:
            result.append(line)
            kept += 1
        else:
            cue = _generate_cue(s)
            if cue and len(cue) < len(s) * 0.7:  # Only cue if actually shorter
                result.append(cue)
                cued += 1
            else:
                result.append(line)  # Keep if cue not shorter
                kept += 1

    if cued > 0:
        print(f"  L10 Cue Distillation: {cued} lines cued, {kept} kept "
              f"(threshold={threshold})", file=sys.stderr)

    return "\n".join(result)


# ── L11: RULE EXTRACTION ──────────────────────────────────────────
# Theory: Kolmogorov complexity (1965) — store the shortest PROGRAM
# that generates the data, not the data itself.
# Detect repeated key=value structures and factorize into rules.

def _extract_rules(text: str) -> str:
    """L11: Rule Extraction — factorize repeated key=value patterns.

    Detects lines with multiple key=value or key: value pairs sharing
    the same unit/structure and condenses them into a single rule line.

    Example:
      battery_drain: 9min screen | 1% GPS | 5% BT | 15% WiFi
      -> battery_drain: screen=9min GPS=1% BT=5% WiFi=15%
    """
    if not text:
        return text or ""
    lines = text.split("\n")
    result = []
    factorized = 0

    for line in lines:
        s = line.strip()
        if not s:
            result.append(line)
            continue

        # Detect pipe-separated key-value entries with shared units
        if '|' in s and s.count('|') >= 2:
            parts = [p.strip() for p in s.split('|')]

            # Try to extract key: entries from each part
            kvs = []
            for p in parts:
                m = re.match(r'^(\w[\w_\s]*?)\s*[:=]\s*(.+)', p)
                if m:
                    kvs.append((m.group(1).strip(), m.group(2).strip()))

            # If most parts are key=value and values share a unit pattern
            if len(kvs) >= 3 and len(kvs) >= len(parts) * 0.6:
                # Extract common unit suffix
                values = [v for _, v in kvs]
                units = set()
                for v in values:
                    u = re.findall(r'[a-zA-Z%]+$', v)
                    if u:
                        units.add(u[0])

                if len(units) == 1:
                    # All same unit — factorize
                    unit = units.pop()
                    compact_parts = []
                    for k, v in kvs:
                        num = re.match(r'[\d\.]+', v)
                        if num:
                            compact_parts.append(f"{k}={num.group()}")
                        else:
                            compact_parts.append(f"{k}={v}")
                    rule_line = f"({unit}) " + ", ".join(compact_parts)
                    result.append(rule_line)
                    factorized += 1
                    continue

        result.append(line)

    if factorized > 0:
        print(f"  L11 Rule Extraction: {factorized} lines factorized",
              file=sys.stderr)

    return "\n".join(result)


def _llm_compress_chunk(text: str, client, context: str = "") -> tuple:
    """Compress a single chunk via Claude Haiku API. Returns text unchanged on failure."""
    try:
        response = client.messages.create(
            model="claude-haiku-4-5-20251001",
            max_tokens=max(1, token_count(text)),
            temperature=0,
            system=_L9_SYSTEM,
            messages=[{"role": "user", "content":
                _L9_PROMPT + f"INPUT ({len(text)} chars):\n{text}"
            }],
        )
        compressed = response.content[0].text
        truncated = response.stop_reason == "max_tokens"
        if truncated:
            print(f"  L9 WARNING: truncated, keeping original [{context}]", file=sys.stderr)
            return text, response.usage
        if len(compressed) < len(text) * 0.9:
            return compressed, response.usage
        return text, response.usage
    except Exception as e:
        print(f"  L9 ERROR: {e} [{context}]", file=sys.stderr)
        return text, None


def _llm_compress(text: str, context: str = "") -> str:
    """Layer 9: LLM self-compress via Claude Haiku API.

    R1-Compress: chunks text by ## sections for better coherence.
    Returns text unchanged if unavailable.
    """
    if len(text) <= 4000:
        return text
    if _m._SKIP_L9:
        return text
    try:
        import os, subprocess as _sp
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            try:
                _r = _sp.run(['powershell', '-Command',
                    "[System.Environment]::GetEnvironmentVariable('ANTHROPIC_API_KEY', 'User')"],
                    capture_output=True, text=True, timeout=5)
                api_key = _r.stdout.strip() or None
            except Exception:
                pass
        if not api_key:
            return text
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        # R1-Compress: chunk by sections for better fact retention
        if len(text) > 8000:
            chunks = re.split(r'(?=^## )', text, flags=re.MULTILINE)
            chunks = [c for c in chunks if c.strip()]

            # Fallback: if no ## headers found, split by line count
            if len(chunks) < 2:
                lines = text.split("\n")
                chunk_size = max(1, len(lines) // max(2, len(text) // 6000))  # M3 fix: at least 2 chunks
                chunks = []
                for i in range(0, len(lines), chunk_size):
                    chunk = "\n".join(lines[i:i + chunk_size])
                    if chunk.strip():
                        chunks.append(chunk)

            if len(chunks) >= 2:
                compressed_chunks = []
                total_in, total_out = 0, 0
                for i, chunk in enumerate(chunks):
                    if len(chunk) < 200:  # too small to compress
                        compressed_chunks.append(chunk)
                        continue
                    result, usage = _llm_compress_chunk(
                        chunk, client, context=f"{context}:chunk{i}")
                    compressed_chunks.append(result)
                    if usage:
                        total_in += usage.input_tokens
                        total_out += usage.output_tokens

                llm_compressed = "\n".join(compressed_chunks)
                if len(llm_compressed) < len(text) * 0.9:
                    print(f"  Layer 9 (LLM): {len(text)} -> {len(llm_compressed)} chars "
                          f"(API: {total_in}in+{total_out}out) "
                          f"[{len(chunks)} chunks] [{context}]", file=sys.stderr)
                    return llm_compressed
                return text

        # Single-chunk compression for smaller texts
        result, usage = _llm_compress_chunk(text, client, context=context)
        if len(result) < len(text) * 0.9:
            api_str = f"(API: {usage.input_tokens}in+{usage.output_tokens}out)" if usage else ""
            print(f"  Layer 9 (LLM): {len(text)} -> {len(result)} chars "
                  f"{api_str} [{context}]", file=sys.stderr)
            return result
        return text
    except ImportError:
        return text  # anthropic not installed
    except Exception as e:
        print(f"  Layer 9 ERROR: {e} [{context}]", file=sys.stderr)
        return text


def compress_file(filepath: Path) -> str:
    filepath = Path(filepath)
    if not filepath.exists():
        return ""
    try:
        text = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError) as e:
        import sys
        print(f"[MUNINN] compress_file failed on {filepath}: {e}", file=sys.stderr)
        return ""

    # P10: Redact secrets before any compression (compiled patterns)
    for cpat in _m._COMPILED_SECRET_PATTERNS:
        text = cpat.sub('[REDACTED]', text)

    lines = text.split("\n")

    sections = []
    current_header = None
    current_lines = []

    for line in lines:
        if line.startswith("## "):
            if current_header or current_lines:
                sections.append((current_header or "## Preamble", current_lines))
            current_header = line
            current_lines = []
        elif line.startswith("# ") and not line.startswith("## "):
            continue
        else:
            current_lines.append(line)

    if current_header or current_lines:
        sections.append((current_header or "## Preamble", current_lines))

    output = ["# MUNINN|codebook=v0.1"]
    for header, slines in sections:
        compressed = compress_section(header, slines)
        output.append(compressed)

    result = "\n".join(output)

    # Contradiction resolution (last-writer-wins on numeric facts)
    result = _resolve_contradictions(result)

    # L10: Cue Distillation — BEFORE L9 (filter generic knowledge early)
    result = _cue_distill(result)

    # L11: Rule Extraction — factorize repeated key=value patterns
    result = _extract_rules(result)

    # Layer 9: LLM self-compress (optional, for large outputs)
    result = _llm_compress(result, context=str(filepath.name))

    return result


def decode_line(line: str) -> str:
    cb = get_codebook()
    result = line

    reverse_rules = {v: k for k, v in cb["text_rules"].items()
                     if len(v) > 0 and v != k}
    for code in sorted(reverse_rules.keys(), key=len, reverse=True):
        if code in result:
            result = result.replace(code, reverse_rules[code])

    return result


def verify_compression(filepath: Path):
    """Compress -> report what was kept, what was lost, quality score.

    Checks:
    1. Fact retention: are all numbers/metrics preserved?
    2. Entity retention: are all named entities preserved?
    3. Compression ratio achieved
    4. Learned rules report (what the mycelium contributed)
    """
    original = filepath.read_text(encoding="utf-8")
    compressed = compress_file(filepath)

    # Extract facts from original and compressed
    orig_facts = extract_facts(original)
    comp_facts = extract_facts(compressed)

    # Find preserved and lost facts
    preserved = [f for f in orig_facts if f in compressed]
    lost = [f for f in orig_facts if f not in compressed]

    # Token counts (real if tiktoken installed, estimate otherwise)
    orig_tokens, tok_method = count_tokens(original)
    comp_tokens, _ = count_tokens(compressed)
    ratio = orig_tokens / max(comp_tokens, 1)

    # Report learned rules contribution
    cb = get_codebook()
    learned_fillers = cb.get("learned_fillers", [])
    learned_abbrevs = cb.get("learned_abbreviations", {})

    # Count how many learned fillers were actually stripped
    filler_hits = 0
    for filler in learned_fillers:
        filler_hits += len(re.findall(rf"\b{re.escape(filler)}\b", original, re.IGNORECASE))

    # Count abbreviation hits
    abbrev_hits = 0
    for long_form in learned_abbrevs:
        abbrev_hits += len(re.findall(rf"\b{re.escape(long_form)}\b", original, re.IGNORECASE))

    print(f"=== MUNINN VERIFY: {filepath.name} ===")
    print(f"\n  Compression ({tok_method}):")
    print(f"    {orig_tokens} -> {comp_tokens} tokens (x{ratio:.1f}, -{(orig_tokens - comp_tokens) / max(orig_tokens, 1) * 100:.0f}%)")
    print(f"\n  Facts ({len(orig_facts)} found):")
    print(f"    Preserved: {len(preserved)}/{len(orig_facts)}")
    if lost:
        print(f"    Lost: {lost[:10]}")
    else:
        print(f"    Lost: none")
    print(f"\n  Mycelium contribution:")
    print(f"    Learned fillers: {len(learned_fillers)} rules, {filler_hits} hits in this file")
    print(f"    Learned abbreviations: {len(learned_abbrevs)} rules, {abbrev_hits} hits in this file")
    print(f"    Mycelium fusions (L6): {len(cb['mycelium_rules'])} rules")
    print(f"\n  Quality score: ", end="")
    fact_retention = len(preserved) / max(len(orig_facts), 1)
    if fact_retention >= 0.9 and ratio >= 2.0:
        print(f"EXCELLENT (facts={fact_retention:.0%}, ratio=x{ratio:.1f})")
    elif fact_retention >= 0.7 and ratio >= 1.5:
        print(f"GOOD (facts={fact_retention:.0%}, ratio=x{ratio:.1f})")
    elif fact_retention >= 0.5:
        print(f"OK (facts={fact_retention:.0%}, ratio=x{ratio:.1f})")
    else:
        print(f"POOR (facts={fact_retention:.0%}, ratio=x{ratio:.1f}) — losing too many facts")


