#!/usr/bin/env python3
"""
V10A — VADER Sentiment Scoring for Muninn.

Paper: Hutto & Gilbert 2014, "VADER: A parsimonious rule-based model
for sentiment analysis of social media text", ICWSM.

Returns compound score in [-1, +1] per message.
Arousal = abs(compound). Valence = compound.
Rule-based, zero LLM, < 1ms per sentence.

Usage:
    try:
        from .sentiment import score_sentiment, score_session
    except ImportError:
        from sentiment import score_sentiment, score_session
    s = score_sentiment("this is great!")  # {'compound': 0.65, 'valence': 0.65, 'arousal': 0.65}
    session = score_session(["msg1", "msg2", ...])  # aggregated scores
"""

# Lazy import — graceful if vaderSentiment not installed
_analyzer = None


def _get_analyzer():
    """Lazy singleton for VADER analyzer."""
    global _analyzer
    if _analyzer is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer
            _analyzer = SentimentIntensityAnalyzer()
        except ImportError:
            return None
    return _analyzer


def score_sentiment(text: str) -> dict:
    """Score a single text. Returns {'compound': float, 'valence': float, 'arousal': float}.

    compound: VADER compound in [-1, +1]
    valence: same as compound (signed)
    arousal: abs(compound) — intensity regardless of polarity

    Returns zeros if VADER not installed or text empty.
    """
    if not isinstance(text, str) or not text.strip():
        return {"compound": 0.0, "valence": 0.0, "arousal": 0.0}

    analyzer = _get_analyzer()
    if analyzer is None:
        return {"compound": 0.0, "valence": 0.0, "arousal": 0.0}

    scores = analyzer.polarity_scores(text)
    compound = scores["compound"]
    return {
        "compound": compound,
        "valence": compound,
        "arousal": abs(compound),
    }


def score_session(messages: list[str]) -> dict:
    """Aggregate sentiment over a session (list of messages).

    Returns:
        {
            'mean_valence': float,   # average valence [-1, +1]
            'mean_arousal': float,   # average arousal [0, 1]
            'peak_valence': float,   # max absolute valence
            'peak_arousal': float,   # max arousal
            'n_positive': int,       # count compound > 0.05
            'n_negative': int,       # count compound < -0.05
            'n_neutral': int,        # count -0.05 <= compound <= 0.05
            'scores': list[float],   # per-message compound scores
        }
    """
    if not messages:
        return {
            "mean_valence": 0.0, "mean_arousal": 0.0,
            "peak_valence": 0.0, "peak_arousal": 0.0,
            "n_positive": 0, "n_negative": 0, "n_neutral": 0,
            "scores": [],
        }

    compounds = []
    for msg in messages:
        s = score_sentiment(msg)
        compounds.append(s["compound"])

    n = len(compounds)
    mean_v = sum(compounds) / n
    mean_a = sum(abs(c) for c in compounds) / n
    peak_v = max(compounds, key=abs) if compounds else 0.0
    peak_a = max(abs(c) for c in compounds) if compounds else 0.0

    n_pos = sum(1 for c in compounds if c > 0.05)
    n_neg = sum(1 for c in compounds if c < -0.05)
    n_neu = n - n_pos - n_neg

    return {
        "mean_valence": round(mean_v, 4),
        "mean_arousal": round(mean_a, 4),
        "peak_valence": round(peak_v, 4),
        "peak_arousal": round(peak_a, 4),
        "n_positive": n_pos,
        "n_negative": n_neg,
        "n_neutral": n_neu,
        "scores": [round(c, 4) for c in compounds],
    }


def circumplex_map(valence: float, arousal: float) -> dict:
    """V10B: Russell circumplex affect mapping (Russell 1980).

    Maps (valence, arousal) to polar coordinates in the affect space.
    theta = angle (emotion category), r = intensity.

    Quadrants:
      Q1 (+v, +a): excited, happy, alert
      Q2 (-v, +a): tense, angry, distressed
      Q3 (-v, -a): sad, depressed, bored
      Q4 (+v, -a): calm, relaxed, serene

    Args:
        valence: [-1, +1]
        arousal: [0, 1] (or [-1, +1] for signed arousal)

    Returns:
        {'theta': float (radians), 'r': float (intensity 0-1),
         'quadrant': str, 'label': str}
    """
    import math
    v = max(-1.0, min(1.0, float(valence)))
    a = max(-1.0, min(1.0, float(arousal)))
    theta = math.atan2(a, v)
    r = min(1.0, math.sqrt(v ** 2 + a ** 2))

    # Determine quadrant and label
    if v >= 0 and a >= 0:
        quadrant = "Q1"
        label = "excited" if r > 0.5 else "content"
    elif v < 0 and a >= 0:
        quadrant = "Q2"
        label = "tense" if r > 0.5 else "alert"
    elif v < 0 and a < 0:
        quadrant = "Q3"
        label = "sad" if r > 0.5 else "bored"
    else:
        quadrant = "Q4"
        label = "calm" if r > 0.5 else "relaxed"

    return {
        "theta": round(theta, 4),
        "r": round(r, 4),
        "quadrant": quadrant,
        "label": label,
    }
