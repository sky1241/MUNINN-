"""
B-SCAN-01: Bible Scraper
========================
Extracts vulnerability patterns from multiple sources into structured JSON per language.

Sources:
  - CORE: built-in patterns (OWASP Top 10, common CWEs). Always available, zero network.
  - CWE XML: parsed from cwec_latest.xml.zip (downloaded + cached in .muninn/scanner_sources/)
  - Semgrep YAML: parsed from semgrep-rules repo (cloned/cached in .muninn/scanner_sources/)

Output: .muninn/scanner_data/bible/{language}.json + universal.json
Format per entry:
  {id, severity, pattern, regex_per_language: {lang: regex, ...}, fix, cwe}
"""

import json
import os
import re
import zipfile
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree

_SCANNER_VERSION = "0.1.0"

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# Dataclass
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@dataclass
class BibleEntry:
    """Single vulnerability pattern."""
    id: str
    severity: str                          # CRIT / HIGH / MED / LOW / INFO
    pattern: str                           # human-readable description
    regex_per_language: dict[str, str]     # {python: "...", go: "...", ...}
    fix: str
    cwe: str                               # CWE-XX
    source: str = "core"                   # core / cwe / semgrep
    languages: list[str] = field(default_factory=list)  # which languages this applies to

    def to_dict(self) -> dict:
        return asdict(self)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CORE BIBLE — built-in, zero network, OWASP Top 10 + common CWEs
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def _core_bible() -> list[BibleEntry]:
    """Built-in vulnerability patterns. Always available."""
    entries = []

    # ── A01: Injection ──────────────────────────────────────────
    entries.append(BibleEntry(
        id="INJ-SQL", severity="CRIT",
        pattern="SQL injection via string concatenation/formatting",
        regex_per_language={
            "python": r'(?:execute|executemany|cursor\.execute)\s*\(\s*(?:["\'].*?%|f["\']|.*?\.format|.*?\+)',
            "javascript": r'(?:query|execute)\s*\(\s*(?:["\`].*?\$\{|.*?\+)',
            "go": r'(?:fmt\.Sprintf|Exec|Query|QueryRow)\s*\(.*?(?:\+|Sprintf)',
            "java": r'(?:Statement|prepareStatement|executeQuery|executeUpdate)\s*\(.*?\+',
            "ruby": r'(?:execute|select_all|find_by_sql)\s*\(.*?(?:#\{|\+)',
            "php": r'(?:mysql_query|mysqli_query|pg_query)\s*\(.*?(?:\.\s*\$|\$)',
            "c_cpp": r'(?:sqlite3_exec|mysql_query|PQexec)\s*\(.*?(?:sprintf|strcat)',
        },
        fix="Use parameterized queries / prepared statements",
        cwe="CWE-89",
    ))

    entries.append(BibleEntry(
        id="INJ-CMD", severity="CRIT",
        pattern="OS command injection via user input",
        regex_per_language={
            "python": r'(?:subprocess\.(?:call|run|Popen|check_output)|os\.(?:system|popen|exec\w*))\s*\(.*?(?:\+|%|format|f["\'])',
            "javascript": r'(?:child_process\.(?:exec|spawn|execSync)|exec)\s*\(.*?(?:\+|\$\{|`)',
            "go": r'exec\.Command\s*\(.*?(?:\+|Sprintf)',
            "java": r'Runtime\.getRuntime\(\)\.exec\s*\(.*?\+',
            "ruby": r'(?:system|exec|`.*?#\{|%x\()',
            "php": r'(?:exec|system|passthru|shell_exec|popen)\s*\(.*?\$',
            "c_cpp": r'(?:system|popen|exec\w*)\s*\(.*?(?:sprintf|strcat|argv)',
        },
        fix="Use allowlist validation, avoid shell=True, use subprocess with list args",
        cwe="CWE-78",
    ))

    entries.append(BibleEntry(
        id="INJ-XSS", severity="HIGH",
        pattern="Cross-site scripting via unescaped output",
        regex_per_language={
            "python": r'(?:render_template_string|Markup|\.safe|\|safe|innerHTML)',
            "javascript": r'(?:innerHTML|outerHTML|document\.write|\.html\(|dangerouslySetInnerHTML|v-html)',
            "go": r'(?:template\.HTML|\.Write\(.*?\+|Fprintf\(w,)',
            "java": r'(?:\.getWriter\(\)\.print|out\.println\(.*?request\.getParameter)',
            "php": r'(?:echo\s+\$_(?:GET|POST|REQUEST)|print\s+\$_)',
        },
        fix="Use context-aware output encoding, CSP headers",
        cwe="CWE-79",
    ))

    entries.append(BibleEntry(
        id="INJ-LDAP", severity="HIGH",
        pattern="LDAP injection via string concatenation",
        regex_per_language={
            "python": r'(?:ldap\.(?:search|search_s|search_ext))\s*\(.*?(?:\+|%|format)',
            "java": r'(?:search|SearchControls)\s*\(.*?(?:\+|String\.format)',
        },
        fix="Use LDAP parameter binding, sanitize special characters",
        cwe="CWE-90",
    ))

    entries.append(BibleEntry(
        id="INJ-XPATH", severity="HIGH",
        pattern="XPath injection via string concatenation",
        regex_per_language={
            "python": r'(?:xpath|find|findall)\s*\(.*?(?:\+|%|format|f["\'])',
            "java": r'(?:evaluate|compile)\s*\(.*?\+.*?(?:request|input|param)',
        },
        fix="Use parameterized XPath queries",
        cwe="CWE-643",
    ))

    # ── A02: Broken Authentication ──────────────────────────────
    entries.append(BibleEntry(
        id="AUTH-HARDCODED", severity="CRIT",
        pattern="Hardcoded password or credentials",
        regex_per_language={
            "python": r'(?i)(?:password|passwd|secret|api_key|token)\s*=\s*["\'][^"\']{4,}["\']',
            "javascript": r'(?i)(?:password|passwd|secret|apiKey|token)\s*[=:]\s*["\'][^"\']{4,}["\']',
            "go": r'(?i)(?:password|passwd|secret|apiKey|token)\s*(?::=|=)\s*"[^"]{4,}"',
            "java": r'(?i)(?:password|passwd|secret|apiKey|token)\s*=\s*"[^"]{4,}"',
            "ruby": r'(?i)(?:password|passwd|secret|api_key|token)\s*=\s*["\'][^"\']{4,}["\']',
            "php": r'(?i)(?:\$password|\$passwd|\$secret|\$api_key|\$token)\s*=\s*["\'][^"\']{4,}["\']',
            "c_cpp": r'(?i)(?:password|passwd|secret|api_key|token)\s*=\s*"[^"]{4,}"',
        },
        fix="Use environment variables or secret management (vault, KMS)",
        cwe="CWE-798",
    ))

    entries.append(BibleEntry(
        id="AUTH-WEAK-HASH", severity="HIGH",
        pattern="Weak password hashing (MD5/SHA1 for passwords)",
        regex_per_language={
            "python": r'(?:hashlib\.(?:md5|sha1)|md5\(|SHA1\()',
            "javascript": r'(?:createHash\(["\'](?:md5|sha1)["\']|MD5\(|SHA1\()',
            "go": r'(?:md5\.(?:New|Sum)|sha1\.(?:New|Sum))',
            "java": r'MessageDigest\.getInstance\(\s*["\'](?:MD5|SHA-1)["\']',
            "php": r'(?:md5\s*\(|sha1\s*\()',
        },
        fix="Use bcrypt, scrypt, or Argon2 for password hashing",
        cwe="CWE-328",
    ))

    entries.append(BibleEntry(
        id="AUTH-MISSING", severity="HIGH",
        pattern="Missing authentication check on sensitive endpoint",
        regex_per_language={
            "python": r'@app\.route\s*\(.*?(?:admin|delete|update|config).*?\)\s*\ndef\s+\w+\([^)]*\)(?:(?!@login_required|@auth|@requires_auth|@permission).)*$',
            "javascript": r'(?:router|app)\.(?:post|put|delete)\s*\(.*?(?:admin|delete|update|config)',
        },
        fix="Add authentication middleware/decorator to sensitive endpoints",
        cwe="CWE-306",
    ))

    # ── A03: Sensitive Data Exposure ────────────────────────────
    entries.append(BibleEntry(
        id="DATA-CLEARTEXT", severity="HIGH",
        pattern="Sensitive data transmitted/stored in cleartext",
        regex_per_language={
            "python": r'(?:http://(?!localhost|127\.0\.0\.1|0\.0\.0\.0)|smtp\.connect|FTP\()',
            "javascript": r'(?:http://(?!localhost|127\.0\.0\.1)|fetch\s*\(\s*["\']http://)',
            "go": r'http://(?!localhost|127\.0\.0\.1)',
            "java": r'(?:http://(?!localhost|127\.0\.0\.1)|new\s+URL\(\s*"http://)',
        },
        fix="Use HTTPS/TLS for all sensitive data in transit",
        cwe="CWE-319",
    ))

    entries.append(BibleEntry(
        id="DATA-LOG-SENSITIVE", severity="MED",
        pattern="Sensitive data written to logs",
        regex_per_language={
            "python": r'(?:log(?:ger)?\.(?:info|debug|warning|error)|print)\s*\(.*?(?:password|token|secret|ssn|credit.?card)',
            "javascript": r'console\.(?:log|info|debug|warn|error)\s*\(.*?(?:password|token|secret|ssn|credit)',
            "go": r'(?:log\.(?:Print|Printf|Println)|fmt\.Print)\s*\(.*?(?:password|token|secret)',
            "java": r'(?:log(?:ger)?\.(?:info|debug|warn|error)|System\.out\.print)\s*\(.*?(?:password|token|secret)',
        },
        fix="Redact sensitive data before logging",
        cwe="CWE-532",
    ))

    # ── A04: XXE ────────────────────────────────────────────────
    entries.append(BibleEntry(
        id="XXE-PARSE", severity="HIGH",
        pattern="XML External Entity injection (unsafe XML parsing)",
        regex_per_language={
            "python": r'(?:xml\.etree\.ElementTree\.parse|minidom\.parse|lxml\.etree\.parse|xmltodict\.parse)\s*\(',
            "java": r'(?:DocumentBuilderFactory|SAXParserFactory|XMLReader)(?!.*?setFeature.*?external)',
            "go": r'xml\.(?:Unmarshal|NewDecoder)',
            "php": r'(?:simplexml_load_string|simplexml_load_file|DOMDocument.*?loadXML)',
        },
        fix="Disable external entity processing, use defusedxml (Python)",
        cwe="CWE-611",
    ))

    # ── A05: Broken Access Control ──────────────────────────────
    entries.append(BibleEntry(
        id="AC-IDOR", severity="HIGH",
        pattern="Insecure Direct Object Reference (user-controlled ID in query)",
        regex_per_language={
            "python": r'(?:get_object_or_404|\.objects\.get|\.filter)\s*\(.*?(?:request\.(?:GET|POST|args|form))',
            "javascript": r'(?:findById|findOne|findByPk)\s*\(\s*(?:req\.params|req\.query|req\.body)',
            "go": r'(?:Find|First|Where)\s*\(.*?(?:r\.URL\.Query|r\.FormValue|c\.Param)',
            "java": r'(?:findById|getOne|getReferenceById)\s*\(\s*(?:request\.getParameter)',
        },
        fix="Verify object ownership/permissions before returning data",
        cwe="CWE-639",
    ))

    entries.append(BibleEntry(
        id="AC-PATH-TRAVERSAL", severity="CRIT",
        pattern="Path traversal via user-controlled file path",
        regex_per_language={
            "python": r'(?:open|Path|os\.path\.join)\s*\(.*?(?:request|input|args|params|argv|filename|filepath|file_path|user_file|upload)',
            "javascript": r'(?:readFile|readFileSync|createReadStream|path\.join)\s*\(.*?(?:req\.|params|query)',
            "go": r'(?:os\.Open|ioutil\.ReadFile|filepath\.Join)\s*\(.*?(?:r\.URL|r\.Form|c\.Param)',
            "java": r'(?:new\s+File|Paths\.get|FileInputStream)\s*\(.*?(?:request\.getParameter)',
            "php": r'(?:file_get_contents|fopen|include|require)\s*\(.*?\$_(?:GET|POST|REQUEST)',
        },
        fix="Validate and sanitize file paths, use allowlist, resolve canonical path",
        cwe="CWE-22",
    ))

    # ── A06: Security Misconfiguration ──────────────────────────
    entries.append(BibleEntry(
        id="CONF-DEBUG", severity="MED",
        pattern="Debug mode enabled in production",
        regex_per_language={
            "python": r'(?:DEBUG\s*=\s*True|app\.debug\s*=\s*True|FLASK_DEBUG\s*=\s*1)',
            "javascript": r'(?:NODE_ENV.*?["\']development["\']|debug\s*:\s*true)',
            "go": r'(?:gin\.SetMode\(gin\.DebugMode\)|debug\s*[:=]\s*true)',
            "java": r'(?:debug\s*=\s*"?true"?|showServerInfo\s*=\s*"?true"?)',
        },
        fix="Disable debug mode in production, use environment-based config",
        cwe="CWE-489",
    ))

    entries.append(BibleEntry(
        id="CONF-CORS-WILD", severity="MED",
        pattern="Overly permissive CORS configuration",
        regex_per_language={
            "python": r'(?:Access-Control-Allow-Origin.*?\*|CORS\(.*?origins\s*=\s*["\']?\*)',
            "javascript": r'(?:Access-Control-Allow-Origin.*?\*|origin\s*:\s*(?:true|["\']?\*))',
            "go": r'(?:Access-Control-Allow-Origin.*?\*|AllowAllOrigins\s*:\s*true)',
            "java": r'(?:addAllowedOrigin\(\s*"\*"|@CrossOrigin(?!\())',
        },
        fix="Restrict CORS to specific trusted origins",
        cwe="CWE-942",
    ))

    # ── A07: XSS (covered in INJ-XSS above) ────────────────────

    # ── A08: Insecure Deserialization ───────────────────────────
    entries.append(BibleEntry(
        id="DESER-UNSAFE", severity="CRIT",
        pattern="Unsafe deserialization of untrusted data",
        regex_per_language={
            "python": r'(?:pickle\.(?:loads?|Unpickler)|yaml\.(?:load|unsafe_load)\s*\((?!.*?Loader=yaml\.SafeLoader)|marshal\.loads?|shelve\.open)',
            "javascript": r'(?:node-serialize|serialize-javascript.*?eval|unserialize)',
            "java": r'(?:ObjectInputStream|readObject\(\)|XMLDecoder|XStream\.fromXML)',
            "ruby": r'(?:Marshal\.load|YAML\.load(?!\(.*?safe))',
            "php": r'(?:unserialize\s*\(.*?\$_(?:GET|POST|REQUEST|COOKIE)|unserialize\s*\(\s*\$)',
        },
        fix="Use safe serialization formats (JSON), validate before deserialization",
        cwe="CWE-502",
    ))

    # ── A09: Insufficient Logging ───────────────────────────────
    # (hard to detect with regex, mostly structural — skip for V1)

    # ── A10: SSRF ───────────────────────────────────────────────
    entries.append(BibleEntry(
        id="SSRF-REQUEST", severity="HIGH",
        pattern="Server-Side Request Forgery (user-controlled URL in server request)",
        regex_per_language={
            "python": r'(?:requests\.(?:get|post|put|delete|head)|urllib\.request\.urlopen|httpx\.(?:get|post))\s*\(.*?(?:request|input|args|params)',
            "javascript": r'(?:fetch|axios\.(?:get|post)|http\.request|got)\s*\(.*?(?:req\.|params|query|body)',
            "go": r'(?:http\.(?:Get|Post|NewRequest))\s*\(.*?(?:r\.URL|r\.Form|c\.Param)',
            "java": r'(?:new\s+URL|HttpURLConnection|RestTemplate)\s*\(.*?(?:request\.getParameter)',
        },
        fix="Validate/allowlist URLs, block internal IPs (169.254.x.x, 10.x, 127.x, etc.)",
        cwe="CWE-918",
    ))

    # ── Race Conditions ─────────────────────────────────────────
    entries.append(BibleEntry(
        id="RACE-SHARED", severity="HIGH",
        pattern="Shared mutable state without synchronization",
        regex_per_language={
            "go": r'go\s+func\s*\(.*?\)\s*\{[^}]*(?:\w+\s*(?:=|\+=|-=|\+\+|--))',
            "python": r'(?:threading\.Thread|concurrent\.futures)\s*\(.*?(?:target|submit).*?(?:global\s+\w+|\w+\.append|\w+\[)',
            "java": r'(?:new\s+Thread|Runnable|ExecutorService).*?(?:(?!synchronized|volatile|Atomic|Lock)\b\w+\s*(?:=|\+=))',
        },
        fix="Use mutex/locks, atomic operations, or channels (Go)",
        cwe="CWE-362",
    ))

    entries.append(BibleEntry(
        id="RACE-TOCTOU", severity="HIGH",
        pattern="Time-of-check to time-of-use race condition",
        regex_per_language={
            "python": r'(?:os\.path\.exists|os\.access)\s*\(.*?\).*?(?:open|os\.remove|os\.rename)',
            "c_cpp": r'(?:access|stat)\s*\(.*?\).*?(?:open|fopen|unlink|rename)',
            "go": r'(?:os\.Stat|os\.IsNotExist)\s*\(.*?\).*?(?:os\.Open|os\.Remove|os\.Rename)',
        },
        fix="Use atomic file operations, open with O_CREAT|O_EXCL",
        cwe="CWE-367",
    ))

    # ── Crypto ──────────────────────────────────────────────────
    entries.append(BibleEntry(
        id="CRYPTO-WEAK", severity="HIGH",
        pattern="Weak or broken cryptographic algorithm (DES, RC4, ECB mode)",
        regex_per_language={
            "python": r'(?:DES\.new|ARC4\.new|AES\.new\(.*?MODE_ECB|Blowfish)',
            "javascript": r'(?:createCipher(?:iv)?\(["\'](?:des|rc4|aes-\d+-ecb))',
            "go": r'(?:des\.NewCipher|rc4\.NewCipher|cipher\.NewECBEncrypter)',
            "java": r'(?:Cipher\.getInstance\(\s*["\'](?:DES|RC4|AES/ECB))',
        },
        fix="Use AES-256-GCM or ChaCha20-Poly1305",
        cwe="CWE-327",
    ))

    entries.append(BibleEntry(
        id="CRYPTO-RANDOM", severity="HIGH",
        pattern="Insecure random number generator for security",
        regex_per_language={
            "python": r'(?:random\.(?:random|randint|choice|randrange|sample))\s*\(',
            "javascript": r'Math\.random\s*\(\)',
            "go": r'math/rand',
            "java": r'(?:new\s+Random\(\)|Math\.random\(\))',
            "c_cpp": r'(?:rand\s*\(\)|srand\s*\()',
        },
        fix="Use secrets module (Python), crypto.randomBytes (JS), crypto/rand (Go)",
        cwe="CWE-330",
    ))

    entries.append(BibleEntry(
        id="CRYPTO-HARDCODED-KEY", severity="CRIT",
        pattern="Hardcoded cryptographic key or IV",
        regex_per_language={
            "python": r'(?i)(?:AES\.new|Fernet|HMAC)\s*\(\s*b?["\'][^"\']{8,}["\']',
            "javascript": r'(?i)(?:createCipher|createHmac|createSign)\s*\([^,]+,\s*["\'][^"\']{8,}["\']',
            "go": r'(?i)(?:aes\.NewCipher|hmac\.New)\s*\(\s*\[\]byte\s*\(\s*"[^"]{8,}"\)',
            "java": r'(?i)(?:SecretKeySpec|IvParameterSpec)\s*\(\s*"[^"]{8,}"',
        },
        fix="Use KMS or key derivation from secure source",
        cwe="CWE-321",
    ))

    # ── Input Validation ────────────────────────────────────────
    entries.append(BibleEntry(
        id="INPUT-REDIRECT", severity="MED",
        pattern="Open redirect via user-controlled URL",
        regex_per_language={
            "python": r'(?:redirect|HttpResponseRedirect)\s*\(\s*(?:request\.(?:GET|POST|args)|url_for.*?\+)',
            "javascript": r'(?:res\.redirect|window\.location|location\.href)\s*(?:=|\()\s*(?:req\.|params|query)',
            "go": r'http\.Redirect\s*\(.*?(?:r\.URL\.Query|r\.FormValue)',
            "java": r'(?:sendRedirect|forward)\s*\(\s*(?:request\.getParameter)',
        },
        fix="Validate redirect URLs against allowlist of trusted domains",
        cwe="CWE-601",
    ))

    entries.append(BibleEntry(
        id="INPUT-REGEX-DOS", severity="MED",
        pattern="ReDoS via user-controlled regex or catastrophic backtracking",
        regex_per_language={
            "python": r're\.(?:compile|match|search|findall)\s*\(.*?(?:request|input|args|params)',
            "javascript": r'new\s+RegExp\s*\(.*?(?:req\.|params|query|body|input)',
            "go": r'regexp\.(?:Compile|MustCompile)\s*\(.*?(?:r\.URL|r\.Form)',
        },
        fix="Validate/sanitize input before regex, use re2 (linear-time)",
        cwe="CWE-1333",
    ))

    # ── Error Handling ──────────────────────────────────────────
    entries.append(BibleEntry(
        id="ERR-INFO-LEAK", severity="MED",
        pattern="Detailed error messages exposed to user (stack traces, SQL errors)",
        regex_per_language={
            "python": r'(?:traceback\.(?:print_exc|format_exc)|except.*?(?:return|Response).*?(?:str\(e\)|repr\(e\)|e\.args))',
            "javascript": r'(?:catch.*?res\.(?:send|json)\s*\(.*?(?:err\.message|err\.stack|error\.message))',
            "go": r'(?:http\.Error\s*\(.*?err\.Error\(\)|fmt\.Fprintf\(w,.*?err)',
            "java": r'(?:printStackTrace\(\)|e\.getMessage\(\).*?(?:response|print|send))',
        },
        fix="Return generic error messages, log details server-side only",
        cwe="CWE-209",
    ))

    entries.append(BibleEntry(
        id="ERR-IGNORE", severity="MED",
        pattern="Error/exception silently ignored",
        regex_per_language={
            "python": r'except(?:\s+\w+)?:\s*(?:pass|\.\.\.)\s*$',
            "go": r'(?:\w+,\s*(?:err|_)\s*:?=.*?)(?:\n\s*(?!if\s+err|if\s+_))',
            "java": r'catch\s*\([^)]+\)\s*\{\s*\}',
        },
        fix="Handle or propagate errors, at minimum log them",
        cwe="CWE-390",
    ))

    # ── Memory / Buffer ─────────────────────────────────────────
    entries.append(BibleEntry(
        id="MEM-BUFFER", severity="CRIT",
        pattern="Buffer overflow via unsafe C functions",
        regex_per_language={
            "c_cpp": r'(?:strcpy|strcat|sprintf|gets|scanf\s*\(\s*"%s")\s*\(',
        },
        fix="Use strncpy, strncat, snprintf, fgets with bounds",
        cwe="CWE-120",
    ))

    entries.append(BibleEntry(
        id="MEM-FORMAT-STR", severity="CRIT",
        pattern="Format string vulnerability",
        regex_per_language={
            "c_cpp": r'(?:printf|fprintf|sprintf|syslog)\s*\(\s*(?!\s*")[^,)]*\)',
        },
        fix="Always use format string literal: printf(\"%s\", var)",
        cwe="CWE-134",
    ))

    entries.append(BibleEntry(
        id="MEM-UAF", severity="CRIT",
        pattern="Use after free",
        regex_per_language={
            "c_cpp": r'free\s*\(\s*(\w+)\s*\)(?:(?!.*?\1\s*=\s*NULL).)*?\1',
        },
        fix="Set pointer to NULL after free, use smart pointers (C++)",
        cwe="CWE-416",
    ))

    # ── Universal (secrets, all languages) ──────────────────────
    entries.append(BibleEntry(
        id="SECRET-GITHUB", severity="CRIT",
        pattern="GitHub personal access token",
        regex_per_language={"universal": r'ghp_[A-Za-z0-9_]{36}'},
        fix="Revoke and rotate token, use environment variables",
        cwe="CWE-798",
    ))

    entries.append(BibleEntry(
        id="SECRET-AWS", severity="CRIT",
        pattern="AWS access key",
        regex_per_language={"universal": r'AKIA[0-9A-Z]{16}'},
        fix="Revoke key, use IAM roles or environment variables",
        cwe="CWE-798",
    ))

    entries.append(BibleEntry(
        id="SECRET-PRIVATE-KEY", severity="CRIT",
        pattern="Private key in source code",
        regex_per_language={"universal": r'-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----'},
        fix="Remove key from source, use key management service",
        cwe="CWE-321",
    ))

    entries.append(BibleEntry(
        id="SECRET-GENERIC", severity="HIGH",
        pattern="Generic secret/token/API key pattern",
        regex_per_language={"universal": r'(?:api[_-]?key|secret[_-]?key|auth[_-]?token|bearer)\s*[=:]\s*["\'][A-Za-z0-9+/=_-]{20,}["\']'},
        fix="Use environment variables or secret management",
        cwe="CWE-798",
    ))

    entries.append(BibleEntry(
        id="SECRET-JWT", severity="HIGH",
        pattern="JWT token hardcoded",
        regex_per_language={"universal": r'eyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}'},
        fix="Never hardcode tokens, use secure token management",
        cwe="CWE-798",
    ))

    entries.append(BibleEntry(
        id="CRYPTO-CERT-NOVERIFY", severity="HIGH",
        pattern="TLS certificate verification disabled",
        regex_per_language={
            "python": r'(?:verify\s*=\s*False|CERT_NONE|check_hostname\s*=\s*False)',
            "javascript": r'(?:rejectUnauthorized\s*:\s*false|NODE_TLS_REJECT_UNAUTHORIZED\s*=\s*["\']0)',
            "go": r'InsecureSkipVerify\s*:\s*true',
            "java": r'(?:TrustAllCerts|X509TrustManager.*?return\s*;|ALLOW_ALL_HOSTNAME)',
        },
        fix="Enable certificate verification, use proper CA certificates",
        cwe="CWE-295",
    ))

    # ── Config-specific ─────────────────────────────────────────
    entries.append(BibleEntry(
        id="CONF-DOCKER-PRIV", severity="HIGH",
        pattern="Docker container running as root or with --privileged",
        regex_per_language={"config": r'(?:--privileged|user:\s*root|USER\s+root)'},
        fix="Run as non-root user, drop capabilities",
        cwe="CWE-250",
    ))

    entries.append(BibleEntry(
        id="CONF-EXPOSED-PORT", severity="MED",
        pattern="Sensitive port exposed (DB, admin, debug)",
        regex_per_language={"config": r'(?:ports:\s*\n\s*-\s*["\']?(?:0\.0\.0\.0:)?(?:3306|5432|27017|6379|9200|11211|2375|8080|5000)["\']?)'},
        fix="Bind to localhost or internal network only",
        cwe="CWE-668",
    ))

    entries.append(BibleEntry(
        id="CONF-ENV-SECRET", severity="HIGH",
        pattern="Secret in environment variable definition (docker-compose, .env, yaml)",
        regex_per_language={"config": r'(?:(?:PASSWORD|SECRET|TOKEN|API_KEY|PRIVATE_KEY)\s*[=:]\s*["\']?[A-Za-z0-9+/=_-]{8,}["\']?)'},
        fix="Use Docker secrets, vault, or encrypted env files",
        cwe="CWE-798",
    ))

    # Assign language lists based on regex keys
    for entry in entries:
        entry.languages = list(entry.regex_per_language.keys())

    return entries


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CWE XML SCRAPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# CWE IDs most relevant to code scanning (not infra/process)
_CWE_CODE_RELEVANT = {
    "89", "78", "79", "22", "90", "91", "94", "95", "96",  # injection
    "120", "121", "122", "125", "126", "127", "131", "134",  # memory
    "190", "191",  # integer overflow
    "200", "209", "215",  # info exposure
    "250", "269", "276",  # privileges
    "287", "306", "307", "312", "319", "321", "327", "328", "330",  # auth + crypto
    "362", "367",  # race
    "400", "416", "434", "476",  # resource + null ptr
    "502", "532", "601", "611", "639", "643", "668",  # deser + XXE + IDOR
    "732", "798", "862", "863", "918", "942",  # access control + SSRF
    "1004", "1333",  # cookie + regex dos
}


def scrape_cwe(xml_path: str | Path) -> list[BibleEntry]:
    """Parse CWE XML file and extract code-relevant weakness entries.

    Args:
        xml_path: path to cwec_vX.X.xml (unzipped) or cwec_latest.xml.zip

    Returns:
        list of BibleEntry from CWE data
    """
    xml_path = Path(xml_path)
    if not xml_path.exists():
        return []

    # Handle .zip
    xml_content = None
    if xml_path.suffix == ".zip":
        with zipfile.ZipFile(xml_path, "r") as zf:
            for name in zf.namelist():
                if name.endswith(".xml"):
                    xml_content = zf.read(name)
                    break
        if xml_content is None:
            return []
        root = ElementTree.fromstring(xml_content)
    else:
        tree = ElementTree.parse(xml_path)
        root = tree.getroot()

    # CWE XML namespace
    ns = ""
    if root.tag.startswith("{"):
        ns = root.tag.split("}")[0] + "}"

    entries = []
    for weakness in root.iter(f"{ns}Weakness"):
        cwe_id = weakness.get("ID", "")
        if cwe_id not in _CWE_CODE_RELEVANT:
            continue

        name = weakness.get("Name", "")
        # Severity from Common_Consequences
        severity = "MED"  # default
        for conseq in weakness.iter(f"{ns}Consequence"):
            impact = ""
            for impact_el in conseq.iter(f"{ns}Impact"):
                impact = (impact_el.text or "").lower()
            if "execute" in impact or "code" in impact:
                severity = "CRIT"
                break
            elif "read" in impact or "modify" in impact:
                severity = "HIGH"

        # Description
        desc_el = weakness.find(f"{ns}Description")
        desc = (desc_el.text or "")[:200] if desc_el is not None else name

        # Mitigations
        fix = ""
        for mitigation in weakness.iter(f"{ns}Mitigation"):
            desc_mit = mitigation.find(f"{ns}Description")
            if desc_mit is not None and desc_mit.text:
                fix = desc_mit.text[:200]
                break

        entries.append(BibleEntry(
            id=f"CWE-{cwe_id}",
            severity=severity,
            pattern=desc.strip(),
            regex_per_language={},  # CWE doesn't provide regex
            fix=fix.strip() or f"See https://cwe.mitre.org/data/definitions/{cwe_id}.html",
            cwe=f"CWE-{cwe_id}",
            source="cwe",
        ))

    return entries


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# SEMGREP YAML SCRAPER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

def scrape_semgrep(rules_dir: str | Path) -> list[BibleEntry]:
    """Parse Semgrep rule YAML files and extract patterns.

    Args:
        rules_dir: path to semgrep-rules/ directory (cloned repo)

    Returns:
        list of BibleEntry from Semgrep rules
    """
    rules_dir = Path(rules_dir)
    if not rules_dir.exists():
        return []

    # Only import yaml if available (optional dep)
    try:
        import yaml
    except ImportError:
        # Fallback: basic YAML parsing for simple semgrep rules
        return _scrape_semgrep_basic(rules_dir)

    entries = []
    lang_dirs = ["python", "javascript", "typescript", "go", "java", "ruby", "php", "c", "cpp"]

    for lang_dir in lang_dirs:
        lang_path = rules_dir / lang_dir
        if not lang_path.exists():
            # Try under subdirectories
            for sub in ["security", "lang"]:
                alt = rules_dir / sub / lang_dir
                if alt.exists():
                    lang_path = alt
                    break
            else:
                continue

        lang_key = lang_dir if lang_dir not in ("c", "cpp", "typescript") else (
            "c_cpp" if lang_dir in ("c", "cpp") else "javascript"
        )

        for yaml_file in lang_path.rglob("*.yaml"):
            try:
                with open(yaml_file, "r", encoding="utf-8", errors="ignore") as f:
                    data = yaml.safe_load(f)
                if not isinstance(data, dict) or "rules" not in data:
                    continue
                for rule in data["rules"]:
                    if not isinstance(rule, dict):
                        continue
                    rule_id = rule.get("id", "")
                    message = rule.get("message", "")
                    severity_raw = rule.get("severity", "WARNING").upper()
                    severity = {"ERROR": "HIGH", "WARNING": "MED", "INFO": "LOW"}.get(severity_raw, "MED")

                    # Extract pattern or patterns
                    pattern = rule.get("pattern", "")
                    if not pattern:
                        patterns = rule.get("patterns", [])
                        if patterns and isinstance(patterns[0], dict):
                            pattern = patterns[0].get("pattern", "")

                    # CWE from metadata
                    metadata = rule.get("metadata", {}) or {}
                    cwe_list = metadata.get("cwe", [])
                    cwe = cwe_list[0] if isinstance(cwe_list, list) and cwe_list else str(cwe_list) if cwe_list else ""
                    fix = rule.get("fix", "") or metadata.get("fix", "") or ""

                    if rule_id and message:
                        entries.append(BibleEntry(
                            id=f"SG-{rule_id}",
                            severity=severity,
                            pattern=message[:200],
                            regex_per_language={lang_key: pattern[:500] if pattern else ""},
                            fix=fix[:200] if fix else f"See semgrep rule: {rule_id}",
                            cwe=cwe[:20] if cwe else "",
                            source="semgrep",
                            languages=[lang_key],
                        ))
            except Exception:
                continue  # Skip malformed YAML

    return entries


def _scrape_semgrep_basic(rules_dir: Path) -> list[BibleEntry]:
    """Minimal YAML parsing without PyYAML dependency."""
    entries = []
    for yaml_file in rules_dir.rglob("*.yaml"):
        try:
            text = yaml_file.read_text(encoding="utf-8", errors="ignore")
            # Extract rule IDs and messages with regex
            ids = re.findall(r'^\s*-?\s*id:\s*(.+)$', text, re.MULTILINE)
            messages = re.findall(r'^\s*message:\s*["\']?(.+?)["\']?\s*$', text, re.MULTILINE)
            severities = re.findall(r'^\s*severity:\s*(\w+)', text, re.MULTILINE)
            patterns = re.findall(r'^\s*pattern:\s*(.+)$', text, re.MULTILINE)

            # Detect language from path
            parts = yaml_file.relative_to(rules_dir).parts
            lang = parts[0] if parts else "unknown"
            lang_key = {"typescript": "javascript", "c": "c_cpp", "cpp": "c_cpp"}.get(lang, lang)

            for i, rid in enumerate(ids):
                msg = messages[i] if i < len(messages) else ""
                sev_raw = (severities[i] if i < len(severities) else "WARNING").upper()
                sev = {"ERROR": "HIGH", "WARNING": "MED", "INFO": "LOW"}.get(sev_raw, "MED")
                pat = patterns[i] if i < len(patterns) else ""

                entries.append(BibleEntry(
                    id=f"SG-{rid.strip()}",
                    severity=sev,
                    pattern=msg.strip()[:200],
                    regex_per_language={lang_key: pat.strip()[:500]},
                    fix=f"See semgrep rule: {rid.strip()}",
                    cwe="",
                    source="semgrep",
                    languages=[lang_key],
                ))
        except Exception:
            continue
    return entries


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# DOWNLOAD SOURCES
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

CWE_URL = "https://cwe.mitre.org/data/xml/cwec_latest.xml.zip"
SEMGREP_URL = "https://github.com/semgrep/semgrep-rules/archive/refs/heads/develop.zip"


def _download_file(url: str, dest: Path) -> bool:
    """Download a file. Returns True on success."""
    try:
        from urllib.request import urlopen, Request
        req = Request(url, headers={"User-Agent": "Muninn-Scanner/0.1"})
        with urlopen(req, timeout=60) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.read())
        return True
    except Exception as e:
        print(f"[B-SCAN-01] Download failed: {url} — {e}")
        return False


def download_sources(sources_dir: str | Path, refresh: bool = False) -> dict[str, Path]:
    """Download CWE XML and Semgrep rules if not cached.

    Args:
        sources_dir: path to .muninn/scanner_sources/
        refresh: force re-download even if cached

    Returns:
        dict with keys 'cwe_xml', 'semgrep_dir' pointing to local paths (or None)
    """
    sources_dir = Path(sources_dir)
    sources_dir.mkdir(parents=True, exist_ok=True)
    result = {"cwe_xml": None, "semgrep_dir": None}

    # CWE
    cwe_zip = sources_dir / "cwec_latest.xml.zip"
    if not cwe_zip.exists() or refresh:
        print("[B-SCAN-01] Downloading CWE XML...")
        if _download_file(CWE_URL, cwe_zip):
            result["cwe_xml"] = cwe_zip
    else:
        result["cwe_xml"] = cwe_zip

    # Semgrep rules
    semgrep_zip = sources_dir / "semgrep-rules.zip"
    semgrep_dir = sources_dir / "semgrep-rules"
    if not semgrep_dir.exists() or refresh:
        print("[B-SCAN-01] Downloading Semgrep rules...")
        if _download_file(SEMGREP_URL, semgrep_zip):
            # Unzip
            try:
                with zipfile.ZipFile(semgrep_zip, "r") as zf:
                    # Zip-slip protection: reject entries with path traversal
                    target = str(sources_dir.resolve())
                    for member in zf.namelist():
                        member_path = str((sources_dir / member).resolve())
                        if not member_path.startswith(target + os.sep) and member_path != target:
                            raise ValueError(f"Zip-slip detected: {member}")
                    zf.extractall(sources_dir)
                # The zip extracts to semgrep-rules-develop/
                extracted = sources_dir / "semgrep-rules-develop"
                if extracted.exists() and not semgrep_dir.exists():
                    extracted.rename(semgrep_dir)
                result["semgrep_dir"] = semgrep_dir
            except Exception as e:
                print(f"[B-SCAN-01] Unzip failed: {e}")
    else:
        result["semgrep_dir"] = semgrep_dir

    return result


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# MAIN: SCRAPE BIBLE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

ALL_LANGUAGES = ["python", "javascript", "go", "java", "ruby", "php", "c_cpp", "rust"]


def scrape_bible(
    output_dir: str | Path,
    sources_dir: Optional[str | Path] = None,
    refresh: bool = False,
    skip_download: bool = False,
) -> dict[str, Path]:
    """Main entry point: scrape all sources, merge, output per-language JSON.

    Args:
        output_dir: where to write the bible JSON files (.muninn/scanner_data/bible/)
        sources_dir: where to cache downloads (.muninn/scanner_sources/)
        refresh: force re-download
        skip_download: skip network access, use only core + cached sources

    Returns:
        dict {language: path_to_json} of generated bible files
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Core bible (always available)
    all_entries = _core_bible()
    print(f"[B-SCAN-01] Core bible: {len(all_entries)} entries")

    # 2. Download sources if requested
    if not skip_download and sources_dir:
        sources = download_sources(sources_dir, refresh=refresh)

        # 3. Scrape CWE
        if sources.get("cwe_xml"):
            cwe_entries = scrape_cwe(sources["cwe_xml"])
            all_entries.extend(cwe_entries)
            print(f"[B-SCAN-01] CWE: {len(cwe_entries)} entries")

        # 4. Scrape Semgrep
        if sources.get("semgrep_dir"):
            sg_entries = scrape_semgrep(sources["semgrep_dir"])
            all_entries.extend(sg_entries)
            print(f"[B-SCAN-01] Semgrep: {len(sg_entries)} entries")
    elif sources_dir:
        # Use cached sources without downloading
        sources_dir = Path(sources_dir)
        cwe_zip = sources_dir / "cwec_latest.xml.zip"
        if cwe_zip.exists():
            cwe_entries = scrape_cwe(cwe_zip)
            all_entries.extend(cwe_entries)
            print(f"[B-SCAN-01] CWE (cached): {len(cwe_entries)} entries")

        semgrep_dir = sources_dir / "semgrep-rules"
        if semgrep_dir.exists():
            sg_entries = scrape_semgrep(semgrep_dir)
            all_entries.extend(sg_entries)
            print(f"[B-SCAN-01] Semgrep (cached): {len(sg_entries)} entries")

    # 5. Organize by language
    by_language = {lang: [] for lang in ALL_LANGUAGES}
    by_language["universal"] = []
    by_language["config"] = []

    for entry in all_entries:
        placed = False
        for lang_key in entry.regex_per_language:
            if lang_key == "universal":
                by_language["universal"].append(entry.to_dict())
                placed = True
            elif lang_key == "config":
                by_language["config"].append(entry.to_dict())
                placed = True
            elif lang_key in by_language:
                by_language[lang_key].append(entry.to_dict())
                placed = True
        # Entries without regex (CWE) go to universal
        if not placed and not entry.regex_per_language:
            by_language["universal"].append(entry.to_dict())

    # 6. Write JSON files
    output_files = {}
    for lang, entries_list in by_language.items():
        if not entries_list:
            continue
        # Dedup by id
        seen_ids = set()
        deduped = []
        for e in entries_list:
            if e["id"] not in seen_ids:
                seen_ids.add(e["id"])
                deduped.append(e)
        out_path = output_dir / f"{lang}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump({"language": lang, "version": _SCANNER_VERSION,
                        "count": len(deduped), "entries": deduped}, f,
                       indent=2, ensure_ascii=False)
        output_files[lang] = out_path
        print(f"[B-SCAN-01] {lang}.json: {len(deduped)} entries")

    print(f"[B-SCAN-01] Total: {sum(len(v) for v in by_language.values())} entries across {len(output_files)} files")
    return output_files


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# CLI
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="B-SCAN-01: Bible Scraper")
    parser.add_argument("--output", default=".muninn/scanner_data/bible",
                        help="Output directory for bible JSON files")
    parser.add_argument("--sources", default=".muninn/scanner_sources",
                        help="Directory to cache downloaded sources")
    parser.add_argument("--refresh", action="store_true",
                        help="Force re-download of sources")
    parser.add_argument("--offline", action="store_true",
                        help="Skip downloads, use only core + cached sources")
    args = parser.parse_args()

    scrape_bible(
        output_dir=args.output,
        sources_dir=args.sources,
        refresh=args.refresh,
        skip_download=args.offline,
    )
