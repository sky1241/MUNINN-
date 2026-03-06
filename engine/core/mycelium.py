#!/usr/bin/env python3
"""
Muninn Mycelium — Living co-occurrence network for semantic compression.

The mycelium tracks which concepts appear together across sessions.
Concepts that co-occur frequently get fused into compact blocks.
The mycelium grows, persists on disk, and decays when unused.

Like Yggdrasil's mycelium tracks co-occurrences across 348M papers,
Muninn's mycelium tracks co-occurrences across user sessions.

Usage:
    from mycelium import Mycelium
    m = Mycelium(repo_path)
    m.observe(["bug", "codec", "utf8"])   # record co-occurrence
    m.observe(["scan", "pipeline", "chunks"])
    m.save()                               # persist to disk
    fused = m.get_fusions()                # get fused concept blocks
    m.decay()                              # weaken old connections
"""
import io
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

if sys.stdout.encoding != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")


class Mycelium:
    """A living co-occurrence network that grows with each session."""

    FUSION_THRESHOLD = 5      # co-occur N times -> fuse into one block
    DECAY_HALF_LIFE = 30      # days before connection strength halves
    MAX_CONNECTIONS = 500      # cap to prevent unbounded growth
    MIN_CONCEPT_LEN = 3       # ignore tiny words

    def __init__(self, repo_path: Path):
        self.repo_path = Path(repo_path).resolve()
        self.mycelium_dir = self.repo_path / ".muninn"
        self.mycelium_path = self.mycelium_dir / "mycelium.json"
        self.data = self._load()

    def _load(self) -> dict:
        """Load mycelium from disk or create fresh."""
        if self.mycelium_path.exists():
            with open(self.mycelium_path, encoding="utf-8") as f:
                return json.load(f)
        return {
            "version": 1,
            "repo": self.repo_path.name,
            "created": time.strftime("%Y-%m-%d"),
            "updated": time.strftime("%Y-%m-%d"),
            "session_count": 0,
            "connections": {},
            "fusions": {},
        }

    def save(self):
        """Persist mycelium to disk (atomic write via tempfile + rename)."""
        import tempfile
        self.mycelium_dir.mkdir(exist_ok=True)
        self.data["updated"] = time.strftime("%Y-%m-%d")
        # Write to temp file first, then atomic rename
        fd, tmp_path = tempfile.mkstemp(
            dir=str(self.mycelium_dir), suffix=".tmp", prefix="mycelium_"
        )
        try:
            with open(fd, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            import os
            os.replace(tmp_path, str(self.mycelium_path))
        except Exception:
            # Clean up temp file on failure
            import os
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)
            raise

    def _key(self, a: str, b: str) -> str:
        """Canonical key for a pair (alphabetical order)."""
        return f"{min(a,b)}|{max(a,b)}"

    def observe(self, concepts: list[str]):
        """Record co-occurrence of concepts in this context.

        Every pair of concepts in the list gets a +1 connection strength.
        This is called when processing user input or compressing text.
        """
        # Filter and normalize
        clean = []
        for c in concepts:
            c = c.lower().strip()
            if len(c) >= self.MIN_CONCEPT_LEN and c not in _STOPWORDS:
                clean.append(c)

        clean = list(set(clean))  # deduplicate

        conns = self.data["connections"]

        # Record all pairs
        for i in range(len(clean)):
            for j in range(i + 1, len(clean)):
                key = self._key(clean[i], clean[j])
                if key not in conns:
                    conns[key] = {
                        "count": 0,
                        "first_seen": time.strftime("%Y-%m-%d"),
                        "last_seen": time.strftime("%Y-%m-%d"),
                    }
                conns[key]["count"] += 1
                conns[key]["last_seen"] = time.strftime("%Y-%m-%d")

        # Check for new fusions
        self._check_fusions()

        # Enforce max connections (prune weakest)
        if len(conns) > self.MAX_CONNECTIONS:
            self._prune_weakest()

    def observe_text(self, text: str):
        """Extract concepts from raw text and observe co-occurrences.

        Works on any text — user messages, code, documentation.
        Extracts meaningful words (4+ chars, not stopwords).
        """
        # Extract words
        words = re.findall(r'[A-Za-zÀ-ÿ_]{4,}', text)
        word_counts = Counter(w.lower() for w in words)

        # Keep all meaningful words (4+ chars, not stopwords)
        concepts = []
        for word, count in word_counts.items():
            if word in _STOPWORDS:
                continue
            concepts.append(word)

        # Also extract capitalized entities from original text
        entities = re.findall(r'[A-Z][a-z]{3,}(?:\s+[A-Z][a-z]+)*', text)
        for entity in entities:
            e = entity.lower()
            if e not in _STOPWORDS and len(e) >= 4:
                concepts.append(e)

        concepts = list(set(concepts))

        if len(concepts) >= 2:
            self.observe(concepts)

    def _check_fusions(self):
        """Check if any connections crossed the fusion threshold."""
        conns = self.data["connections"]
        fusions = self.data["fusions"]

        for key, conn in conns.items():
            if conn["count"] >= self.FUSION_THRESHOLD:
                if key not in fusions:
                    a, b = key.split("|")
                    fused_form = f"{a}+{b}"
                    fusions[key] = {
                        "concepts": [a, b],
                        "form": fused_form,
                        "strength": conn["count"],
                        "fused_at": time.strftime("%Y-%m-%d"),
                    }
                else:
                    # Update strength to match current count
                    fusions[key]["strength"] = conn["count"]

    def _prune_weakest(self):
        """Remove weakest connections to stay under MAX_CONNECTIONS."""
        conns = self.data["connections"]
        sorted_keys = sorted(conns.keys(), key=lambda k: conns[k]["count"])
        while len(conns) > self.MAX_CONNECTIONS:
            weakest = sorted_keys.pop(0)
            # Don't prune fused connections
            if weakest not in self.data["fusions"]:
                del conns[weakest]

    def decay(self, days: int = None):
        """Weaken connections that haven't been seen recently.

        Connections that haven't been reinforced decay over time.
        Dead connections (count drops to 0) are removed.
        """
        if days is None:
            days = self.DECAY_HALF_LIFE

        today = time.strftime("%Y-%m-%d")
        conns = self.data["connections"]
        dead = []

        for key, conn in conns.items():
            try:
                from datetime import datetime
                last = datetime.strptime(conn["last_seen"], "%Y-%m-%d")
                now = datetime.strptime(today, "%Y-%m-%d")
                age_days = (now - last).days
            except (ValueError, KeyError):
                age_days = 0

            if age_days > days:
                # Halve the count for each half-life period passed
                periods = age_days // days
                new_count = conn["count"] >> periods  # integer division by 2^periods
                if new_count <= 0:
                    dead.append(key)
                else:
                    conn["count"] = new_count

        # Remove dead connections and their fusions
        for key in dead:
            del conns[key]
            if key in self.data["fusions"]:
                del self.data["fusions"][key]

        return len(dead)

    def get_fusions(self) -> dict:
        """Get all fused concept blocks.

        Returns dict of {key: {concepts, form, strength}}.
        These are concept pairs that co-occur so often they should
        be compressed as a single unit.
        """
        return self.data.get("fusions", {})

    def get_compression_rules(self) -> dict:
        """Generate compression rules from the mycelium.

        Returns a dict {pattern: replacement} for the compressor.
        Strongest fusions -> shortest codes.
        """
        fusions = self.get_fusions()
        if not fusions:
            return {}

        # Sort by strength (most fused first)
        ranked = sorted(fusions.items(), key=lambda x: x[1]["strength"], reverse=True)

        rules = {}
        for key, fusion in ranked:
            concepts = fusion["concepts"]
            # The compression rule: when both concepts appear nearby,
            # they can be referenced as a single block
            rules[key] = {
                "concepts": concepts,
                "form": fusion["form"],
                "strength": fusion["strength"],
            }

        return rules

    def get_learned_fillers(self) -> list[str]:
        """Identify filler words from the mycelium.

        A filler = a word that appears in MANY connections but NEVER fuses.
        High connectivity + zero fusion = noise word, carries no information.
        These are candidates for L2 (filler word removal).
        """
        conns = self.data["connections"]
        fusions = self.data["fusions"]

        if not conns:
            return []

        # Count how many connections each concept participates in
        concept_conn_count = {}
        for key in conns:
            a, b = key.split("|")
            concept_conn_count[a] = concept_conn_count.get(a, 0) + 1
            concept_conn_count[b] = concept_conn_count.get(b, 0) + 1

        # Concepts that appear in fusions
        fused_concepts = set()
        for key, fusion in fusions.items():
            for c in fusion["concepts"]:
                fused_concepts.add(c)

        # Fillers: in 10+ connections but never fused = noise
        fillers = []
        for concept, count in concept_conn_count.items():
            if count >= 10 and concept not in fused_concepts:
                fillers.append(concept)

        return sorted(fillers)

    def get_learned_abbreviations(self) -> dict:
        """Generate abbreviation rules from strong fusions.

        Only creates abbreviations when one concept is a prefix/substring
        of the other (e.g., "compression" -> "comp", "encoding" -> "enc").
        Random co-occurrences like "compression|lines" are NOT abbreviations.

        Returns dict {long_form: short_form}.
        """
        fusions = self.data["fusions"]
        if not fusions:
            return {}

        abbrevs = {}
        for key, fusion in fusions.items():
            if fusion["strength"] >= 8:
                a, b = fusion["concepts"]
                # Only abbreviate when short is a prefix of long
                # (e.g., "comp" is prefix of "compression")
                long, short = (a, b) if len(a) > len(b) else (b, a)
                if long.startswith(short) and len(short) >= 3:
                    abbrevs[long] = short
        return abbrevs

    def start_session(self):
        """Mark the beginning of a new session."""
        self.data["session_count"] = self.data.get("session_count", 0) + 1

    def status(self) -> str:
        """Print mycelium status."""
        conns = self.data["connections"]
        fusions = self.data["fusions"]
        sessions = self.data.get("session_count", 0)

        lines = [
            f"=== MUNINN MYCELIUM: {self.data['repo']} ===",
            f"  Sessions: {sessions}",
            f"  Connections: {len(conns)}",
            f"  Fusions: {len(fusions)}",
            f"  Updated: {self.data.get('updated', '?')}",
        ]

        if conns:
            # Top 10 strongest connections
            top = sorted(conns.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
            lines.append(f"\n  Top connections:")
            for key, conn in top:
                fused = " [FUSED]" if key in fusions else ""
                lines.append(f"    {key}: {conn['count']}x{fused}")

        if fusions:
            lines.append(f"\n  Fusions ({len(fusions)}):")
            for key, fusion in sorted(fusions.items(),
                                       key=lambda x: x[1]["strength"],
                                       reverse=True)[:10]:
                lines.append(f"    {fusion['concepts']} -> {fusion['form']} "
                           f"(strength={fusion['strength']})")

        return "\n".join(lines)


# Stopwords — never track these as concepts
_STOPWORDS = {
    # English
    "this", "that", "with", "from", "have", "been", "will", "would", "could",
    "should", "what", "when", "where", "which", "while", "their", "there",
    "they", "them", "then", "than", "these", "those", "each", "every",
    "some", "also", "just", "like", "make", "only", "over", "such", "after",
    "before", "into", "about", "between", "through", "during", "again",
    "further", "more", "most", "other", "very", "here", "your", "does",
    "doing", "done", "being", "were", "because", "both", "same",
    # French
    "pour", "dans", "avec", "sont", "plus", "tout", "mais", "cette",
    "comme", "elle", "nous", "vous", "leur", "faire", "peut", "bien",
    "encore", "aussi", "autre", "quand", "etre", "avoir", "fait",
    # Programming
    "print", "return", "import", "from", "self", "class", "function",
    "const", "true", "false", "none", "else", "elif", "pass", "break",
    "continue", "lambda", "yield", "async", "await", "raise", "except",
    "finally", "assert", "global", "default", "require", "module",
    "name", "type", "data", "file", "path", "list", "dict", "args",
    "kwargs", "init", "main", "test", "open", "read", "write", "close",
    "string", "number", "boolean", "object", "array", "append", "items",
    "keys", "values", "update", "float", "format", "strip", "split",
    "join", "replace", "encoding", "decode", "encode", "input", "output",
}


# ── CLI ──────────────────────────────────────────────────────────

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Muninn Mycelium — living compression network")
    parser.add_argument("command", choices=["status", "observe", "decay", "simulate"])
    parser.add_argument("repo", help="Path to the repo")
    parser.add_argument("--text", help="Text to observe (for observe command)")
    parser.add_argument("--file", help="File to observe (for observe command)")
    args = parser.parse_args()

    m = Mycelium(Path(args.repo))

    if args.command == "status":
        print(m.status())

    elif args.command == "observe":
        if args.file:
            text = Path(args.file).read_text(encoding="utf-8")
            m.observe_text(text)
            m.save()
            print(f"Observed {args.file}")
            print(m.status())
        elif args.text:
            m.observe_text(args.text)
            m.save()
            print(f"Observed text input")
            print(m.status())
        else:
            print("ERROR: --text or --file required")

    elif args.command == "decay":
        dead = m.decay()
        m.save()
        print(f"Decayed: {dead} dead connections removed")
        print(m.status())

    elif args.command == "simulate":
        # Simulate 10 sessions to show mycelium growth
        print("=== MYCELIUM GROWTH SIMULATION ===\n")
        m.start_session()

        # Simulate typical Sky sessions (20 sessions to see fusions emerge)
        sessions = [
            "bug codec utf8 encoding windows python crash fix",
            "scan pipeline chunks papers arxiv openalex data",
            "tree root branch leaf budget lines memory compression",
            "bug fix codec encoding test validation ci",
            "compression tokens memory tree root branch budget",
            "scan data pipeline chunks arxiv papers results",
            "bug codec fix encoding utf8 windows crash",
            "tree memory compression budget tokens root branch leaf",
            "scan pipeline data chunks arxiv openalex snapshot",
            "bug fix codec utf8 encoding validation test ci",
            "codec bug crash encoding utf8 fix windows",
            "pipeline scan arxiv chunks data papers openalex",
            "memory tree compression root branch tokens budget",
            "encoding codec bug fix crash validation windows",
            "tree compression memory tokens budget branch root",
            "scan arxiv pipeline chunks papers data results",
            "bug codec encoding utf8 fix crash windows python",
            "compression tree memory root branch leaf budget tokens",
            "pipeline scan chunks arxiv data openalex papers",
            "codec bug encoding utf8 fix validation crash ci",
        ]

        for i, session_text in enumerate(sessions):
            m.start_session()
            m.observe_text(session_text)
            conns = len(m.data["connections"])
            fusions = len(m.data["fusions"])
            print(f"  Session {i+1}: +observe -> {conns} connections, {fusions} fusions")

        m.save()
        print(f"\n{m.status()}")

        rules = m.get_compression_rules()
        if rules:
            print(f"\n  Compression rules generated:")
            for key, rule in rules.items():
                print(f"    {rule['concepts']} -> '{rule['form']}' (strength={rule['strength']})")


if __name__ == "__main__":
    main()
