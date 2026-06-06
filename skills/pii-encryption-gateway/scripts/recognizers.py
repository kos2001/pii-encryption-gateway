"""Value-level PII recognizers — find PII by the shape of a value, not the
column name. This is the Presidio AnalyzerEngine idea ported to stdlib: a small
registry of pattern recognizers, each with an optional validator that adjusts
confidence (Presidio's `validate_result`).

Why this complements pii_config: classify_field() only fires when a *column
name* matches an alias. A free-text "비고"/remarks column, a mis-named column,
or PII embedded mid-sentence slips through that net. analyze() scans the actual
text, so those cases are caught regardless of where they live.

Confidence is fail-safe toward protection: a format match alone clears the
default threshold, so RRN-shaped values that fail their check digit (common in
real and synthetic dumps) are still tokenized. A passing checksum only *raises*
the score. CARD is the deliberate exception — a 16-digit run that fails Luhn is
rejected, because false positives there are both common and expensive.

No third-party dependencies, matching crypto_core's portability constraint.
"""

import re
from collections import namedtuple

Span = namedtuple("Span", ["start", "end", "entity_type", "score"])

# Default confidence required to tokenize a span.
THRESHOLD = 0.5

_BANKS = "국민|신한|우리|하나|농협|기업|SC제일|씨티|카카오뱅크|케이뱅크|토스뱅크"


def _rrn_validate(text: str) -> float:
    """Korean RRN weighted mod-11 check digit. Pass -> 0.95, format-only -> 0.6.

    Never returns None: an RRN-shaped value is protected whether or not the
    check digit is valid (fail-safe).
    """
    digits = [int(c) for c in text if c.isdigit()]
    if len(digits) != 13:
        return 0.6
    weights = [2, 3, 4, 5, 6, 7, 8, 9, 2, 3, 4, 5]
    total = sum(d * w for d, w in zip(digits[:12], weights))
    expected = (11 - (total % 11)) % 10
    return 0.95 if expected == digits[12] else 0.6


def _luhn_ok(text: str) -> bool:
    digits = [int(c) for c in text if c.isdigit()][::-1]
    total = 0
    for i, d in enumerate(digits):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _card_validate(text: str):
    """Reject 16-digit runs that fail Luhn (return None drops the candidate)."""
    return 0.9 if _luhn_ok(text) else None


def _account_validate(text: str):
    """A bare triple-group number is an account only if it carries enough
    digits to not be a date (which has 8). >= 11 digits -> 0.6, else reject."""
    return 0.6 if sum(c.isdigit() for c in text) >= 11 else None


# entity_type, compiled pattern, base score, optional validator(matched_text).
# A validator returning None rejects the candidate; otherwise it sets the score.
_RECOGNIZERS = [
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), 0.9, None),
    ("RRN", re.compile(r"\b\d{6}-[1-8]\d{6}\b"), 0.6, _rrn_validate),
    ("PHONE", re.compile(r"\b01[0-9]-?\d{3,4}-?\d{4}\b"), 0.85, None),
    ("CARD", re.compile(r"\b(?:\d{4}-){3}\d{4}\b|\b\d{16}\b"), 0.9, _card_validate),
    ("ACCOUNT", re.compile(rf"(?:{_BANKS})\s*\d{{2,6}}-\d{{2,6}}-\d{{2,6}}"), 0.9, None),
    ("ACCOUNT", re.compile(r"\b\d{2,6}-\d{2,6}-\d{2,6}\b"), 0.6, _account_validate),
]


def analyze(text: str, threshold: float = THRESHOLD):
    """Return non-overlapping PII Spans in `text` scoring >= threshold.

    Overlaps are resolved greedily by (score desc, length desc, position): the
    strongest, longest claim on a stretch of text wins, so a full 16-digit CARD
    beats the ACCOUNT pattern that matches its first 12 digits.
    """
    candidates = []
    for entity_type, pattern, base, validate in _RECOGNIZERS:
        for m in pattern.finditer(text):
            score = base
            if validate is not None:
                score = validate(m.group(0))
                if score is None:
                    continue
            if score >= threshold:
                candidates.append(Span(m.start(), m.end(), entity_type, score))

    candidates.sort(key=lambda s: (-s.score, -(s.end - s.start), s.start))
    chosen = []
    occupied = []
    for span in candidates:
        if any(span.start < e and o < span.end for o, e in occupied):
            continue
        chosen.append(span)
        occupied.append((span.start, span.end))

    chosen.sort(key=lambda s: s.start)
    return chosen


# A sampled cell counts as "being" an entity (vs merely containing one in prose)
# only when detected spans cover most of its text.
_CELL_COVERAGE = 0.6
# Fraction of non-empty samples that must agree on one entity type to classify
# the whole column.
_COLUMN_MAJORITY = 0.6


def infer_column_type(values, sample_size: int = 50):
    """Classify a whole column from a sample of its values (presidio-structured).

    Returns (entity_type, fraction) when a majority of non-empty samples *are* a
    single PII entity, else None. "Are" — not "contain": a cell qualifies only
    when matched spans cover >= _CELL_COVERAGE of it, so a dedicated phone column
    classifies while a free-text column that merely mentions phones does not.

    Generalizing from the column majority lets protect.py seal an odd malformed
    or off-format cell that the per-value recognizers would miss on its own.
    """
    samples = [str(v) for v in values if v not in (None, "")][:sample_size]
    if not samples:
        return None

    type_hits = {}
    for cell in samples:
        spans = analyze(cell)
        # A dedicated PII column holds ONE entity per cell. A cell with several
        # spans (e.g. a phone AND an email) is composite free text, not a column
        # of one entity — exclude it so such columns stay span-level.
        if len(spans) != 1:
            continue
        span = spans[0]
        if (span.end - span.start) / len(cell) < _CELL_COVERAGE:
            continue  # the value is a fragment of prose, not the cell's identity
        type_hits[span.entity_type] = type_hits.get(span.entity_type, 0) + 1

    if not type_hits:
        return None
    best = max(type_hits, key=type_hits.get)
    fraction = type_hits[best] / len(samples)
    return (best, fraction) if fraction >= _COLUMN_MAJORITY else None
