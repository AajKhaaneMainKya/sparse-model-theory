from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache

import numpy as np
from sentence_transformers import SentenceTransformer

from .note import Note


# Placeholder only. MiniLM cosine distributions must be recalibrated once real
# Rahul notes exist; 0.30 is not a settled project truth.
STRONG_MATCH_THRESHOLD = 0.30


class MatchTier(Enum):
    NO_MATCH = "no_match"
    WEAK_MATCH = "weak_match"
    STRONG_MATCH = "strong_match"


@dataclass(frozen=True)
class Match:
    note: Note
    score: float


@dataclass(frozen=True)
class MatchResult:
    tier: MatchTier
    matches: list[Match]


def precedent_matches(query: str, notes: list[Note], top_n: int = 3) -> MatchResult:
    contested = [note for note in notes if note.anchor_type == "contested"]
    query_vector = embed(query)
    scored = [
        Match(note=note, score=cosine(query_vector, embed(note.title + "\n" + note.body)))
        for note in contested
    ]
    ranked = sorted(scored, key=lambda item: item.score, reverse=True)[:top_n]

    # Dense embedding cosine is rarely exactly zero, unlike sparse bag-of-words
    # overlap. The tier is what separates weak candidates from strong precedent.
    matches = [match for match in ranked if match.score > 0]
    if not matches:
        return MatchResult(tier=MatchTier.NO_MATCH, matches=[])
    if matches[0].score >= STRONG_MATCH_THRESHOLD:
        return MatchResult(tier=MatchTier.STRONG_MATCH, matches=matches)
    return MatchResult(tier=MatchTier.WEAK_MATCH, matches=matches)


@lru_cache(maxsize=1)
def embedding_model() -> SentenceTransformer:
    return SentenceTransformer("all-MiniLM-L6-v2")


# Follow-up: replace this text-keyed cache with a note id + content hash index.
@lru_cache(maxsize=1024)
def embed(text: str) -> np.ndarray:
    return embedding_model().encode(text, convert_to_numpy=True)


def cosine(left: np.ndarray, right: np.ndarray) -> float:
    left_norm = np.linalg.norm(left)
    right_norm = np.linalg.norm(right)
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return float(np.dot(left, right) / (left_norm * right_norm))
