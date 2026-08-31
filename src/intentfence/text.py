from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable

from intentfence.constants import INPUT_MODES
from intentfence.schema import IntentSample

WHITESPACE_RE = re.compile(r"\s+")
EMAIL_RE = re.compile(r"\b[\w.+-]+@[\w.-]+\.[a-z]{2,}\b", re.IGNORECASE)
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
VOLATILE_TOKEN_RE = re.compile(
    r"\b[a-z0-9_./:@-]*\d[a-z0-9_./:@-]*\b",
    re.IGNORECASE,
)


def normalize_text(value: str) -> str:
    """Normalize for deduplication only; model inputs keep their original form."""

    value = unicodedata.normalize("NFKC", value).casefold()
    return WHITESPACE_RE.sub(" ", value).strip()


def normalize_semantic_template(value: str) -> str:
    """Remove deterministic fixture identifiers before split-isolation checks.

    This normalization is deliberately stricter than ``normalize_text``.  It is
    used only for detecting generated-template reuse across data roles; model
    inputs retain the original text.
    """

    value = normalize_text(value)
    value = EMAIL_RE.sub("<email>", value)
    value = URL_RE.sub("<url>", value)
    value = VOLATILE_TOKEN_RE.sub("<id>", value)
    return WHITESPACE_RE.sub(" ", value).strip()


def build_model_text(
    sample: IntentSample,
    mode: str = "action",
    separator: str = "[SEP]",
) -> str:
    if mode not in INPUT_MODES:
        raise ValueError(f"Unknown input mode {mode!r}; expected one of {INPUT_MODES}")
    if mode == "text":
        return sample.untrusted_content
    if mode == "context":
        return f"{sample.user_goal} {separator} {sample.untrusted_content}".strip()
    return (
        f"{sample.user_goal} {separator} {sample.untrusted_content} "
        f"{separator} {sample.proposed_action}"
    ).strip()


def build_text_from_fields(
    user_goal: str,
    untrusted_content: str,
    proposed_action: str,
    separator: str = "[SEP]",
) -> str:
    return (
        f"{user_goal.strip()} {separator} {untrusted_content.strip()} "
        f"{separator} {proposed_action.strip()}"
    ).strip()


def char_ngrams(value: str, n: int = 5) -> set[str]:
    normalized = normalize_text(value)
    if len(normalized) <= n:
        return {normalized} if normalized else set()
    return {normalized[index : index + n] for index in range(len(normalized) - n + 1)}


def jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    left_set, right_set = set(left), set(right)
    if not left_set and not right_set:
        return 1.0
    union = left_set | right_set
    return len(left_set & right_set) / len(union) if union else 0.0


def chunk_untrusted_content(
    content: str,
    *,
    chunk_words: int = 260,
    overlap_words: int = 40,
) -> list[str]:
    """Deterministic word-window fallback before tokenizer-aware chunking."""

    if chunk_words <= 0 or overlap_words < 0 or overlap_words >= chunk_words:
        raise ValueError("Require chunk_words > overlap_words >= 0")
    words = content.split()
    if len(words) <= chunk_words:
        return [content]
    step = chunk_words - overlap_words
    return [" ".join(words[start : start + chunk_words]) for start in range(0, len(words), step)]
