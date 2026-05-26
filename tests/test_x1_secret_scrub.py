"""X1 — Secret scrub: 7 entry points + defense in observe_text().

Tests:
  X1.1  redact_secrets_text strips GitHub PAT
  X1.2  redact_secrets_text strips Anthropic API key
  X1.3  redact_secrets_text strips Bearer token (20+ chars)
  X1.4  redact_secrets_text preserves normal text
  X1.5  redact_secrets_text strips password= pattern
  X1.6  redact_secrets_text strips AWS access key
  X1.7  observe_text defense — secrets never reach mycelium concepts
  X1.8  redact_secrets_text strips DB connection string
  X1.9  redact_secrets_text strips PEM private key
  X1.10 redact_secrets_text strips French password patterns (mdp/cle)
  X1.11 multiple secrets in one text all redacted
"""
import sys, os, tempfile, shutil
from pathlib import Path

# BRICK 14 (2026-04-11): fix the collection-time ImportError. The original
# `from _secrets import redact_secrets_text` at module top tried to import
# before any sys.path setup, so pytest collection blew up with
# ModuleNotFoundError. Add the engine/core dir to sys.path FIRST, then import.
_ENGINE_CORE = Path(__file__).resolve().parent.parent / "engine" / "core"
if str(_ENGINE_CORE) not in sys.path:
    sys.path.insert(0, str(_ENGINE_CORE))

from _secrets import redact_secrets_text  # noqa: E402


def test_x1_1_github_pat():
    """GitHub PAT classic is redacted."""
    text = "token is ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ12345"
    result = redact_secrets_text(text)
    assert "ghp_" not in result, f"X1.1 FAIL: GitHub PAT not redacted: {result}"
    assert "[REDACTED]" in result
    print(f"  X1.1 PASS: GitHub PAT redacted")


def test_x1_2_anthropic_key():
    """Anthropic/OpenAI sk- key is redacted."""
    text = "my key is sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890"
    result = redact_secrets_text(text)
    assert "sk-ant" not in result, f"X1.2 FAIL: API key not redacted: {result}"
    assert "[REDACTED]" in result
    print(f"  X1.2 PASS: Anthropic key redacted")


def test_x1_3_bearer_token():
    """Bearer token with 20+ chars is redacted."""
    text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.abc"
    result = redact_secrets_text(text)
    assert "eyJhbG" not in result, f"X1.3 FAIL: Bearer token not redacted: {result}"
    assert "[REDACTED]" in result
    print(f"  X1.3 PASS: Bearer token redacted")


def test_x1_4_normal_text_preserved():
    """Normal text without secrets is unchanged."""
    text = "The compression pipeline has 11 layers and achieves x4.5 ratio on real transcripts."
    result = redact_secrets_text(text)
    assert result == text, f"X1.4 FAIL: normal text modified: {result}"
    print(f"  X1.4 PASS: normal text preserved")


def test_x1_5_password_pattern():
    """password= pattern is redacted."""
    text = "config password=SuperSecret123!"
    result = redact_secrets_text(text)
    assert "SuperSecret" not in result, f"X1.5 FAIL: password not redacted: {result}"
    assert "[REDACTED]" in result
    print(f"  X1.5 PASS: password pattern redacted")


def test_x1_6_aws_key():
    """AWS access key is redacted."""
    text = "aws_access_key_id = AKIAIOSFODNN7EXAMPLE"
    result = redact_secrets_text(text)
    assert "AKIAIOSFODNN7EXAMPLE" not in result, f"X1.6 FAIL: AWS key not redacted: {result}"
    assert "[REDACTED]" in result
    print(f"  X1.6 PASS: AWS key redacted")


def test_x1_7_observe_text_defense():
    """Secrets fed to observe_text() never appear in mycelium concepts."""
    from muninn.mycelium import Mycelium

    tmpdir = tempfile.mkdtemp(prefix="muninn_x1_")
    try:
        muninn_dir = Path(tmpdir) / ".muninn"
        muninn_dir.mkdir()

        m = Mycelium(Path(tmpdir))
        m.start_session()

        # Feed text containing a secret
        secret = "ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ12345"
        text = f"The token is {secret} and we use it for auth"
        m.observe_text(text)

        # Check that the secret (or any part of it) is not in concepts
        if m._db is not None:
            concepts = m._db.get_all_concepts()
        else:
            concepts = list(m.data.get("concepts", {}).keys())

        for concept in concepts:
            assert "ghp_" not in concept, f"X1.7 FAIL: secret leaked to concept: {concept}"
            assert secret[:10] not in concept, f"X1.7 FAIL: secret fragment in concept: {concept}"

        print(f"  X1.7 PASS: observe_text defense works ({len(concepts)} concepts, no leaks)")
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def test_x1_8_db_connection_string():
    """Database connection string with password is redacted."""
    text = "dsn = postgresql://admin:p4ssw0rd@db.example.com:5432/mydb"
    result = redact_secrets_text(text)
    assert "p4ssw0rd" not in result, f"X1.8 FAIL: DB password not redacted: {result}"
    assert "[REDACTED]" in result
    print(f"  X1.8 PASS: DB connection string redacted")


def test_x1_9_pem_private_key():
    """PEM private key block is redacted."""
    text = "-----BEGIN RSA PRIVATE KEY-----\nMIIEpAIBAAKCAQEA0Z3VS5JJcds\n-----END RSA PRIVATE KEY-----"
    result = redact_secrets_text(text)
    assert "MIIEpAIBAAK" not in result, f"X1.9 FAIL: PEM key not redacted: {result}"
    assert "[REDACTED]" in result
    print(f"  X1.9 PASS: PEM private key redacted")


def test_x1_10_french_password():
    """French password patterns (mdp, cle) are redacted."""
    text = "mdp: monmotdepasse123"
    result = redact_secrets_text(text)
    assert "monmotdepasse" not in result, f"X1.10 FAIL: French password not redacted: {result}"
    assert "[REDACTED]" in result
    print(f"  X1.10 PASS: French password pattern redacted")


def test_x1_11_multiple_secrets():
    """Multiple secrets in one text are all redacted."""
    text = (
        "GitHub: ghp_aBcDeFgHiJkLmNoPqRsTuVwXyZ12345\n"
        "API: sk-ant-api03-abcdefghijklmnopqrstuvwxyz1234567890\n"
        "AWS: AKIAIOSFODNN7EXAMPLE\n"
        "Normal text that should survive compression."
    )
    result = redact_secrets_text(text)
    assert "ghp_" not in result, f"X1.11 FAIL: GitHub PAT leaked"
    assert "sk-ant" not in result, f"X1.11 FAIL: API key leaked"
    assert "AKIAIOSFODNN7EXAMPLE" not in result, f"X1.11 FAIL: AWS key leaked"
    assert "Normal text" in result, f"X1.11 FAIL: normal text lost"
    assert result.count("[REDACTED]") >= 3, f"X1.11 FAIL: not all secrets redacted"
    print(f"  X1.11 PASS: {result.count('[REDACTED]')} secrets redacted, normal text preserved")


if __name__ == "__main__":
    test_x1_1_github_pat()
    test_x1_2_anthropic_key()
    test_x1_3_bearer_token()
    test_x1_4_normal_text_preserved()
    test_x1_5_password_pattern()
    test_x1_6_aws_key()
    test_x1_7_observe_text_defense()
    test_x1_8_db_connection_string()
    test_x1_9_pem_private_key()
    test_x1_10_french_password()
    test_x1_11_multiple_secrets()
    print("\nAll X1 tests PASS")
