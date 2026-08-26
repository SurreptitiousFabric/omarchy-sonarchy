from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping
from typing import Any

MIN_TITLE_SCORE = 0.68
MIN_ARTIST_SCORE = 0.62
MIN_MATCH_SCORE = 0.80
AMBIGUITY_MARGIN = 0.035

_VERSION_WORDS = frozenset(
    {
        "album",
        "edit",
        "edition",
        "mono",
        "radio",
        "remaster",
        "remastered",
        "single",
        "stereo",
        "version",
    }
)
_ARTIST_SEPARATORS = re.compile(r"\s*(?:,|;|/|&|\band\b|\bfeat(?:uring)?\.?\b)\s*", re.I)


def _tokens(value: Any, *, discard_version_words: bool = False) -> tuple[str, ...]:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = "".join(character for character in text if not unicodedata.combining(character))
    tokens = re.findall(r"[a-z0-9]+", text)
    if discard_version_words:
        tokens = [token for token in tokens if token not in _VERSION_WORDS]
    return tuple(tokens)


def _token_similarity(left: Iterable[str], right: Iterable[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    shared = len(left_set & right_set)
    containment = shared / min(len(left_set), len(right_set))
    jaccard = shared / len(left_set | right_set)
    return 0.65 * containment + 0.35 * jaccard


def _is_contiguous_subsequence(needle: tuple[str, ...], haystack: tuple[str, ...]) -> bool:
    if len(needle) < 2 or len(needle) > len(haystack):
        return False
    width = len(needle)
    return any(
        haystack[index : index + width] == needle for index in range(len(haystack) - width + 1)
    )


def title_similarity(reference: Any, candidate: Any) -> float:
    reference_tokens = _tokens(reference, discard_version_words=True)
    candidate_tokens = _tokens(candidate, discard_version_words=True)
    score = _token_similarity(reference_tokens, candidate_tokens)
    # Classical stations often name the whole work while Apple lists its
    # individual movements. A multi-word work title embedded intact in the
    # catalog title is strong evidence, provided the artist/composer gate also
    # passes later.
    if _is_contiguous_subsequence(reference_tokens, candidate_tokens):
        score = max(score, 0.95)
    return score


def artist_similarity(reference: Any, candidate: Any) -> float:
    candidate_tokens = _tokens(candidate)
    whole_score = _token_similarity(_tokens(reference), candidate_tokens)
    part_scores = (
        _token_similarity(_tokens(part), candidate_tokens)
        for part in _ARTIST_SEPARATORS.split(str(reference or ""))
        if part.strip()
    )
    return max((whole_score, *part_scores), default=0.0)


def _identity(candidate: Mapping[str, Any]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    return (
        _tokens(candidate.get("title"), discard_version_words=True),
        _tokens(candidate.get("artist")),
    )


def select_artwork_match(
    title: Any,
    artist: Any,
    candidates: Iterable[Mapping[str, Any]],
) -> dict[str, Any] | None:
    """Choose a conservative title-and-artist match from catalog results."""

    ranked: list[dict[str, Any]] = []
    for candidate in candidates:
        artwork_url = str(candidate.get("artwork_url", "") or "")
        if not artwork_url:
            continue
        title_score = title_similarity(title, candidate.get("title"))
        artist_score = artist_similarity(artist, candidate.get("artist"))
        score = 0.72 * title_score + 0.28 * artist_score
        if (
            title_score < MIN_TITLE_SCORE
            or artist_score < MIN_ARTIST_SCORE
            or score < MIN_MATCH_SCORE
        ):
            continue
        ranked.append(
            {
                "title": str(candidate.get("title", "") or ""),
                "artist": str(candidate.get("artist", "") or ""),
                "album": str(candidate.get("album", "") or ""),
                "artwork_url": artwork_url,
                "confidence": round(score, 3),
                "_identity": _identity(candidate),
            }
        )

    ranked.sort(key=lambda item: (-float(item["confidence"]), item["title"], item["artist"]))
    if not ranked:
        return None

    best = ranked[0]
    if len(ranked) > 1:
        runner_up = ranked[1]
        if (
            float(best["confidence"]) - float(runner_up["confidence"]) < AMBIGUITY_MARGIN
            and best["_identity"] != runner_up["_identity"]
            and best["artwork_url"] != runner_up["artwork_url"]
        ):
            return None

    best.pop("_identity")
    return best
