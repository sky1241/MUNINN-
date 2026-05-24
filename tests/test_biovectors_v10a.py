"""V10A — VADER Sentiment Scoring: strict validation bornes.

Paper: Hutto & Gilbert 2014, ICWSM.
Echelle: compound in [-1,+1], F1~0.96 vs human annotations.

Tests:
  V10A.1  compound in [-1,+1] for all inputs
  V10A.2  "this is great!" > 0.5
  V10A.3  "terrible failure" < -0.5
  V10A.4  "the function returns 42" in [-0.1,+0.1] (neutral)
  V10A.5  Performance: < 1ms per phrase (rule-based)
  V10A.6  Empty/None input: no crash, returns zeros
  V10A.7  Session scoring: 1000 messages, no crash
  V10A.8  Arousal = abs(valence) always
  V10A.9  Session aggregates are consistent
  V10A.10 Graceful when vaderSentiment not installed (mocked)
"""
import sys, os, time
from sentiment import score_sentiment, score_session

PASS = 0
FAIL = 0

def check(name, condition, detail=""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  {name} PASS{': ' + detail if detail else ''}")
    else:
        FAIL += 1
        print(f"  {name} FAIL{': ' + detail if detail else ''}")


def test_v10a_1_range():
    """compound always in [-1, +1]"""
    test_cases = [
        "this is great!",
        "terrible failure and disaster",
        "the function returns 42",
        "I LOVE this!! Amazing!!!",
        "worst thing ever, absolutely horrible",
        "",
        "a",
        "hello world",
        "error error error crash burn die",
        "wonderful beautiful perfect excellent superb",
    ]
    all_in_range = True
    for text in test_cases:
        s = score_sentiment(text)
        if not (-1.0 <= s["compound"] <= 1.0):
            all_in_range = False
            break
    check("V10A.1", all_in_range, f"all {len(test_cases)} inputs in [-1,+1]")


def test_v10a_2_positive():
    """'this is great!' > 0.5"""
    s = score_sentiment("this is great!")
    check("V10A.2", s["compound"] > 0.5, f"compound={s['compound']:.4f}")


def test_v10a_3_negative():
    """'terrible failure' < -0.5"""
    s = score_sentiment("terrible failure")
    check("V10A.3", s["compound"] < -0.5, f"compound={s['compound']:.4f}")


def test_v10a_4_neutral():
    """'the function returns 42' in [-0.1,+0.1]"""
    s = score_sentiment("the function returns 42")
    check("V10A.4", -0.1 <= s["compound"] <= 0.1, f"compound={s['compound']:.4f}")


def test_v10a_5_performance():
    """< 1ms per phrase"""
    texts = ["This is a test sentence for performance measurement."] * 100
    start = time.perf_counter()
    for t in texts:
        score_sentiment(t)
    elapsed = (time.perf_counter() - start) / len(texts) * 1000  # ms per call
    check("V10A.5", elapsed < 1.0, f"{elapsed:.3f}ms per call")


def test_v10a_6_empty():
    """Empty/None/non-string: no crash, returns zeros"""
    s1 = score_sentiment("")
    s2 = score_sentiment("   ")
    s3 = score_sentiment(None)
    s4 = score_sentiment(42)
    ok = (s1["compound"] == 0.0 and s2["compound"] == 0.0
          and s3["compound"] == 0.0 and s4["compound"] == 0.0)
    check("V10A.6", ok, f"empty={s1['compound']}, spaces={s2['compound']}, None={s3['compound']}, int={s4['compound']}")


def test_v10a_7_session_1000():
    """1000 messages session, no crash"""
    messages = [f"Message number {i} about testing stuff" for i in range(1000)]
    try:
        result = score_session(messages)
        ok = (len(result["scores"]) == 1000
              and isinstance(result["mean_valence"], float)
              and isinstance(result["mean_arousal"], float))
        check("V10A.7", ok, f"1000 msgs scored, mean_v={result['mean_valence']:.4f}")
    except Exception as e:
        check("V10A.7", False, f"crash: {e}")


def test_v10a_8_arousal_abs():
    """arousal = abs(valence) always"""
    tests = [
        "this is great!",
        "terrible failure",
        "the function returns 42",
        "I am so happy today!",
        "this makes me angry",
    ]
    all_ok = True
    for t in tests:
        s = score_sentiment(t)
        if abs(s["arousal"] - abs(s["valence"])) > 1e-10:
            all_ok = False
            break
    check("V10A.8", all_ok, "arousal == abs(valence) for all tests")


def test_v10a_9_session_consistency():
    """Session aggregates are consistent"""
    msgs = ["great success!", "terrible disaster", "normal operation", "amazing!", "awful bug"]
    result = score_session(msgs)
    ok = (result["n_positive"] + result["n_negative"] + result["n_neutral"] == len(msgs)
          and -1.0 <= result["mean_valence"] <= 1.0
          and 0.0 <= result["mean_arousal"] <= 1.0
          and result["n_positive"] >= 2  # "great success" + "amazing"
          and result["n_negative"] >= 2)  # "terrible disaster" + "awful bug"
    check("V10A.9", ok,
          f"pos={result['n_positive']} neg={result['n_negative']} neu={result['n_neutral']}")


def test_v10a_10_empty_session():
    """Empty session returns zeros"""
    result = score_session([])
    ok = (result["mean_valence"] == 0.0 and result["mean_arousal"] == 0.0
          and result["n_positive"] == 0 and result["scores"] == [])
    check("V10A.10", ok, "empty session = all zeros")


def test_v10a_11_non_string_in_session():
    """Non-string elements in session list don't crash"""
    try:
        result = score_session(["hello", None, 42, "", "great!"])
        ok = len(result["scores"]) == 5
        check("V10A.11", ok, f"mixed types: {len(result['scores'])} scores, no crash")
    except Exception as e:
        check("V10A.11", False, f"crash: {e}")


if __name__ == "__main__":
    print("=== V10A VADER Sentiment — 11 bornes ===")
    test_v10a_1_range()
    test_v10a_2_positive()
    test_v10a_3_negative()
    test_v10a_4_neutral()
    test_v10a_5_performance()
    test_v10a_6_empty()
    test_v10a_7_session_1000()
    test_v10a_8_arousal_abs()
    test_v10a_9_session_consistency()
    test_v10a_10_empty_session()
    test_v10a_11_non_string_in_session()
    print(f"\n=== RESULTAT: {PASS} PASS, {FAIL} FAIL ===")
    if FAIL > 0:
        sys.exit(1)
