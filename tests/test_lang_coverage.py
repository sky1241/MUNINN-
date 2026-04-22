"""Test anchor coverage on all corpus languages with all fixes."""
import sys, re, os
sys.stdout.reconfigure(encoding='utf-8', errors='replace')
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from engine.core.cube import subdivide_file, extract_ast_hints, normalize_content, enrich_hints_with_file_context

corpus = os.path.join(os.path.dirname(__file__), 'cube_corpus')
files = {
    'Python': 'analytics.py',
    'Rust': 'cache.rs',
    'C': 'allocator.c',
    'JSX': 'components.jsx',
    'TypeScript': 'store.ts',
    'COBOL': 'banking.cob',
    'Kotlin': 'pipeline.kt',
    'Go': 'server.go',
}

_RET_KW = {'nil', 'err', 'true', 'false', 'ok', 'none', 'None', 'null', 'undefined'}


def build_full_anchor_map(tc, hints, ol, n, ext, known_idents):
    am = {}
    if hints.get('first_line'):
        am[0] = hints['first_line']
    if hints.get('last_line'):
        am[n - 1] = hints['last_line']
    if hints.get('anchors'):
        for ln, lt in hints['anchors']:
            idx = ln - 1
            if 0 <= idx < n:
                am[idx] = lt
    # Constants
    for cl in hints.get('constant_lines', []):
        cn = re.sub(r'\s+', ' ', cl.strip())
        for idx in range(n):
            if idx not in am:
                on = re.sub(r'\s+', ' ', ol[idx].strip())
                if cn and cn == on:
                    am[idx] = ol[idx]
    # Struct fields with tags
    for idx in range(n):
        if idx not in am:
            line = ol[idx]
            if '`' in line and ('json:' in line or 'xml:' in line or 'yaml:' in line):
                am[idx] = line
    # Fix 6: closing braces + structural closers
    for idx in range(n):
        if idx not in am:
            s = ol[idx].strip()
            if s in ('}', '});', '})', '};', '} else {', '},', '/>', ')', ');'):
                am[idx] = ol[idx]
    # Fix 7+8: defer + blank
    for idx in range(n):
        if idx not in am:
            s = ol[idx].strip()
            if s.startswith('defer ') and ('Unlock()' in s or 'Close()' in s or 'cancel()' in s):
                am[idx] = ol[idx]
            elif s == '':
                am[idx] = ''
    # Fix 9: strings
    ks = set(hints.get('strings', []))
    for idx in range(n):
        if idx not in am:
            line = ol[idx]
            for s in ks:
                if len(s) >= 3 and s in line:
                    am[idx] = line
                    break
    # Fix 10: func decl + struct field
    for idx in range(n):
        if idx not in am:
            s = ol[idx].strip()
            if s.startswith('func ') and '(' in s:
                am[idx] = ol[idx]
            elif s.startswith('def ') and ':' in s:
                am[idx] = ol[idx]
            elif s.startswith('class ') and ':' in s:
                am[idx] = ol[idx]
            else:
                m2 = re.match(r'(\w+):\s+\S', s)
                if m2 and (s.endswith(',') or s.endswith('{')):
                    if m2.group(1) in known_idents:
                        am[idx] = ol[idx]
    # Fix 11: Lock
    for idx in range(n):
        if idx not in am:
            s = ol[idx].strip()
            if '.Lock()' in s or '.RLock()' in s or '.RUnlock()' in s:
                am[idx] = ol[idx]
    # Fix 12: return known
    for idx in range(n):
        if idx not in am:
            s = ol[idx].strip()
            if s.startswith('return '):
                tokens = re.findall(r'[a-zA-Z_]\w*', s[7:])
                if tokens and all(t in known_idents or t in _RET_KW for t in tokens):
                    am[idx] = ol[idx]
    # Fix 13: all idents known
    for idx in range(n):
        if idx not in am:
            s = ol[idx].strip()
            if not s or s in ('{', '}'):
                continue
            tokens = re.findall(r'[a-zA-Z_]\w+', s)
            if len(tokens) >= 2 and all(t in known_idents or t in _RET_KW for t in tokens):
                am[idx] = ol[idx]
    # Fix 14: Python
    if ext == '.py':
        for idx in range(n):
            if idx not in am:
                s = ol[idx].strip()
                fw = s.split()[0].rstrip(':') if s.split() else ''
                if fw in ('else', 'elif', 'except', 'finally', 'pass', 'break', 'continue', 'raise'):
                    am[idx] = ol[idx]
                elif s.startswith('@'):
                    am[idx] = ol[idx]
    # Fix 15: Rust
    if ext == '.rs':
        for idx in range(n):
            if idx not in am:
                s = ol[idx].strip()
                if s.startswith('#[') or s.startswith('#!['):
                    am[idx] = ol[idx]
                elif re.search(r'\w+!\s*[\(\[\{]', s):
                    am[idx] = ol[idx]
                elif re.search(r"'[a-z]", s):
                    am[idx] = ol[idx]
    # Fix 16: JSX
    if ext in ('.jsx', '.tsx'):
        for idx in range(n):
            if idx not in am:
                s = ol[idx].strip()
                if s.startswith('<') and not s.startswith('<=') and not s.startswith('<<'):
                    am[idx] = ol[idx]
                elif re.match(r'\w+={', s) or re.match(r'\w+="', s):
                    am[idx] = ol[idx]
    # Fix 17: C preprocessor
    if ext in ('.c', '.h', '.cpp', '.hpp', '.cc'):
        for idx in range(n):
            if idx not in am:
                s = ol[idx].strip()
                if s.startswith('#'):
                    am[idx] = ol[idx]
    # Fix 18: COBOL
    if ext in ('.cob', '.cbl', '.cobol'):
        for idx in range(n):
            if idx not in am:
                s = ol[idx].strip()
                u = s.upper()
                if 'DIVISION' in u or 'SECTION' in u or u.startswith('END-') or u.endswith('.'):
                    am[idx] = ol[idx]
    # TS/JS
    if ext in ('.ts', '.js'):
        for idx in range(n):
            if idx not in am:
                s = ol[idx].strip()
                if (s.startswith('interface ') or s.startswith('type ') or
                        s.startswith('enum ') or s.startswith('import ') or
                        s.startswith('export ')):
                    am[idx] = ol[idx]
    return am


for lang, fname in files.items():
    fpath = os.path.join(corpus, fname)
    ext = os.path.splitext(fpath)[1].lower()
    with open(fpath, 'r', encoding='utf-8', errors='replace') as fh:
        content = fh.read()
    cubes = subdivide_file(content=content, file_path=fpath, target_tokens=112)

    total_lines = 0
    total_anchors = 0
    zero_gap = 0

    for tc in cubes:
        orig = normalize_content(tc.content)
        ol = orig.split('\n')
        n = len(ol)
        hints = extract_ast_hints(tc)
        hints['_raw_content'] = tc.content
        hints = enrich_hints_with_file_context(hints, content)
        ki = set(hints.get('identifiers', []))
        am = build_full_anchor_map(tc, hints, ol, n, ext, ki)
        total_lines += n
        total_anchors += len(am)
        if len(am) == n:
            zero_gap += 1

    gaps = total_lines - total_anchors
    pct = 100 * total_anchors / total_lines if total_lines else 0
    gap_pct = 100 * gaps / total_lines if total_lines else 0
    print(f'{lang:>12} ({fname:>15}): {len(cubes):>3} cubes, '
          f'{total_lines:>5} lines, {total_anchors:>5} anchors ({pct:.0f}%), '
          f'{gaps:>4} gaps ({gap_pct:.0f}%), {zero_gap} auto-SHA')
