"""
B-SCAN-06: LLM Scanner (Pass 1)
================================
Scans priority-ordered source files for security vulnerabilities using
an LLM (Haiku via Anthropic API).

Input:  priority-ordered files (top 20%, min 10) + bible .mn content
Output: list of LLMFinding {file, line, type, severity, description, confidence}

Graceful degradation: if Anthropic API is unavailable, returns empty list.
This scanner NEVER crashes — all API errors are caught and logged.
"""

import re
import time
import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Data model
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class LLMFinding:
    """A single vulnerability finding from the LLM scanner."""
    file: str
    line: int
    type: str
    severity: str
    description: str
    confidence: float = 0.7
    source: str = "llm"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Constants
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_SCANNER_VERSION = "0.1.0"

# Approximate tokens per character (conservative estimate for English code)
_CHARS_PER_TOKEN = 4

# Default model
DEFAULT_MODEL = "claude-haiku-4-20250414"

# Cost per million tokens (Haiku)
_COST_PER_M_INPUT = 0.25   # $/M input tokens
_COST_PER_M_OUTPUT = 1.25  # $/M output tokens

# Max tokens per batch
MAX_BATCH_TOKENS = 4000


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Prompt construction
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_PROMPT_HEADER = (
    "You are a security auditor. Below is a vulnerability bible for {language}, "
    "followed by source code.\n"
    "Find ALL security vulnerabilities in the code. For each finding, output EXACTLY:\n"
    "FILE:{{path}} LINE:{{number}} TYPE:{{vulnerability_id}} "
    "SEVERITY:{{CRIT|HIGH|MED|LOW}} DESC:{{one-line}}\n"
    "If no vulnerabilities found, output: CLEAN\n"
    "Do NOT explain. Do NOT add commentary. Only the format above."
)


def build_prompt(file_path: str, content: str, language: str, bible_mn: str) -> str:
    """Construct the LLM prompt for scanning a file.

    Args:
        file_path: path to the source file
        content: source code content
        language: programming language
        bible_mn: compressed bible content

    Returns:
        Formatted prompt string
    """
    header = _PROMPT_HEADER.format(language=language)
    return f"{header}\n\n=== BIBLE ===\n{bible_mn}\n\n=== CODE ===\n{content}"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Response parsing
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# Regex to parse: FILE:path LINE:123 TYPE:INJ-SQL SEVERITY:CRIT DESC:some text
_FINDING_RE = re.compile(
    r"^FILE:(?P<file>.+?)\s+"
    r"LINE:(?P<line>\d+)\s+"
    r"TYPE:(?P<type>\S+)\s+"
    r"SEVERITY:(?P<severity>CRIT|HIGH|MED|LOW)\s+"
    r"DESC:(?P<desc>.+)$"
)


def parse_llm_response(response: str, default_file: str = "") -> list[LLMFinding]:
    """Parse the structured LLM output into LLMFinding objects.

    Args:
        response: raw LLM response text
        default_file: fallback file path if not in response

    Returns:
        List of LLMFinding (empty if CLEAN or unparseable)
    """
    if not response or not response.strip():
        return []

    findings = []
    for raw_line in response.splitlines():
        line = raw_line.strip()

        # CLEAN means no findings
        if line == "CLEAN":
            return []

        m = _FINDING_RE.match(line)
        if m:
            try:
                findings.append(LLMFinding(
                    file=m.group("file"),
                    line=int(m.group("line")),
                    type=m.group("type"),
                    severity=m.group("severity"),
                    description=m.group("desc").strip(),
                ))
            except (ValueError, KeyError):
                continue

    return findings


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Cost estimation
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def estimate_cost(
    files: list[tuple[str, str]],
    model: str = DEFAULT_MODEL,
    bible_mn: str = "",
) -> dict:
    """Estimate tokens and cost before scanning.

    Args:
        files: list of (file_path, content) tuples
        model: model name (for future cost differentiation)
        bible_mn: bible content (counted once per batch)

    Returns:
        dict with keys: total_tokens, estimated_cost_usd, file_count, batches
    """
    if not files:
        return {
            "total_tokens": 0,
            "estimated_cost_usd": 0.0,
            "file_count": 0,
            "batches": 0,
        }

    bible_tokens = len(bible_mn) // _CHARS_PER_TOKEN if bible_mn else 0

    total_tokens = 0
    batch_count = 0
    current_batch_tokens = 0

    for _path, content in files:
        file_tokens = len(content) // _CHARS_PER_TOKEN
        prompt_tokens = bible_tokens + file_tokens

        # Check if we need a new batch
        if current_batch_tokens > 0 and current_batch_tokens + file_tokens > MAX_BATCH_TOKENS:
            batch_count += 1
            current_batch_tokens = 0

        if current_batch_tokens == 0:
            # New batch: includes bible
            current_batch_tokens = prompt_tokens
        else:
            current_batch_tokens += file_tokens

        total_tokens += prompt_tokens

    # Count the last batch
    if current_batch_tokens > 0:
        batch_count += 1

    # Estimate output tokens (~10% of input)
    output_tokens = total_tokens // 10
    cost = (total_tokens * _COST_PER_M_INPUT + output_tokens * _COST_PER_M_OUTPUT) / 1_000_000

    return {
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(cost, 6),
        "file_count": len(files),
        "batches": batch_count,
    }


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# LLM call
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _get_client(client=None):
    """Get or create an Anthropic client. Returns None if unavailable."""
    if client is not None:
        return client
    try:
        import anthropic
        return anthropic.Anthropic()
    except Exception:
        logger.info("[B-SCAN-06] anthropic not available, LLM scanner disabled")
        return None


def _call_llm(prompt: str, client, model: str = DEFAULT_MODEL) -> str:
    """Call the LLM API. Returns response text or empty string on error.

    NEVER raises — all errors are caught and logged.
    """
    if client is None:
        return ""
    try:
        response = client.messages.create(
            model=model,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from response
        if response and response.content:
            return response.content[0].text
        return ""
    except Exception as e:
        logger.warning(f"[B-SCAN-06] LLM call failed: {e}")
        return ""


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Single file scan
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scan_file(
    file_path: str,
    content: str,
    language: str,
    bible_mn: str,
    client=None,
    model: str = DEFAULT_MODEL,
) -> list[LLMFinding]:
    """Scan a single file for vulnerabilities using the LLM.

    Args:
        file_path: path to the source file
        content: source code content
        language: programming language
        bible_mn: compressed bible content
        client: optional Anthropic client (None = try to create one)
        model: model to use

    Returns:
        List of LLMFinding (empty if API unavailable or no findings)
    """
    client = _get_client(client)
    if client is None:
        return []

    prompt = build_prompt(file_path, content, language, bible_mn)
    response = _call_llm(prompt, client, model)
    return parse_llm_response(response, default_file=file_path)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Batch scan with rate limiting
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scan_batch(
    files: list[tuple[str, str]],
    bible_mn: str,
    language: str,
    client=None,
    max_rps: int = 10,
    model: str = DEFAULT_MODEL,
) -> list[LLMFinding]:
    """Scan multiple files with rate limiting.

    Args:
        files: list of (file_path, content) tuples
        bible_mn: compressed bible content
        language: programming language
        client: optional Anthropic client
        max_rps: max requests per second (default 10)
        model: model to use

    Returns:
        Combined list of LLMFinding from all files
    """
    if not files:
        return []

    client = _get_client(client)
    if client is None:
        return []

    all_findings = []
    min_interval = 1.0 / max_rps if max_rps > 0 else 0
    last_call = 0.0

    for file_path, content in files:
        # Rate limiting
        now = time.time()
        elapsed = now - last_call
        if elapsed < min_interval and last_call > 0:
            time.sleep(min_interval - elapsed)

        prompt = build_prompt(file_path, content, language, bible_mn)
        last_call = time.time()
        response = _call_llm(prompt, client, model)
        findings = parse_llm_response(response, default_file=file_path)
        all_findings.extend(findings)

    return all_findings
