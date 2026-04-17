"""Muninn feed pipeline — transcript parsing, compression, hooks."""

import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path

from tokenizer import count_tokens, token_count
from _secrets import redact_secrets_text as _redact_secrets_text


class _ModRef:
    """Lazy reference to muninn module — avoids circular import."""
    def __getattr__(self, name):
        return getattr(sys.modules['muninn'], name)
    def __setattr__(self, name, value):
        setattr(sys.modules['muninn'], name, value)

_m = _ModRef()

__all__ = ['_MuninnLock', '_compress_code_blocks', '_detect_transcript_format', '_feed_from_stop_hook_locked', '_hook_log', '_parse_json_conversation', '_parse_markdown_conversation', '_semantic_rle', '_update_session_index', '_update_usefulness', 'compress_transcript', 'feed_from_hook', 'feed_from_stop_hook', 'feed_from_transcript', 'feed_history', 'feed_watch', 'ingest', 'parse_transcript']


def _compress_code_blocks(text: str) -> str:
    """P17: Compress code blocks in text — keep signatures, drop bodies.

    Replaces ```...``` blocks with function/class signatures + '...' placeholder.
    Non-code blocks (e.g., ```json, ```yaml) are kept as-is if short (<5 lines).
    """
    def _compress_block(match):
        lang = (match.group(1) or "").strip().lower()
        code = match.group(2)

        # Keep short blocks as-is (config, output, etc.)
        lines = code.strip().split("\n")
        if len(lines) <= 4:
            return match.group(0)

        # For code: extract signatures (def, class, function, const, etc.)
        sigs = []
        for line in lines:
            stripped = line.strip()
            if re.match(r"^(def |class |async def |function |const |let |var |export |import |from )", stripped):
                sigs.append(stripped)
            elif re.match(r"^(#|//|/\*)", stripped) and len(stripped) < 80:
                sigs.append(stripped)  # keep short comments

        if sigs:
            return f"```{lang}\n" + "\n".join(sigs) + "\n  ...\n```"
        else:
            # No signatures found — keep first 2 lines + ellipsis
            return f"```{lang}\n" + "\n".join(lines[:2]) + "\n  ...\n```"

    return re.sub(r"```(\w*)\n(.*?)```", _compress_block, text, flags=re.DOTALL)


def _parse_json_conversation(filepath: Path) -> list[str]:
    """P38: Parse claude.ai JSON export (conversations format)."""
    try:
        data = json.loads(filepath.read_text(encoding="utf-8", errors="ignore"))
    except (json.JSONDecodeError, OSError):
        return []

    texts = []
    # Handle various JSON conversation formats
    messages = []
    if isinstance(data, dict):
        # claude.ai format: {"chat_messages": [...]} or {"conversation": [...]}
        messages = data.get("chat_messages", data.get("conversation",
                   data.get("messages", data.get("content", []))))
    elif isinstance(data, list):
        messages = data

    for msg in messages:
        if not isinstance(msg, dict):
            continue
        # Extract text content
        content = msg.get("content", msg.get("text", ""))
        if isinstance(content, str) and len(content.strip()) >= 10:
            texts.append(content.strip())
        elif isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    t = part.get("text", "")
                    if len(t.strip()) >= 10:
                        texts.append(t.strip())
                elif isinstance(part, str) and len(part.strip()) >= 10:
                    texts.append(part.strip())
    return texts


def _parse_markdown_conversation(filepath: Path) -> list[str]:
    """P38: Parse markdown conversation (## Human / ## Assistant headers)."""
    try:
        text = filepath.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    texts = []
    current = []
    for line in text.split("\n"):
        if re.match(r'^##\s*(Human|Assistant|User|Claude)', line, re.IGNORECASE):
            if current:
                block = "\n".join(current).strip()
                if len(block) >= 10:
                    texts.append(block)
                current = []
        else:
            current.append(line)
    if current:
        block = "\n".join(current).strip()
        if len(block) >= 10:
            texts.append(block)
    return texts


def _detect_transcript_format(filepath) -> str:
    """P38: Detect transcript format from file content.

    Returns: 'jsonl', 'json', 'markdown', or 'unknown'.

    BUG-107 fix (brick 18): wrap input with Path() so callers can pass
    str. Forge property test caught the AttributeError on str input.
    """
    # BUG-107: tolerate str / None / Path input
    if not filepath:
        return "unknown"
    if not isinstance(filepath, Path):
        try:
            filepath = Path(filepath)
        except (TypeError, ValueError):
            return "unknown"
    try:
        first_bytes = filepath.read_bytes()[:500]
        first_text = first_bytes.decode("utf-8", errors="ignore").strip()
    except OSError:
        return "unknown"

    # JSONL: first line is a valid JSON object
    first_line = first_text.split("\n")[0].strip()
    if first_line.startswith("{"):
        try:
            obj = json.loads(first_line)
            # Check if it's a single JSON file (not JSONL)
            # JSONL = multiple lines starting with {
            lines = first_text.split("\n")
            json_lines = sum(1 for l in lines[:5] if l.strip().startswith("{"))
            if json_lines >= 2:
                return "jsonl"
            # Single JSON object with known keys = could be JSONL (1 msg) or json conversation
            if isinstance(obj, dict):
                if any(k in obj for k in ("messages", "chat_messages", "conversation", "content")):
                    return "json"
                # Single JSONL line (e.g. {"type": "user", ...})
                if "type" in obj or "role" in obj:
                    return "jsonl"
        except json.JSONDecodeError:
            pass

    # JSON: starts with [ (array of messages). Don't read whole file to validate —
    # if first bytes look like JSON array and it's not JSONL, assume json.
    if first_text.startswith("["):
        return "json"

    # Markdown: contains ## headers (Human/Assistant or any section)
    if re.search(r'^#{1,3}\s+\S', first_text, re.MULTILINE):
        return "markdown"

    return "unknown"


def parse_transcript(jsonl_path) -> list[str]:
    """Parse a transcript and extract text messages.

    P38: Auto-detects format: JSONL (Claude Code), JSON (claude.ai), markdown.
    L0 FILTER: strips tool results (77% of transcript) down to 1-line summaries.
    Keeps: user messages, assistant text, tool call names + args (not results).

    BUG-107 fix (brick 18): wrap input with Path() so callers can pass str.
    """
    if not jsonl_path:
        return []
    if not isinstance(jsonl_path, Path):
        try:
            jsonl_path = Path(jsonl_path)
        except (TypeError, ValueError):
            return []
    # P38: Multi-format detection
    fmt = _detect_transcript_format(jsonl_path)
    if fmt == "json":
        return _parse_json_conversation(jsonl_path)
    elif fmt == "markdown":
        return _parse_markdown_conversation(jsonl_path)
    # Default: JSONL (Claude Code) — fall through to original parser

    # P28: Claude verbal tics — full sentences that carry zero information
    _CLAUDE_TICS = re.compile(
        r"^("
        r"Let me (?:read|check|look|examine|search|find|see|verify|review|update|analyze|explore|open)"
        r"|I'll (?:now |start |begin |go ahead and )?"
          r"(?:read|check|look|examine|search|find|see|verify|review|update|analyze|fix|implement|create|add|make|write)"
        r"|(?:Here's|Here is) what (?:I found|I see|the .+ looks like|we have)"
        r"|(?:Now |OK(?:ay)?,? )?(?:let me|I'll) (?:take a look|have a look|investigate|dig into)"
        r"|(?:Great|Perfect|Good|Excellent|Sure|Alright|Got it|Understood)[.!,]?\s*(?:Let me|I'll|Now)?"
        r"|Looking (?:at|into|through) (?:the |this |that )?"
        r"|I (?:can see|notice|observe) (?:that )?"
        r"|(?:Based on|From) (?:the |my |this |what )?(?:analysis|review|reading|examination|investigation)"
        r"|This (?:looks|seems|appears) (?:like |to be )?"
        r"|I've (?:made|completed|finished|updated|fixed|implemented|added|created) the"
        r")",
        re.IGNORECASE
    )
    texts = []
    # P27: Track file reads — only keep last read per file
    file_reads = {}  # file_path -> (index_in_texts, summary, result)

    with open(jsonl_path, encoding="utf-8", errors="ignore") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            if entry.get("type") not in ("user", "assistant"):
                continue

            message = entry.get("message", {})
            content = message.get("content", [])

            if isinstance(content, str):
                texts.append(content)
                continue

            if not isinstance(content, list):
                continue

            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type", "")

                if btype == "text":
                    text = block.get("text", "")
                    if len(text) >= 20:
                        # P17: compress code blocks in text
                        if "```" in text:
                            text = _compress_code_blocks(text)
                        # P28: Strip Claude verbal tics prefix (keep content after tic)
                        filtered_lines = []
                        for tline in text.split("\n"):
                            stripped = tline.strip()
                            m = _CLAUDE_TICS.match(stripped)
                            if m:
                                # Keep the rest of the line after the tic
                                remainder = stripped[m.end():].strip().lstrip(".,;:!").strip()
                                if len(remainder) >= 10:
                                    filtered_lines.append(remainder)
                                # else: pure tic sentence, drop entirely
                            else:
                                filtered_lines.append(tline)
                        text = "\n".join(filtered_lines).strip()
                        if len(text) >= 10:
                            texts.append(text)

                elif btype == "tool_use":
                    # L0: keep tool name + key args as 1-line summary
                    name = block.get("name", "?")
                    inp = block.get("input", {})
                    if name in ("Read", "read"):
                        fpath = inp.get('file_path', '?')
                        summary = f"[read {fpath}]"
                        # P27: mark previous reads of same file for removal
                        if fpath in file_reads:
                            old_idx = file_reads[fpath]
                            texts[old_idx] = None  # mark tool_use for removal
                            # Also mark the tool_result that follows (-> ...)
                            if old_idx + 1 < len(texts) and texts[old_idx + 1] and texts[old_idx + 1].startswith("->"):
                                texts[old_idx + 1] = None
                        file_reads[fpath] = len(texts)
                    elif name in ("Edit", "edit"):
                        summary = f"[edit {inp.get('file_path', '?')}]"
                    elif name in ("Write", "write"):
                        summary = f"[write {inp.get('file_path', '?')}]"
                    elif name in ("Bash", "bash"):
                        cmd = inp.get("command", "?")[:80]
                        summary = f"[bash: {cmd}]"
                    elif name in ("Grep", "grep"):
                        summary = f"[grep '{inp.get('pattern', '?')}' in {inp.get('path', '.')}]"
                    elif name in ("Glob", "glob"):
                        summary = f"[glob {inp.get('pattern', '?')}]"
                    elif name == "Agent":
                        summary = f"[agent: {inp.get('description', '?')}]"
                    else:
                        summary = f"[{name}]"
                    texts.append(summary)

                elif btype == "tool_result":
                    # L0: strip tool results to first line only
                    rc = block.get("content", "")
                    if isinstance(rc, str) and rc.strip():
                        first_line = rc.split("\n")[0][:100]
                        if first_line.strip():
                            texts.append(f"-> {first_line}")

    # P27: Remove None-marked duplicate reads
    texts = [t for t in texts if t is not None]

    return texts


def feed_from_transcript(jsonl_path: Path, repo_path: Path,
                         max_seconds: float = 60.0):
    """Feed the mycelium from a single transcript JSONL file.
    V6A: Per-message arousal via VADER -> passed to observe() for emotional tagging.
    Chunked: saves every FEED_CHUNK_SIZE messages to avoid timeout on large transcripts.
    Resumable: tracks offset in .muninn/feed_progress.json to resume after interruption.
    Graceful timeout: if max_seconds elapsed, saves progress and exits cleanly.
    Next call resumes where it left off. No more infinite crash loops.
    """
    FEED_CHUNK_SIZE = 50  # save mycelium every N messages

    if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
    from mycelium import Mycelium

    # Resume support: check how many messages we already fed for this file
    progress_path = repo_path / ".muninn" / "feed_progress.json"
    progress = {}
    if progress_path.exists():
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            progress = {}

    file_key = jsonl_path.name
    file_size = jsonl_path.stat().st_size
    prev = progress.get(file_key, {})
    # If file size changed since last progress, start fresh (file grew)
    offset = prev.get("offset", 0) if prev.get("size", 0) == file_size else 0

    texts = parse_transcript(jsonl_path)
    if not texts:
        print(f"  No text messages found in {jsonl_path.name}")
        return 0, []

    if offset >= len(texts):
        print(f"  Already fed {offset}/{len(texts)} messages from {jsonl_path.name}")
        return len(texts), texts

    if offset > 0:
        print(f"  Resuming feed from message {offset}/{len(texts)} ({jsonl_path.name})")

    m = Mycelium(repo_path)
    m.start_session()

    fed = 0
    _t_start = time.time()
    _timed_out = False
    for i in range(offset, len(texts)):
        text = _redact_secrets_text(texts[i])
        # V6A: Score arousal per message for emotional tagging
        msg_arousal = 0.0
        if _m._HAS_SENTIMENT:
            s = _m.score_sentiment(text)
            msg_arousal = s["arousal"]
        m.observe_text(text, arousal=msg_arousal)
        fed += 1

        # Checkpoint every FEED_CHUNK_SIZE messages
        if fed % FEED_CHUNK_SIZE == 0:
            m.save()
            progress[file_key] = {"offset": offset + fed, "size": file_size}
            _m._atomic_json_write(progress_path, progress)

        # GRACEFUL TIMEOUT: check EVERY message (not just at chunk boundaries).
        # On a 1.3GB DB, a single observe_text can take minutes — we must check
        # after each message or the timeout is useless.
        if time.time() - _t_start > max_seconds:
            m.save()
            progress[file_key] = {"offset": offset + fed, "size": file_size}
            _m._atomic_json_write(progress_path, progress)
            _timed_out = True
            print(f"  TIMEOUT: fed {fed} messages in {max_seconds:.0f}s, "
                  f"saving at {offset + fed}/{len(texts)} ({jsonl_path.name})")
            break

    # Final save + close (prevent SQLite connection leak)
    m.save()
    m.close()
    if not _timed_out:
        progress[file_key] = {"offset": len(texts), "size": file_size}
    else:
        progress[file_key] = {"offset": offset + fed, "size": file_size}
    _m._atomic_json_write(progress_path, progress)
    return (len(texts) if not _timed_out else offset + fed), texts


def _semantic_rle(texts: list[str]) -> list[str]:
    """Collapse debug/retry loops in transcript messages.

    Detects sequences where the same action is retried multiple times
    (error→fix→error→fix→success) and condenses them.

    Patterns detected:
    1. Repeated similar error messages → keep first + last + count
    2. Retry sequences (try→fail→try→fail→success) → "tried A,B(fail); C worked"
    3. Consecutive reads of related files → merge into one line

    Returns filtered texts list (shorter or same length).
    """
    if len(texts) < 4:
        return texts

    result = []
    i = 0
    collapsed_count = 0

    # Error/retry detection patterns
    error_pats = re.compile(
        r'(?:error|fail|exception|traceback|errno|cannot|could not|unable|'
        r'not found|permission denied|syntax error|import error|'
        r'TypeError|ValueError|KeyError|AttributeError|NameError|IndexError|'
        r'FileNotFoundError|ModuleNotFoundError)',
        re.IGNORECASE
    )
    retry_pats = re.compile(
        r'(?:let me try|trying|attempt|retry|let me fix|fixing|'
        r'let me check|checking again|running again|re-run)',
        re.IGNORECASE
    )

    while i < len(texts):
        text = texts[i]

        # Detect start of error/retry loop
        if error_pats.search(text) and i + 2 < len(texts):
            # Scan ahead for a retry loop
            loop_start = i
            loop_errors = [text]
            loop_retries = []
            j = i + 1

            while j < len(texts):
                t = texts[j]
                is_error = bool(error_pats.search(t))
                is_retry = bool(retry_pats.search(t))

                if is_error:
                    loop_errors.append(t)
                    j += 1
                elif is_retry:
                    loop_retries.append(t)
                    j += 1
                else:
                    break

            loop_len = j - loop_start

            if loop_len >= 3 and (len(loop_errors) >= 2 or len(loop_retries) >= 2):
                # Collapse: keep first error, count, and the resolution
                first_err = loop_errors[0][:120]
                last_err = loop_errors[-1][:120]
                # Check if next message after loop is a success/fix
                resolution = ""
                if j < len(texts):
                    next_text = texts[j]
                    if not error_pats.search(next_text):
                        resolution = " -> " + next_text[:80]
                        j += 1

                collapsed = (
                    f"[RLE:{len(loop_errors)} errors, {len(loop_retries)} retries] "
                    f"{first_err}"
                )
                if last_err != first_err:
                    collapsed += f" ... {last_err}"
                collapsed += resolution

                result.append(collapsed)
                collapsed_count += loop_len
                i = j
                continue

        result.append(text)
        i += 1

    if collapsed_count > 0:
        print(f"  Semantic RLE: {collapsed_count} messages collapsed "
              f"({len(texts)} -> {len(result)})", file=sys.stderr)

    return result


def compress_transcript(jsonl_path: Path, repo_path: Path, texts: list = None) -> tuple:
    """Compress a transcript JSONL into a dense .mn session file.

    Extracts user+assistant messages, compresses each with the 7-layer
    pipeline, writes result to .muninn/sessions/<timestamp>.mn.
    Returns the path to the written .mn file.
    Accepts pre-parsed texts to avoid double parse_transcript call.
    """
    if texts is None:
        texts = parse_transcript(jsonl_path)
    if not texts:
        return None, None

    # P10: Strip secrets before compression (compiled patterns)
    for i, text in enumerate(texts):
        for cpat in _m._COMPILED_SECRET_PATTERNS:
            texts[i] = cpat.sub('[REDACTED]', texts[i])

    # Semantic RLE: collapse debug/retry loops
    # Detects sequences of similar messages (error→retry→error→retry→success)
    # and condenses them into a summary.
    texts = _semantic_rle(texts)

    # Build a pseudo-markdown from transcript messages for compress_section
    sections = []
    current_topic = []
    current_header = "## Session context"

    for text in texts:
        # If text looks like a new topic (long enough, starts with capital or #)
        if text.startswith("## ") or text.startswith("# "):
            if current_topic:
                sections.append((current_header, current_topic))
            current_header = text if text.startswith("## ") else f"## {text.lstrip('# ')}"
            current_topic = []
        else:
            current_topic.append(text)

    if current_topic:
        sections.append((current_header, current_topic))

    # If no markdown headers found, chunk by message groups
    if len(sections) == 1 and len(texts) > 10:
        sections = []
        chunk_size = max(5, len(texts) // 6)  # ~6 sections max
        for i in range(0, len(texts), chunk_size):
            chunk = texts[i:i + chunk_size]
            if not chunk:
                continue
            # Use first non-trivial line as header
            header_text = chunk[0][:80].strip()
            header_text = re.sub(r"[#\n]", "", header_text)
            sections.append((f"## {header_text}", chunk))

    # Compress each section (tags applied AFTER L9, not here)
    # B12: Emit ## headers so _m.grow_branches_from_session() can segment by topic
    output = ["# MUNINN|session_compressed"]
    for header, lines in sections:
        compressed = _m.compress_section(header, lines)
        if compressed and len(compressed) > 5:
            # Preserve ## header for grow_branches segmentation
            if header.startswith("## "):
                output.append(header)
            output.append(compressed)

    # Add facts summary at the end
    all_text = "\n".join(texts)
    facts = _m.extract_facts(all_text)
    if facts:
        output.append(f"?FACTS:{' | '.join(facts[:30])}")

    result = "\n".join(output)

    # P26: Dedup compressed lines (exact + normalized)
    seen_hashes = set()
    deduped_lines = []
    for dline in result.split("\n"):
        if dline.startswith("#") or dline.startswith("?FACTS"):
            deduped_lines.append(dline)
            continue
        # Normalize: lowercase, strip extra spaces, remove punctuation for fuzzy match
        norm = re.sub(r'[^\w\s]', '', dline.lower()).strip()
        norm = re.sub(r'\s+', ' ', norm)
        if not norm:
            deduped_lines.append(dline)  # preserve blank lines as structural separators
            continue
        if norm in seen_hashes:
            continue
        seen_hashes.add(norm)
        deduped_lines.append(dline)
    result = "\n".join(deduped_lines)

    # Contradiction resolution (last-writer-wins on numeric facts)
    result = _m._resolve_contradictions(result)

    # L10: Cue Distillation — BEFORE L9 (filter generic knowledge early)
    result = _m._cue_distill(result)

    # L11: Rule Extraction — factorize repeated key=value patterns
    result = _m._extract_rules(result)

    # Layer 9: SKIP on transcripts — regex already achieves x100+ on tool-heavy
    # transcripts, L9 adds no value (tested: 3014 vs 3319 tokens, L9 is worse).
    # L9 is only useful on raw prose (compress_file, ingest, bootstrap).

    # P14: Tag memory types AFTER L9 (so tags survive rewriting)
    tagged_lines = []
    for rline in result.split("\n"):
        if rline.strip() and not rline.startswith("#") and not rline.startswith("?FACTS"):
            tagged_lines.append(_m.tag_memory_type(rline))
        else:
            tagged_lines.append(rline)
    result = "\n".join(tagged_lines)

    # P25: Priority survival — if too many lines, drop low-priority first
    _TAG_PRIORITY = {"D>": 5, "B>": 4, "E>": 3, "F>": 3, "A>": 2}
    result_tokens = token_count(result)
    max_session_tokens = 3000  # session .mn should fit in ~3K tokens
    if result_tokens > max_session_tokens:
        lines_with_priority = []
        for pline in result.split("\n"):
            stripped = pline.strip()
            if stripped.startswith("#") or stripped.startswith("?FACTS"):
                lines_with_priority.append((99, pline))  # always keep
            else:
                priority = 1  # default: untagged
                for tag, prio in _TAG_PRIORITY.items():
                    if stripped.startswith(tag):
                        priority = prio
                        break
                lines_with_priority.append((priority, pline))
        # Sort by priority (descending), keep highest priority lines until budget
        # But preserve original order within same priority
        by_priority = sorted(enumerate(lines_with_priority),
                             key=lambda x: (-x[1][0], x[0]))
        kept_indices = set()
        running_tokens = 0
        for orig_idx, (prio, pline) in by_priority:
            line_tokens = max(1, len(pline) // 4)  # estimate, avoid per-line tiktoken
            if running_tokens + line_tokens <= max_session_tokens:
                kept_indices.add(orig_idx)
                running_tokens += line_tokens
        # Rebuild in original order
        result = "\n".join(
            pline for i, (_, pline) in enumerate(lines_with_priority)
            if i in kept_indices
        )

    # Write to .muninn/sessions/ — dedup by transcript source
    sessions_dir = repo_path / ".muninn" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    mn_path = sessions_dir / f"{timestamp}.mn"

    # Dedup: check if this transcript was already compressed (same source, same size)
    # Prevents PreCompact+SessionEnd and repeated Stop hooks from creating duplicate .mn files
    dedup_path = repo_path / ".muninn" / "compressed_transcripts.json"
    dedup_state = {}
    if dedup_path.exists():
        try:
            dedup_state = json.loads(dedup_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            dedup_state = {}

    source_key = jsonl_path.name if jsonl_path else timestamp
    source_size = jsonl_path.stat().st_size if jsonl_path and jsonl_path.exists() else 0
    prev_entry = dedup_state.get(source_key, {})

    if prev_entry.get("size", 0) == source_size and source_size > 0:
        # Same transcript, same size — overwrite the existing .mn instead of creating new one
        existing_mn = sessions_dir / prev_entry.get("mn_file", "")
        if existing_mn.exists():
            mn_path = existing_mn  # overwrite same file

    # Atomic write: tempfile + os.replace to avoid corruption on crash
    import tempfile as _tf
    _fd, _tmp = _tf.mkstemp(dir=str(mn_path.parent), suffix=".tmp")
    try:
        with open(_fd, "w", encoding="utf-8") as _f:
            _f.write(result)
        os.replace(_tmp, str(mn_path))
    except BaseException:
        try:
            os.unlink(_tmp)
        except OSError:
            pass
        raise

    # Track which transcript produced which .mn
    dedup_state[source_key] = {"size": source_size, "mn_file": mn_path.name, "timestamp": timestamp}
    _m._atomic_json_write(dedup_path, dedup_state)

    # Keep only last 10 session files (oldest get pruned)
    session_files = sorted(sessions_dir.glob("*.mn"))
    for old_file in session_files[:-10]:
        try:
            old_file.unlink()
        except OSError:
            pass

    orig_tokens, tok_method = count_tokens(all_text)
    comp_tokens = token_count(result)
    ratio = orig_tokens / max(comp_tokens, 1)
    print(f"MUNINN SESSION ({tok_method}): {orig_tokens} -> {comp_tokens} tokens (x{ratio:.1f}) -> {mn_path.name}")

    # P16: Append 1-line session summary to root.mn
    _m._append_session_log(repo_path, result, ratio)

    # P18: Extract error/fix pairs for auto-surfacing
    _m._extract_error_fixes(repo_path, result)

    # V10A: Score sentiment on RAW messages (before compression strips emotional cues)
    session_sentiment = None
    if _m._HAS_SENTIMENT:
        session_sentiment = _m.score_session(texts)

    # P22: Update session index for future retrieval
    _danger = _update_session_index(repo_path, mn_path, result, ratio, session_sentiment)

    # I1: Piggyback danger_score into session_sentiment for grow_branches_from_session
    if _danger and _danger > 0:
        if session_sentiment is None:
            session_sentiment = {"mean_valence": 0.0, "mean_arousal": 0.0,
                                 "peak_valence": 0.0, "peak_arousal": 0.0,
                                 "n_positive": 0, "n_negative": 0, "n_neutral": 0}
        session_sentiment["danger_score"] = _danger

    return mn_path, session_sentiment


def _update_session_index(repo_path: Path, mn_path: Path, compressed: str, ratio: float,
                          session_sentiment: dict = None):
    """P22: Add session entry to .muninn/session_index.json for boot search."""
    index_path = repo_path / ".muninn" / "session_index.json"
    try:
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
        if not isinstance(index, list):
            index = []
    except (json.JSONDecodeError, OSError):
        index = []

    # Extract tagged lines (D>, B>, F> are high-value)
    tagged = []
    for line in compressed.split("\n"):
        stripped = line.strip()
        for tag in ("D>", "B>", "F>", "E>", "A>"):
            if stripped.startswith(tag):
                tagged.append(stripped[:120])
                break

    # Extract key concepts (top words by frequency, excluding short/common)
    words = re.findall(r'[A-Za-z]{4,}', compressed.lower())
    stop = {"this", "that", "with", "from", "have", "been", "will", "into",
            "also", "just", "more", "some", "then", "than", "when", "what",
            "each", "line", "file", "text", "here", "there", "about"}
    word_freq = {}
    for w in words:
        if w not in stop:
            word_freq[w] = word_freq.get(w, 0) + 1
    top_concepts = sorted(word_freq, key=word_freq.get, reverse=True)[:10]

    # I1: Danger Theory DCA (Greensmith 2008)
    # Compute session danger signal from error rate, retry patterns, topic switches.
    _total_lines = max(1, len(compressed.split("\n")))
    _error_lines = sum(1 for l in compressed.split("\n") if l.strip().startswith("E>"))
    _error_rate = _error_lines / _total_lines
    _retry_count = len(re.findall(r'(?i)\b(retry|debug|fix|error|traceback|failed)\b', compressed))
    _retry_rate = min(1.0, _retry_count / max(1, _total_lines) * 5)
    _topic_switches = 0
    _prev_concepts = set()
    for line in compressed.split("\n"):
        stripped = line.strip()
        if stripped.startswith("D>") or stripped.startswith("B>"):
            cur_words = set(re.findall(r'[A-Za-z]{4,}', stripped.lower()))
            if _prev_concepts and len(cur_words & _prev_concepts) == 0:
                _topic_switches += 1
            _prev_concepts = cur_words
    _switch_rate = min(1.0, _topic_switches / max(1, _total_lines) * 10)
    _chaos_ratio = min(1.0, max(0.0, 1.0 - (ratio / 5.0))) if ratio > 0 else 0.5
    _danger_score = round(
        0.4 * _error_rate + 0.3 * _retry_rate + 0.2 * _switch_rate + 0.1 * _chaos_ratio, 4)

    entry = {
        "file": mn_path.name,
        "date": time.strftime("%Y-%m-%d"),
        "ratio": round(ratio, 1),
        "concepts": top_concepts,
        "tagged": tagged[:15],  # max 15 tagged lines per session
        "danger_score": _danger_score,  # I1
    }

    # V10A: VADER sentiment (scored on RAW messages in compress_transcript)
    if session_sentiment is not None:
        entry["sentiment"] = {
            "mean_valence": session_sentiment["mean_valence"],
            "mean_arousal": session_sentiment["mean_arousal"],
            "peak_valence": session_sentiment["peak_valence"],
            "peak_arousal": session_sentiment["peak_arousal"],
            "n_positive": session_sentiment["n_positive"],
            "n_negative": session_sentiment["n_negative"],
            "n_neutral": session_sentiment["n_neutral"],
        }
        # V10B: Russell circumplex mapping — emotional label for the session
        try:
            from sentiment import circumplex_map
            affect = circumplex_map(
                session_sentiment["mean_valence"],
                session_sentiment["mean_arousal"],
            )
            entry["sentiment"]["quadrant"] = affect["quadrant"]
            entry["sentiment"]["label"] = affect["label"]
        except (ImportError, KeyError, TypeError):
            pass

    # Dedup by filename
    index = [e for e in index if e.get("file") != mn_path.name]
    index.append(entry)

    # Keep last 50 sessions in index (even if .mn files are pruned to 10)
    index = index[-50:]
    _m._atomic_json_write(index_path, index)

    return _danger_score  # I1: propagate to grow_branches_from_session


def _update_usefulness(repo_path: Path, jsonl_path: Path):
    """P36: Boot Feedback Loop — score which boot branches were actually useful.

    Compares concepts from the session transcript against concepts from branches
    loaded at boot. Branches whose concepts appeared in the session get a higher
    usefulness_score in tree.json. This adapts scoring per-repo over time.
    """
    manifest_path = repo_path / ".muninn" / "last_boot.json"
    if not manifest_path.exists():
        return

    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return

    boot_branches = manifest.get("branches", [])
    if not boot_branches:
        return

    # Extract concepts from session transcript
    session_concepts = set()
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                    content = msg.get("message", {}).get("content", [])
                    if isinstance(content, str):
                        words = re.findall(r'[a-zA-Z]{4,}', content.lower())
                        session_concepts.update(words)
                    elif isinstance(content, list):
                        for part in content:
                            if isinstance(part, dict) and part.get("type") == "text":
                                words = re.findall(r'[a-zA-Z]{4,}', part["text"].lower())
                                session_concepts.update(words)
                except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
                    continue
    except OSError:
        return

    if not session_concepts:
        return

    # Load tree and score branches
    tree = _m.load_tree()
    nodes = tree["nodes"]
    tree_dir = _m._get_tree_dir()
    updated = False

    # V2B fix: compute mean td_value across all branches for proper Bellman backup
    _all_td = [nodes[b].get("td_value", 0.5) for b in boot_branches
                if b in nodes and "::" not in b]
    _mean_td = sum(_all_td) / max(1, len(_all_td)) if _all_td else 0.5

    for bname in boot_branches:
        if bname not in nodes or "::" in bname:  # skip virtual branches
            continue
        node = nodes[bname]
        bfile = tree_dir / node.get("file", "")
        if not bfile.exists():
            continue
        try:
            branch_text = bfile.read_text(encoding="utf-8")
        except OSError:
            continue

        branch_concepts = set(re.findall(r'[a-zA-Z]{4,}', branch_text.lower()))
        if not branch_concepts:
            continue

        # Usefulness = fraction of branch concepts that appeared in session
        overlap = branch_concepts & session_concepts
        reward = len(overlap) / len(branch_concepts)  # r_t in [0, 1]

        # V2B: TD-Learning reward prediction error (Schultz, Dayan, Montague 1997)
        # delta_t = r_t + gamma * V(s_next) - V(s_t)
        # V(s_t) <- V(s_t) + alpha * delta_t
        # gamma=0.9 (future discount), alpha=0.1 (learning rate)
        _gamma = 0.9
        _alpha_td = 0.1
        v_current = node.get("td_value", 0.5)  # V(s), default 0.5
        # V(s_next) ~ mean V across all branches (mean-field Bellman backup)
        v_next = _mean_td
        delta = reward + _gamma * v_next - v_current
        v_new = v_current + _alpha_td * delta
        v_new = max(0.0, min(1.0, v_new))  # clamp [0, 1]
        node["td_value"] = round(v_new, 4)
        node["td_delta"] = round(delta, 4)  # store last delta for debugging

        # Usefulness updated via EMA as before, now also informed by TD
        # Branches with positive delta (better than expected) get boosted
        old_score = node.get("usefulness", 0.5)
        # Blend: 70% old + 30% reward, plus TD bonus (delta > 0 = surprise boost)
        td_bonus = max(0.0, delta) * 0.1  # positive surprise adds up to +0.1
        node["usefulness"] = round(max(0.0, min(1.0, 0.7 * old_score + 0.3 * reward + td_bonus)), 3)

        # V4B: EWC Fisher importance (Kirkpatrick et al. 2017)
        # F_i = proxy for how critical this branch is to system performance.
        # Computed as normalized(access_count * usefulness * td_value).
        # High-F branches get slower decay in _ebbinghaus_recall.
        _ac = node.get("access_count", 0)
        _u = node["usefulness"]
        _tv = node.get("td_value", 0.5)
        # Raw Fisher: product of usage signals, normalize later
        _fisher_raw = _ac * _u * _tv
        node["_fisher_raw"] = round(_fisher_raw, 4)

        updated = True

    # V4B: Normalize Fisher importance to [0, 1] across all updated branches
    if updated:
        max_fisher = max((nodes[b].get("_fisher_raw", 0) for b in boot_branches
                          if b in nodes), default=1.0)
        for bname in boot_branches:
            if bname in nodes and "_fisher_raw" in nodes[bname]:
                if max_fisher > 0:
                    nodes[bname]["fisher_importance"] = round(
                        nodes[bname]["_fisher_raw"] / max_fisher, 4)
                else:
                    nodes[bname]["fisher_importance"] = 0.0
                del nodes[bname]["_fisher_raw"]

    if updated:
        _m.save_tree(tree)


class _MuninnLock:
    """Self-healing file lock: mkdir atomicity + PID check + heartbeat + max age.

    Three layers of stale detection (any one triggers cleanup):
    1. PID check — owner process dead? Remove immediately.
    2. Heartbeat — owner hasn't written heartbeat in 120s? Zombie. Remove.
    3. Max age — lock older than 1h? Unconditional remove. No lock should last that long.

    The owner writes a heartbeat file every ~60s via touch_heartbeat().
    Long-running operations (feed_history, feed_watch) must call it periodically.
    """
    STALE_SECONDS = 300     # 5 min — fallback time-based detection
    HEARTBEAT_STALE = 120   # 2 min — if heartbeat not refreshed, owner is stuck
    MAX_AGE_SECONDS = 3600  # 1h — absolute maximum, unconditional removal

    def __init__(self, repo_path: Path, name: str = "hook", timeout: int = 120):
        self.lock_dir = repo_path / ".muninn" / f"{name}.lock"
        self.pid_file = self.lock_dir / "pid"
        self.heartbeat_file = self.lock_dir / "heartbeat"
        self.timeout = timeout
        self._repo_path = repo_path

    def _is_pid_alive(self, pid: int) -> bool:
        """Check if process with given PID is still running."""
        try:
            if sys.platform == "win32":
                import ctypes
                kernel32 = ctypes.windll.kernel32
                # PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
                handle = kernel32.OpenProcess(0x1000, False, pid)
                if not handle:
                    return False
                # STILL_ACTIVE = 259
                exit_code = ctypes.c_ulong()
                if kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    kernel32.CloseHandle(handle)
                    return exit_code.value == 259  # STILL_ACTIVE
                kernel32.CloseHandle(handle)
                return False
            else:
                os.kill(pid, 0)
                return True
        except (OSError, PermissionError, AttributeError):
            return False

    def _is_lock_stale(self) -> bool:
        """Three-layer stale detection. Returns True if lock should be force-removed."""
        # Layer 1: PID check — is the owner process dead?
        try:
            if self.pid_file.exists():
                owner_pid = int(self.pid_file.read_text(encoding="utf-8").strip())
                if not self._is_pid_alive(owner_pid):
                    _hook_log(self._repo_path, f"STALE LOCK: PID {owner_pid} dead")
                    return True
        except (OSError, ValueError):
            pass

        # Layer 2: Heartbeat — is the owner stuck/frozen?
        try:
            if self.heartbeat_file.exists():
                hb_age = time.time() - self.heartbeat_file.stat().st_mtime
                if hb_age > self.HEARTBEAT_STALE:
                    _hook_log(self._repo_path, f"STALE LOCK: heartbeat {hb_age:.0f}s old (limit {self.HEARTBEAT_STALE}s)")
                    return True
        except OSError:
            pass

        # Layer 3: Max age — absolute limit, no lock should live this long
        try:
            lock_age = time.time() - self.lock_dir.stat().st_mtime
            if lock_age > self.MAX_AGE_SECONDS:
                _hook_log(self._repo_path, f"STALE LOCK: age {lock_age:.0f}s exceeds max {self.MAX_AGE_SECONDS}s")
                return True
            # Fallback: mtime-based (original behavior)
            if lock_age > self.STALE_SECONDS:
                return True
        except OSError:
            pass

        return False

    def touch_heartbeat(self):
        """Update heartbeat timestamp. Call this periodically in long operations."""
        try:
            self.heartbeat_file.write_text(str(time.time()), encoding="utf-8")
        except OSError:
            pass

    def __enter__(self):
        deadline = time.time() + self.timeout
        while True:
            try:
                self.lock_dir.mkdir(parents=True, exist_ok=False)
                # Write PID + initial heartbeat
                try:
                    self.pid_file.write_text(str(os.getpid()), encoding="utf-8")
                    self.touch_heartbeat()
                except OSError:
                    pass
                return self
            except FileExistsError:
                if self._is_lock_stale():
                    import shutil
                    try:
                        _hook_log(self._repo_path, f"STALE LOCK removed: {self.lock_dir.name}")
                    except Exception:
                        pass
                    # Atomic rename to avoid TOCTOU race: if rename fails,
                    # another process already claimed the stale lock
                    stale_tmp = self.lock_dir.parent / f"{self.lock_dir.name}.stale.{os.getpid()}"
                    try:
                        self.lock_dir.rename(stale_tmp)
                    except OSError:
                        # Another process won the race — just retry
                        time.sleep(0.1)
                        continue
                    shutil.rmtree(stale_tmp, ignore_errors=True)
                    continue

                if time.time() > deadline:
                    raise TimeoutError(f"Muninn lock '{self.lock_dir}' held too long")
                time.sleep(1)

    def __exit__(self, *args):
        import shutil
        try:
            shutil.rmtree(self.lock_dir)
        except OSError:
            try:
                _hook_log(self._repo_path, f"WARN: lock dir removal failed: {self.lock_dir}")
            except Exception:
                pass


def _hook_log(repo_path: Path, message: str):
    """Append a timestamped line to .muninn/hook_log.txt for debugging."""
    try:
        log_path = repo_path / ".muninn" / "hook_log.txt"
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} {message}\n")
    except OSError:
        pass


def feed_from_hook(repo_path: Path):
    """Called by PreCompact/SessionEnd hook. Reads transcript_path from stdin JSON."""
    hook_event = "PreCompact/SessionEnd"
    _hook_log(repo_path, f"ENTER feed_from_hook (repo={repo_path.name})")
    if sys.stdin.isatty():
        print(f"MUNINN {hook_event}: no stdin (tty mode). Use 'feed --history' for manual.", file=sys.stderr)
        sys.exit(1)
    try:
        raw = sys.stdin.read()
        hook_input = json.loads(raw)
        hook_event = hook_input.get("hook_event_name", hook_event)
    except (json.JSONDecodeError, EOFError) as e:
        print(f"MUNINN {hook_event}: invalid JSON on stdin: {e}", file=sys.stderr)
        sys.exit(1)

    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        print(f"MUNINN {hook_event}: no transcript_path in hook data", file=sys.stderr)
        sys.exit(1)

    jsonl_path = Path(transcript_path)
    if not jsonl_path.exists():
        print(f"MUNINN {hook_event}: transcript not found: {_m._safe_path(jsonl_path)}", file=sys.stderr)
        sys.exit(1)

    print(f"MUNINN {hook_event}: processing {jsonl_path.name} for {repo_path.name}", file=sys.stderr)

    # Lock to prevent concurrent hooks (Stop + PreCompact) from racing on tree.json
    try:
        with _MuninnLock(repo_path, "hook", timeout=120):
            # 0. P36: Update usefulness scores before anything modifies the tree
            _update_usefulness(repo_path, jsonl_path)

            # 1. Feed mycelium (co-occurrences)
            count, parsed_texts = feed_from_transcript(jsonl_path, repo_path)
            print(f"MUNINN FEED: {count} messages -> mycelium ({repo_path.name})")

            # 2. Compress transcript into a .mn session file (reuse parsed texts)
            mn_path, session_sentiment = compress_transcript(jsonl_path, repo_path, texts=parsed_texts)

            # 3. Auto-segment into tree branches (Brique 3)
            # V6B: Pass session sentiment to branches for valence-modulated decay
            if mn_path:
                _m.grow_branches_from_session(mn_path, session_sentiment=session_sentiment)

            # 4. Refresh tree temperatures
            tree = _m.load_tree()
            _m.refresh_tree_metadata(tree)
            _m.save_tree(tree)

            # B15: Auto-prune when branches exceed cap
            # Light prune: kills dead + dust only (no L9, no consolidation)
            branch_count = len([n for n in tree["nodes"] if n != "root"])
            if branch_count > 150:
                print(f"MUNINN AUTO-PRUNE: {branch_count} branches > 150, running light prune", file=sys.stderr)
                _m._light_prune()

            # P20c: Ensure repo is registered for cross-repo discovery
            _m._register_repo(repo_path)
    except TimeoutError:
        print(f"MUNINN {hook_event}: lock timeout, skipping", file=sys.stderr)
    except Exception as e:
        _hook_log(repo_path, f"CRITICAL feed_from_hook crashed: {e}")
        print(f"MUNINN {hook_event} CRASHED: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc(file=sys.stderr)
    finally:
        # P20b: Sync to meta-mycelium — ALWAYS, even if feed/compress crashed
        # This prevents meta stalling when a single transcript hangs
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(repo_path)
            pushed = m.sync_to_meta()
            if pushed > 0:
                print(f"MUNINN SYNC: {pushed} connections -> meta-mycelium")
                _hook_log(repo_path, f"SYNC: {pushed} -> meta")
            # CHUNK 1: Auto-decay — run once per session (SessionEnd).
            # Debounced: only runs if hook_event is SessionEnd (not PreCompact
            # which can fire multiple times per session).
            if hook_event == "SessionEnd":
                dead = m.decay()
                if dead > 0:
                    m.save()
                    print(f"MUNINN DECAY: {dead} dead connections removed")
                    _hook_log(repo_path, f"DECAY: {dead} dead")
                # CHUNK 6 fix: Load tree, find cold branches, pass to consolidate.
                # _sleep_consolidate requires (cold_branches, nodes) args.
                try:
                    tree = _m.load_tree()
                    nodes = {n["name"]: n for n in tree.get("nodes", []) if isinstance(n, dict)}
                    cold = []
                    for name, node in nodes.items():
                        if name == "root":
                            continue
                        recall = _m._ebbinghaus_recall(node)
                        if recall < 0.15:
                            cold.append((name, node))
                    if cold:
                        merged = _m._sleep_consolidate(cold, nodes)
                        if merged:
                            _m.save_tree(tree)
                            _hook_log(repo_path, f"SLEEP_CONSOLIDATE: {len(merged)} merged")
                except Exception as e:
                    print(f"MUNINN CONSOLIDATE warning: {e}", file=sys.stderr)
            m.close()
        except Exception as e:
            print(f"MUNINN SYNC warning: {e}", file=sys.stderr)


def feed_from_stop_hook(repo_path: Path):
    """Called by Stop hook. Debounced: only feeds when new messages exist.

    P32: captures short conversations that never trigger PreCompact/SessionEnd.
    Uses message count dedup to avoid reprocessing the same conversation 50x.
    """
    _hook_log(repo_path, "ENTER feed_from_stop_hook")
    try:
        raw = sys.stdin.read() if not sys.stdin.isatty() else ""
    except Exception:
        raw = ""
    if not raw.strip():
        _hook_log(repo_path, "EXIT no stdin data")
        print("MUNINN STOP: no stdin data received", file=sys.stderr)
        return
    try:
        hook_input = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        print(f"MUNINN STOP: invalid JSON on stdin", file=sys.stderr)
        return

    # Note: stop_hook_active is always True in Claude Code Stop events.
    # Anti-loop protection is handled by the dedup mechanism below (line count check).

    transcript_path = hook_input.get("transcript_path")
    if not transcript_path:
        print("MUNINN STOP: no transcript_path in hook data", file=sys.stderr)
        return
    jsonl_path = Path(transcript_path)
    if not jsonl_path.exists():
        print(f"MUNINN STOP: transcript not found: {_m._safe_path(jsonl_path)}", file=sys.stderr)
        return

    session_id = hook_input.get("session_id", jsonl_path.stem)

    # Lock to prevent concurrent stop hooks from racing
    try:
        with _MuninnLock(repo_path, "hook", timeout=120):
            _feed_from_stop_hook_locked(repo_path, jsonl_path, session_id)
    except TimeoutError:
        print("MUNINN STOP: lock timeout, skipping", file=sys.stderr)


def _feed_from_stop_hook_locked(repo_path: Path, jsonl_path: Path, session_id: str):
    """Inner stop hook logic, called under lock."""
    # Count messages in transcript for dedup
    try:
        with open(jsonl_path, encoding="utf-8", errors="replace") as f:
            msg_count = sum(1 for _ in f)
    except OSError:
        return
    if msg_count == 0:
        return

    # Dedup file: {session_id: last_fed_count}
    dedup_path = repo_path / ".muninn" / "stop_dedup.json"
    dedup = {}
    if dedup_path.exists():
        try:
            dedup = json.loads(dedup_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            dedup = {}

    last_count = dedup.get(session_id, 0)
    if msg_count <= last_count:
        return  # Nothing new, skip

    # New messages detected — feed the full conversation
    print(f"MUNINN STOP: {msg_count - last_count} new messages (session {session_id[:8]})")

    # 0. P36: Update usefulness scores
    _update_usefulness(repo_path, jsonl_path)

    try:
        # 1. Feed mycelium
        count, parsed_texts = feed_from_transcript(jsonl_path, repo_path)
        print(f"MUNINN FEED: {count} messages -> mycelium ({repo_path.name})")

        # 2. Compress transcript (reuse parsed texts)
        mn_path, session_sentiment = compress_transcript(jsonl_path, repo_path, texts=parsed_texts)

        # 3. Auto-segment into branches
        if mn_path:
            _m.grow_branches_from_session(mn_path, session_sentiment=session_sentiment)

        # 4. Refresh tree
        tree = _m.load_tree()
        _m.refresh_tree_metadata(tree)
        _m.save_tree(tree)

        # P20c: Ensure repo is registered for cross-repo discovery
        _m._register_repo(repo_path)
    except Exception as e:
        _hook_log(repo_path, f"STOP feed error: {e}")
        print(f"MUNINN STOP feed error: {e}", file=sys.stderr)
    finally:
        # 5. Sync to meta-mycelium — ALWAYS, even if feed crashed
        try:
            if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
            from mycelium import Mycelium
            m = Mycelium(repo_path)
            pushed = m.sync_to_meta()
            if pushed > 0:
                print(f"MUNINN SYNC: {pushed} connections -> meta-mycelium")
                _hook_log(repo_path, f"STOP sync: {pushed} -> meta")
        except Exception as e:
            print(f"MUNINN SYNC warning: {e}", file=sys.stderr)

    # 6. Update dedup — keep only last 20 sessions
    dedup[session_id] = msg_count
    if len(dedup) > 20:
        oldest = sorted(dedup.keys())[:len(dedup) - 20]  # session_ids are timestamp-based, lexicographic = chronological
        for k in oldest:
            del dedup[k]
    _m._atomic_json_write(dedup_path, dedup)


def feed_history(repo_path: Path):
    """Feed mycelium from all past transcript JSONL files for this project.

    Scans ~/.claude/projects/<project>/ for .jsonl files and digests them.
    Tracks which files have been digested in .muninn/fed_transcripts.json.
    """
    if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
    from mycelium import Mycelium

    # Find the project's transcript directory
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        print(f"ERROR: claude projects directory not found")
        sys.exit(1)

    # Find matching project dirs (repo name encoded in path)
    repo_name = repo_path.name
    project_dirs = []
    for d in claude_dir.iterdir():
        if d.is_dir() and d.name.lower().endswith(f"-{repo_name.lower()}"):
            project_dirs.append(d)

    if not project_dirs:
        print(f"  No project directories found matching '{repo_name}'")
        return

    # Load already-fed transcript list
    muninn_dir = repo_path / ".muninn"
    muninn_dir.mkdir(exist_ok=True)
    fed_path = muninn_dir / "fed_transcripts.json"
    fed = set()
    if fed_path.exists():
        try:
            with open(fed_path, encoding="utf-8") as f:
                fed = set(json.load(f))
        except (json.JSONDecodeError, ValueError, TypeError):
            print("WARNING: fed_transcripts.json corrupted, resetting", file=sys.stderr)

    # Lock to prevent concurrent history + hook from racing
    m = Mycelium(repo_path)
    total_messages = 0
    new_files = 0

    try:
        with _MuninnLock(repo_path, "hook", timeout=120) as lock:
            _last_hb = time.time()
            for project_dir in project_dirs:
                # Top-level .jsonl files (main sessions)
                for jsonl_file in sorted(project_dir.glob("*.jsonl")):
                    file_key = str(jsonl_file)
                    if file_key in fed:
                        continue

                    texts = parse_transcript(jsonl_file)
                    if texts:
                        m.start_session()
                        for text in texts:
                            m.observe_text(text)
                            # Heartbeat every 60s so lock doesn't look stale
                            if time.time() - _last_hb > 60:
                                lock.touch_heartbeat()
                                _last_hb = time.time()
                        total_messages += len(texts)
                        new_files += 1

                    fed.add(file_key)

                    # Checkpoint every file (not all-or-nothing)
                    if new_files % 3 == 0:
                        m.save()
                        _m._atomic_json_write(fed_path, sorted(fed))
                        lock.touch_heartbeat()
                        _last_hb = time.time()

                # Subagent transcripts (top-level and inside session subdirectories)
                subagent_dirs = []
                top_sa = project_dir / "subagents"
                if top_sa.exists():
                    subagent_dirs.append(top_sa)
                for sub_dir in project_dir.iterdir():
                    if sub_dir.is_dir():
                        sa_dir = sub_dir / "subagents"
                        if sa_dir.exists():
                            subagent_dirs.append(sa_dir)

                for sa_dir in subagent_dirs:
                    for jsonl_file in sorted(sa_dir.glob("*.jsonl")):
                        file_key = str(jsonl_file)
                        if file_key in fed:
                            continue
                        texts = parse_transcript(jsonl_file)
                        if texts:
                            m.start_session()
                            for text in texts:
                                m.observe_text(text)
                                if time.time() - _last_hb > 60:
                                    lock.touch_heartbeat()
                                    _last_hb = time.time()
                            total_messages += len(texts)
                            new_files += 1
                        fed.add(file_key)

            if total_messages > 0:
                m.save()

            # Save fed list
            _m._atomic_json_write(fed_path, sorted(fed))
    except TimeoutError:
        print("MUNINN HISTORY: lock timeout, skipping", file=sys.stderr)
        return

    print(f"=== MUNINN FEED HISTORY ===")
    print(f"  New transcripts: {new_files}")
    print(f"  Messages digested: {total_messages}")
    print(f"  Total fed transcripts: {len(fed)}")
    if total_messages > 0:
        print(f"\n{m.status()}")

    # Compress transcripts into .mn and auto-segment into branches
    # M8 fix: track compressed files by path (not stem — stems don't match .mn timestamps)
    sessions_dir = repo_path / ".muninn" / "sessions"
    sessions_dir.mkdir(parents=True, exist_ok=True)
    compressed_path = muninn_dir / "compressed_transcripts.json"
    compressed = {}
    if compressed_path.exists():
        try:
            with open(compressed_path, encoding="utf-8") as f:
                raw = json.load(f)
                # Handle both old format (list) and new format (dict)
                if isinstance(raw, list):
                    compressed = {k: {} for k in raw}
                else:
                    compressed = raw
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    for project_dir in project_dirs:
        for jsonl_file in sorted(project_dir.glob("*.jsonl")):
            file_key = str(jsonl_file)
            if file_key in compressed:
                continue
            mn_path, _sent = compress_transcript(jsonl_file, repo_path)
            if mn_path:
                created = _m.grow_branches_from_session(mn_path, session_sentiment=_sent)
                if created > 0:
                    print(f"  {jsonl_file.name}: {created} branches created")
            compressed[file_key] = {"mn_file": mn_path.name if mn_path else None}
    _m._atomic_json_write(compressed_path, compressed)

    # Refresh tree
    tree = _m.load_tree()
    _m.refresh_tree_metadata(tree)
    _m.save_tree(tree)


def feed_watch(repo_path: Path):
    """P41: Poll-based feed — scans active transcripts every N minutes.

    Finds the Claude project dir for this repo, checks each .jsonl for size
    changes since last poll, and feeds only those that grew. Uses
    .muninn/watch_state.json to track {filename: last_size_bytes}.
    Zero work if nothing changed.
    """
    _hook_log(repo_path, "ENTER feed_watch")

    # Find project dir
    claude_dir = Path.home() / ".claude" / "projects"
    if not claude_dir.exists():
        print(f"MUNINN WATCH: claude projects directory not found", file=sys.stderr)
        return

    repo_name = repo_path.name
    project_dirs = [d for d in claude_dir.iterdir()
                    if d.is_dir() and d.name.lower().endswith(f"-{repo_name.lower()}")]
    if not project_dirs:
        print(f"MUNINN WATCH: no project dir for '{repo_name}'", file=sys.stderr)
        return

    # Load watch state
    state_path = repo_path / ".muninn" / "watch_state.json"
    state = {}
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            state = {}

    # Find transcripts that grew or have incomplete feed
    changed = []
    changed_keys = {}  # jsonl_path -> state key (for deferred state update)
    for project_dir in project_dirs:
        for jsonl_file in project_dir.glob("*.jsonl"):
            key = f"{project_dir.name}/{jsonl_file.name}"
            try:
                current_size = jsonl_file.stat().st_size
            except OSError:
                continue
            last_size = state.get(key, 0)
            if current_size > last_size:
                changed.append(jsonl_file)
                changed_keys[str(jsonl_file)] = (key, current_size)
            elif last_size > 0:
                # B.4 fix: check if prior feed was incomplete (state says done but
                # compress/branches may have failed). Re-include if .mn session
                # doesn't exist for this file yet. feed_from_transcript handles
                # "already complete" efficiently via feed_progress.json offset check.
                sessions_dir = repo_path / ".muninn" / "sessions"
                if sessions_dir.exists():
                    # Simple heuristic: if state recorded this file but no session
                    # was created in the last 24h, retry the compress+grow pipeline
                    from datetime import datetime
                    recent_sessions = [
                        s for s in sessions_dir.glob("*.mn")
                        if (datetime.now().timestamp() - s.stat().st_mtime) < 86400
                    ]
                    if not recent_sessions:
                        changed.append(jsonl_file)
                        changed_keys[str(jsonl_file)] = (key, current_size)

    if not changed:
        _hook_log(repo_path, "EXIT watch: nothing changed")
        return

    print(f"MUNINN WATCH: {len(changed)} transcript(s) changed")

    # Lock to prevent concurrent watch + hook from racing
    fed_count = 0
    try:
        with _MuninnLock(repo_path, "hook", timeout=120) as lock:
            for jsonl_path in changed:
                lock.touch_heartbeat()
                try:
                    _hook_log(repo_path, f"WATCH feeding {jsonl_path.name}")

                    # Step 1: Feed mycelium (chunked + resumable — survives timeout)
                    count, parsed_texts = feed_from_transcript(jsonl_path, repo_path)
                    print(f"  FEED: {count} messages -> mycelium ({jsonl_path.name})")

                    # Step 2: Compress transcript (reuse parsed texts)
                    mn_path, _sent = compress_transcript(jsonl_path, repo_path, texts=parsed_texts)

                    # Step 3: Auto-segment into branches
                    if mn_path:
                        _m.grow_branches_from_session(mn_path, session_sentiment=_sent)

                    # Save state AFTER full pipeline (feed+compress+grow) succeeds
                    ck = changed_keys.get(str(jsonl_path))
                    if ck:
                        state[ck[0]] = ck[1]
                    _m._atomic_json_write(state_path, state)

                    fed_count += 1
                    _hook_log(repo_path, f"WATCH fed ok {jsonl_path.name}: {count} msgs")
                except Exception as e:
                    print(f"  WATCH error on {jsonl_path.name}: {e}", file=sys.stderr)
                    _hook_log(repo_path, f"WATCH error {jsonl_path.name}: {e}")
                    import traceback
                    traceback.print_exc(file=sys.stderr)

            if fed_count > 0:
                # Refresh tree
                tree = _m.load_tree()
                _m.refresh_tree_metadata(tree)
                _m.save_tree(tree)
                _m._register_repo(repo_path)

            # Sync to meta-mycelium — ALWAYS, even if fed_count == 0
            # Local mycelium may have been updated by boot/recall/inject/other paths
            try:
                if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
                from mycelium import Mycelium
                m = Mycelium(repo_path)
                pushed = m.sync_to_meta()
                if pushed > 0:
                    print(f"  SYNC: {pushed} connections -> meta-mycelium")
                    _hook_log(repo_path, f"WATCH sync: {pushed} -> meta")
            except Exception as e:
                print(f"  SYNC warning: {e}", file=sys.stderr)
    except TimeoutError:
        print("MUNINN WATCH: lock timeout, skipping", file=sys.stderr)
        return

    _hook_log(repo_path, f"WATCH done: {fed_count}/{len(changed)} transcript(s) fed")


def ingest(filepath: Path, repo_path: Path):
    """Ingest a reference document (or all .md in a folder) into the tree as permanent branches.

    Compresses with full pipeline (L1-L7+L9), then auto-segments into branches.
    Use case: bibles UX, docs de reference, specs — anything you want available via boot.
    """
    files_to_ingest = []
    if filepath.is_dir():
        files_to_ingest = sorted(filepath.glob("**/*.md"))
        if not files_to_ingest:
            files_to_ingest = sorted(filepath.glob("**/*.txt"))
        # Also include LaTeX sources
        files_to_ingest.extend(sorted(filepath.glob("**/*.tex")))
        print(f"=== MUNINN INGEST: {filepath.name} ({len(files_to_ingest)} files) ===")
    elif filepath.is_file():
        files_to_ingest = [filepath]
        print(f"=== MUNINN INGEST: {filepath.name} ===")
    else:
        print(f"ERROR: {_m._safe_path(filepath)} not found")
        return

    total_branches = 0
    total_original = 0
    total_compressed = 0

    for f in files_to_ingest:
        content = f.read_text(encoding="utf-8", errors="replace")
        if len(content.strip()) < 50:
            continue

        total_original += token_count(content)

        # Compress with full pipeline
        compressed = _m.compress_file(f)
        total_compressed += token_count(compressed)

        # Write as .mn in repo's .muninn/tree/ for auto-segmentation
        mn_dir = repo_path / ".muninn" / "tree"
        mn_dir.mkdir(parents=True, exist_ok=True)
        mn_temp = mn_dir / f"_ingest_{f.stem}.mn"
        mn_temp.write_text(compressed, encoding="utf-8")

        # Auto-segment into branches
        created = _m.grow_branches_from_session(mn_temp)
        total_branches += created

        # Clean up temp file (branches are already stored)
        if mn_temp.exists():
            mn_temp.unlink()

        orig_tok = token_count(content)
        comp_tok = token_count(compressed)
        ratio = orig_tok / max(comp_tok, 1)
        print(f"  {f.name}: {orig_tok} -> {comp_tok} tokens (x{ratio:.1f}), {created} branches")

    # Nourrit aussi le mycelium avec le contenu
    if _m._CORE_DIR not in sys.path: sys.path.insert(0, _m._CORE_DIR)
    from mycelium import Mycelium
    m = Mycelium(repo_path)
    m.start_session()
    for f in files_to_ingest:
        content = f.read_text(encoding="utf-8", errors="replace")
        if content.strip():
            clean = _redact_secrets_text(content)
            if f.suffix == ".tex":
                m.observe_latex(clean)
            else:
                m.observe_text(clean)
    m.save()

    # Refresh tree
    tree = _m.load_tree()
    _m.refresh_tree_metadata(tree)
    _m.save_tree(tree)

    ratio = total_original / max(total_compressed, 1)
    print(f"\n  Total: {total_original} -> {total_compressed} tokens (x{ratio:.1f})")
    print(f"  Branches created: {total_branches}")
    print(f"  Mycelium updated")


