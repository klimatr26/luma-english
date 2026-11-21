"""Synthetic integration tests for real ERRANT in the isolated v2 venv.

Run with any Python from the repository; the launcher always executes the test
fixtures in SLM_A1A2/.venv_eval_v2 and never imports a substitute scorer.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import unittest


SLM_ROOT = Path(__file__).resolve().parents[1]
if os.name == "nt":
    EVAL_PYTHON = SLM_ROOT / ".venv_eval_v2" / "Scripts" / "python.exe"
else:
    EVAL_PYTHON = SLM_ROOT / ".venv_eval_v2" / "bin" / "python"


def _same_executable(left: str | Path, right: str | Path) -> bool:
    try:
        return Path(left).resolve().samefile(Path(right).resolve())
    except (OSError, FileNotFoundError):
        return False


def _run_from_eval_venv() -> int:
    if not EVAL_PYTHON.exists():
        print(
            "Missing SLM_A1A2/.venv_eval_v2. Create it and install "
            "requirements-evaluation-v2.txt before running these tests.",
            file=sys.stderr,
        )
        return 2
    if not _same_executable(sys.executable, EVAL_PYTHON):
        return subprocess.run(
            [str(EVAL_PYTHON), str(Path(__file__).resolve()), "--in-venv"],
            cwd=SLM_ROOT,
            check=False,
        ).returncode
    return 0


_RUNNING_IN_EVAL_VENV = _same_executable(sys.executable, EVAL_PYTHON)


if _RUNNING_IN_EVAL_VENV:

    class ErrantAlignmentIntegrationTests(unittest.TestCase):
        @classmethod
        def setUpClass(cls) -> None:
            from gec_alignment_v2 import get_engine

            cls.engine = get_engine()

        def test_engine_metadata_identifies_real_pinned_errant_stack(self) -> None:
            metadata = self.engine.metadata()
            self.assertEqual(metadata["engine"], "ERRANT")
            self.assertEqual(metadata["language"], "en")
            self.assertEqual(metadata["versions"]["errant"], "3.0.2")
            self.assertEqual(metadata["versions"]["spacy"], "3.8.7")
            self.assertEqual(metadata["versions"]["en-core-web-sm"], "3.8.0")
            self.assertTrue(metadata["parse_tokenise"])
            self.assertIn("spacy", metadata["tokenizer_class"])

        def test_insert_delete_punctuation_contraction_repetition_and_case(self) -> None:
            scenarios = (
                ("I walk home.", "I quickly walk home.", "M:ADV"),
                ("I really walk home.", "I walk home.", "U:ADV"),
                ("Hello world.", "Hello, world.", "M:PUNCT"),
                ("I do not know.", "I don't know.", "R:CONTR"),
                ("I I like tea.", "I like tea.", "U:PRON"),
                ("i like tea.", "I like tea.", "R:ORTH"),
            )
            from gec_alignment_v2 import score_text

            for source, correction, category in scenarios:
                with self.subTest(category=category):
                    result = score_text(source, [correction], correction)
                    primary = result["primary"]
                    self.assertGreater(primary["reference_edit_count"], 0)
                    self.assertEqual(primary["tp"], primary["reference_edit_count"])
                    self.assertEqual(primary["fp"], 0)
                    self.assertEqual(primary["fn"], 0)
                    self.assertIn(category, primary["category_lineage"])

        def test_whitespace_is_retained_as_errant_space_edits(self) -> None:
            from gec_alignment_v2 import score_text

            result = score_text(
                "She go home.", ["She goes home."], "She goes home.\n"
            )
            primary = result["primary"]
            self.assertEqual(primary["tp"], 1)
            self.assertEqual(primary["fp"], 1)
            self.assertEqual(primary["fn"], 0)
            self.assertTrue(
                any(
                    edit["type"] == "M:SPACE" and edit["c_str"] == "\n"
                    for edit in result["hypothesis_edits"]
                )
            )

        def test_identical_whitespace_input_is_repeatable_with_cache_trace(self) -> None:
            from gec_alignment_v2 import score_text

            args = ("She go home.", ["She goes home."], "She goes home.\n")
            first = score_text(*args)
            second = score_text(*args)
            for field in (
                "primary",
                "best_full_reference",
                "reference_scores",
                "best_reference_index",
                "hypothesis_edits",
                "selection_policy",
                "matching_policy",
            ):
                self.assertEqual(first[field], second[field])
            self.assertGreater(
                second["engine_provenance"]["cache"]["annotation_pair_hits"],
                first["engine_provenance"]["cache"]["annotation_pair_hits"],
            )

        def test_exact_correction_requires_same_source_span_and_target(self) -> None:
            from gec_alignment_v2 import score_text

            result = score_text(
                "They walk home.", ["They walked home."], "They jogged home."
            )
            self.assertEqual(
                (result["primary"]["tp"], result["primary"]["fp"], result["primary"]["fn"]),
                (0, 1, 1),
            )

        def test_multi_reference_selection_never_combines_edits(self) -> None:
            from gec_alignment_v2 import score_text

            result = score_text(
                "She go home.",
                ["She goes home.", "She go home today."],
                "She goes home today.",
            )
            self.assertEqual(len(result["hypothesis_edits"]), 2)
            self.assertEqual(len(result["reference_scores"]), 2)
            self.assertEqual(result["best_reference_index"], 0)
            self.assertEqual(
                [score["reference_index"] for score in result["reference_scores"]],
                [0, 1],
            )
            self.assertEqual(
                [len(score["reference_edits"]) for score in result["reference_scores"]],
                [1, 1],
            )
            self.assertEqual(
                [(score["tp"], score["fp"], score["fn"])
                 for score in result["reference_scores"]],
                [(1, 1, 0), (1, 1, 0)],
            )
            self.assertEqual(result["best_full_reference"]["reference_index"], 0)

        def test_primary_and_best_complete_reference_are_separate(self) -> None:
            from gec_alignment_v2 import score_text

            result = score_text(
                "She go home.",
                ["She goes home.", "She go home today."],
                "She go home today.",
            )
            self.assertEqual(result["primary"]["reference_index"], 0)
            self.assertEqual(result["primary"]["tp"], 0)
            self.assertEqual(result["best_reference_index"], 1)
            self.assertEqual(result["best_full_reference"]["tp"], 1)
            self.assertEqual(result["best_full_reference"]["fp"], 0)
            self.assertEqual(result["best_full_reference"]["fn"], 0)

        def test_reference_gold_annotations_are_cached_across_candidates(self) -> None:
            from gec_alignment_v2 import score_text

            before = self.engine._annotate_pair.cache_info().hits
            score_text("A child go home.", ["A child goes home."], "A child went home.")
            score_text("A child go home.", ["A child goes home."], "A child walk home.")
            after = self.engine._annotate_pair.cache_info().hits
            self.assertGreater(after, before)

        def test_type_is_diagnostic_and_not_part_of_correction_matching(self) -> None:
            from gec_alignment_v2 import ErrantEdit, _counts_and_diagnostics

            hypothesis = [ErrantEdit(1, 2, "go", 1, 2, "goes", "R:VERB")]
            reference = [ErrantEdit(1, 2, "go", 1, 2, "goes", "R:VERB:SVA")]
            result = _counts_and_diagnostics(hypothesis, reference)
            self.assertEqual((result["tp"], result["fp"], result["fn"]), (1, 0, 0))
            self.assertEqual(len(result["type_mismatches"]), 1)
            self.assertIn("R:VERB:SVA", result["category_lineage"])

        def test_empty_or_wrong_type_candidate_is_rejected(self) -> None:
            from gec_alignment_v2 import score_text

            for candidate in ("", "  ", None):
                with self.subTest(candidate=candidate):
                    with self.assertRaises((TypeError, ValueError)):
                        score_text("She go home.", ["She goes home."], candidate)

            with self.assertRaises(ValueError):
                score_text("She go home.", [""], "She goes home.")

else:

    class ErrantAlignmentIntegrationLauncherTests(unittest.TestCase):
        """Delegate discovery from the lab venv and fail unless real tests pass."""

        def test_all_errant_fixtures_pass_in_isolated_environment(self) -> None:
            result = _run_from_eval_venv()
            self.assertEqual(result, 0, "the isolated ERRANT test subprocess failed")


def main() -> int:
    unittest.main(argv=[sys.argv[0]], verbosity=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
