"""ERRANT-backed, exact-edit scoring for evaluation v2.

This module deliberately requires the isolated evaluation environment and the
English spaCy model. It never substitutes a token or string diff when ERRANT is
unavailable.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from functools import lru_cache
import importlib.metadata
import platform
import sys
from typing import Any, Sequence


_CACHE_SIZE = 8192
_BETA = 0.5


@dataclass(frozen=True, slots=True)
class ErrantEdit:
    """Immutable fields copied from an ERRANT Edit object."""

    o_start: int
    o_end: int
    o_str: str
    c_start: int
    c_end: int
    c_str: str
    category: str

    @property
    def match_key(self) -> tuple[int, int, str]:
        # ERRANT's correction scorer keys edits by source span and correction.
        # The category is intentionally descriptive and excluded from matching.
        return (self.o_start, self.o_end, self.c_str)

    def as_dict(self) -> dict[str, Any]:
        return {
            "o_start": self.o_start,
            "o_end": self.o_end,
            "o_str": self.o_str,
            "c_start": self.c_start,
            "c_end": self.c_end,
            "c_str": self.c_str,
            "type": self.category,
        }


class ErrantEngine:
    """Loaded ERRANT English annotator with bounded parse/edit caches."""

    def __init__(self) -> None:
        try:
            import errant

            self._annotator = errant.load("en")
        except Exception as exc:  # Import/model failures must stay visible.
            raise RuntimeError(
                "Could not load real ERRANT for English. Install the pinned "
                "requirements from SLM_A1A2/requirements-evaluation-v2.txt "
                "inside SLM_A1A2/.venv_eval_v2; no fallback scorer is used."
            ) from exc

    @lru_cache(maxsize=_CACHE_SIZE)
    def _parse(self, text: str) -> Any:
        # ERRANT's own spaCy tokenizer is required for raw, untokenized text.
        return self._annotator.parse(text, tokenise=True)

    @lru_cache(maxsize=_CACHE_SIZE)
    def _annotate_pair(self, source: str, target: str) -> tuple[ErrantEdit, ...]:
        edits = self._annotator.annotate(self._parse(source), self._parse(target))
        return tuple(
            ErrantEdit(
                o_start=int(edit.o_start),
                o_end=int(edit.o_end),
                o_str=str(edit.o_str),
                c_start=int(edit.c_start),
                c_end=int(edit.c_end),
                c_str=str(edit.c_str),
                category=str(edit.type),
            )
            for edit in edits
        )

    def annotate_pair(self, source: str, target: str) -> tuple[ErrantEdit, ...]:
        """Return actual ERRANT edits for one complete source→target pair."""

        return self._annotate_pair(source, target)

    def metadata(self) -> dict[str, Any]:
        """Describe the annotation stack and effective tokenizer settings."""

        try:
            versions = {
                package: importlib.metadata.version(package)
                for package in (
                    "errant",
                    "spacy",
                    "en-core-web-sm",
                    "rapidfuzz",
                    "click",
                )
            }
        except importlib.metadata.PackageNotFoundError as exc:
            raise RuntimeError(
                f"Required evaluation distribution is missing: {exc.name}"
            ) from exc

        tokenizer = self._annotator.nlp.tokenizer
        return {
            "engine": "ERRANT",
            "language": "en",
            "versions": versions,
            "python_version": platform.python_version(),
            "platform": platform.platform(),
            "tokenizer_class": (
                f"{tokenizer.__class__.__module__}.{tokenizer.__class__.__qualname__}"
            ),
            "spacy_pipeline": list(self._annotator.nlp.pipe_names),
            "parse_tokenise": True,
            "alignment": "ERRANT Annotator.annotate (lev=False, merging='rules')",
            "category_source": "ERRANT Edit.type, preserved verbatim",
            "cache": {
                "parse_maxsize": _CACHE_SIZE,
                "annotation_pair_maxsize": _CACHE_SIZE,
                "parse_hits": self._parse.cache_info().hits,
                "annotation_pair_hits": self._annotate_pair.cache_info().hits,
            },
        }


@lru_cache(maxsize=1)
def get_engine() -> ErrantEngine:
    """Load one cached ERRANT engine for this Python process."""

    return ErrantEngine()


def _counts_and_diagnostics(
    hypothesis_edits: Sequence[ErrantEdit], reference_edits: Sequence[ErrantEdit]
) -> dict[str, Any]:
    """Compare ERRANT edits by exact source span and correction text.

    Categories are returned as lineage diagnostics. They do not change whether
    an edit is a correction match.
    """

    hypothesis_by_key: dict[tuple[int, int, str], list[ErrantEdit]] = defaultdict(list)
    reference_by_key: dict[tuple[int, int, str], list[ErrantEdit]] = defaultdict(list)
    for edit in hypothesis_edits:
        hypothesis_by_key[edit.match_key].append(edit)
    for edit in reference_edits:
        reference_by_key[edit.match_key].append(edit)

    tp = fp = fn = 0
    category_counts: dict[str, Counter[str]] = defaultdict(Counter)
    type_mismatches: list[dict[str, Any]] = []

    for key in sorted(hypothesis_by_key.keys() | reference_by_key.keys()):
        hyp_group = hypothesis_by_key.get(key, [])
        ref_group = reference_by_key.get(key, [])
        matched = min(len(hyp_group), len(ref_group))
        tp += matched
        fp += len(hyp_group) - matched
        fn += len(ref_group) - matched

        for index in range(matched):
            hypothesis = hyp_group[index]
            reference = ref_group[index]
            # A TP inherits the reference's ERRANT type, matching ERRANT's
            # correction-score lineage convention. Type does not affect TP.
            category_counts[reference.category]["tp"] += 1
            if hypothesis.category != reference.category:
                type_mismatches.append(
                    {
                        "o_start": key[0],
                        "o_end": key[1],
                        "c_str": key[2],
                        "hypothesis_type": hypothesis.category,
                        "reference_type": reference.category,
                    }
                )

        for edit in hyp_group[matched:]:
            category_counts[edit.category]["fp"] += 1
        for edit in ref_group[matched:]:
            category_counts[edit.category]["fn"] += 1

    precision = tp / (tp + fp) if (tp + fp) else 1.0
    recall = tp / (tp + fn) if (tp + fn) else 1.0
    denominator = (_BETA**2 * precision) + recall
    f0_5 = ((1 + _BETA**2) * precision * recall / denominator) if denominator else 0.0

    return {
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "precision": round(precision, 6),
        "recall": round(recall, 6),
        "f0_5": round(f0_5, 6),
        "hypothesis_edit_count": len(hypothesis_edits),
        "reference_edit_count": len(reference_edits),
        "category_lineage": {
            category: {
                "tp": counts["tp"],
                "fp": counts["fp"],
                "fn": counts["fn"],
            }
            for category, counts in sorted(category_counts.items())
        },
        "type_mismatches": type_mismatches,
    }


def _best_reference_index(reference_scores: Sequence[dict[str, Any]]) -> int:
    """Choose the best complete reference; never combine their edits."""

    def unrounded_f0_5(score: dict[str, Any]) -> float:
        tp, fp, fn = score["tp"], score["fp"], score["fn"]
        precision = tp / (tp + fp) if tp + fp else 1.0
        recall = tp / (tp + fn) if tp + fn else 1.0
        denominator = (_BETA**2 * precision) + recall
        return (
            (1 + _BETA**2) * precision * recall / denominator
            if denominator
            else 0.0
        )

    return min(
        range(len(reference_scores)),
        key=lambda index: (
            -unrounded_f0_5(reference_scores[index]),
            reference_scores[index]["fp"],
            -reference_scores[index]["tp"],
            reference_scores[index]["reference_index"],
        ),
    )


def _require_nonempty_text(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{label} must be a string; got {type(value).__name__}.")
    if not value.strip():
        raise ValueError(f"{label} must be a non-empty text string.")
    return value


def score_text(
    source: str, reference_texts: Sequence[str], candidate: str
) -> dict[str, Any]:
    """Score source→candidate edits against complete source→reference edits.

    ``reference_texts[0]`` is the primary reference; later entries are complete
    alternatives. Each reference is scored independently with ERRANT edits, and
    the best alternative is selected per case by unrounded F0.5, then lower FP,
    higher TP, then lower input index.

    Exact correction matching uses only ``(o_start, o_end, c_str)``. ERRANT's
    classified type is returned for lineage and mismatch diagnostics, but is not
    part of the correction match key.
    """

    source = _require_nonempty_text(source, "source")
    candidate = _require_nonempty_text(candidate, "candidate")
    if isinstance(reference_texts, (str, bytes)) or not isinstance(
        reference_texts, Sequence
    ):
        raise TypeError("reference_texts must be a sequence of complete strings.")
    if not reference_texts:
        raise ValueError("reference_texts must contain at least the primary reference.")

    references = tuple(
        _require_nonempty_text(reference, f"reference_texts[{index}]")
        for index, reference in enumerate(reference_texts)
    )
    engine = get_engine()
    hypothesis_edits = engine.annotate_pair(source, candidate)

    reference_scores: list[dict[str, Any]] = []
    for reference_index, reference_text in enumerate(references):
        reference_edits = engine.annotate_pair(source, reference_text)
        score = _counts_and_diagnostics(hypothesis_edits, reference_edits)
        score.update(
            {
                "reference_index": reference_index,
                "reference_role": "primary" if reference_index == 0 else "alternative",
                "reference_edits": [edit.as_dict() for edit in reference_edits],
            }
        )
        reference_scores.append(score)

    best_index = _best_reference_index(reference_scores)
    return {
        "primary": reference_scores[0],
        "best_full_reference": reference_scores[best_index],
        "reference_scores": reference_scores,
        "best_reference_index": best_index,
        "hypothesis_edits": [edit.as_dict() for edit in hypothesis_edits],
        "engine_provenance": engine.metadata(),
        "selection_policy": {
            "scope": "per complete reference for this case",
            "order": [
                "highest unrounded F0.5",
                "lowest FP",
                "highest TP",
                "lowest reference_index",
            ],
            "alternatives_are_not_combined": True,
        },
        "matching_policy": "exact source token span (o_start,o_end) plus corrected text (c_str); ERRANT type is diagnostic only",
    }


__all__ = ["ErrantEdit", "ErrantEngine", "get_engine", "score_text"]
