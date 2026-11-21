# Evaluation rubric — Fase 2 writing A1/A2 (development benchmark, 120 cases)

Independent scoring rubric for the 120-case development benchmark. It covers
only already-collected raw outputs against the frozen gold file. It performs
no inference, downloads no models, and never references the final ~200-case
test set.

Companion script: `SLM_A1A2/scripts/evaluate_benchmark_120.py`
(standard library only). Unit tests:
`SLM_A1A2/scripts/test_evaluate_benchmark_120.py` (synthetic texts only).

## 1. Case verdicts

Each (model, case) pair receives one provisional verdict, plus a final verdict
once an optional traced human evaluation exists:

| Verdict | Meaning |
|---|---|
| `CORRECT` | All real errors handled acceptably, no false error invented, no new error introduced, `corrected_text` matches the gold primary text, `is_correct` flag right, schema valid. Provisional until a human confirms meaning and explanations. |
| `PARTIAL` | Some but not all required corrections handled; or the text fix is right but the error declaration is wrong/incomplete; or the match relies on a gold-licensed alternative pending human confirmation; or the flag contradicts the fix. |
| `INCORRECT` | No gold error covered; or the output is unparseable / schema-invalid; or a correct control was changed or false-flagged. |
| `INVALID_CASE` | The benchmark case itself is defective or genuinely ambiguous. Applies to **every** model, is excluded from all aggregates, and never triggers a gold rewrite after outputs were seen. A human can also mark a case invalid (requires reviewer + rationale). |

Score levels mirror the smoke-phase `scoring_policy`: strict correctness
requires every condition at once; anything less is at most `PARTIAL`.

## 2. Error detection: TP / FP / FN (strict, string-based)

Counts are computed per case over the gold `errors` list vs the predicted
`errors` list. Matching is deliberately strict and auditable:

- A true positive (TP) requires **all three** (matching the existing frozen evaluator behavior):
  1. the predicted `original` string matches the gold original fragment (NFKC, case-sensitive, surrounding whitespace ignored);
  2. the predicted `correction` string exactly equals a gold-licensed string
     (the error's `correction` or one of its `acceptable_corrections`;
     NFKC, case-sensitive, surrounding whitespace ignored), **and**
  3. that same correction string occurs verbatim inside the predicted `corrected_text`.
- A gold error with no such three-part match is a false negative (FN), including:
  fixed-in-text-but-not-declared, declared-but-not-realized-in-text, and plain
  misses.
- A predicted error matching no gold error is a false positive (FP).
- Each predicted entry is consumed at most once (greedy, in gold order).

Precision, recall and F0.5 (β = 0.5, precision-weighted) use micro-totals over
the **incorrect** cases (the primary detection scope; controls are measured
separately in §3):

- `precision = TP / (TP + FP)` (1.0 when nothing was predicted and nothing was
  missed; 0.0 when nothing was predicted but errors were missed).
- `recall = TP / (TP + FN)` (1.0 when there is no gold error).
- `F0.5 = 1.25·P·R / (0.25·P + R)` (0.0 when the denominator is 0).

## 3. Control metrics (30 controls)

| Metric | Definition |
|---|---|
| CTMR (control text modification rate) | Controls whose `corrected_text` differs from `student_text` beyond surrounding whitespace, / 30. |
| CFAR (control false-alarm rate) | Controls with `is_correct=false` **or** non-empty `errors`, / 30. |
| Fully preserved | Controls with byte-equivalent text (modulo surrounding whitespace) **and** `is_correct=true` **and** `errors=[]`, / 30. |

A clean control (`CORRECT`) needs no human explanation review because it
claims nothing. Any modified or false-flagged control is `INCORRECT`
(provisional) and stays reviewable so a human can rescue genuine
dialect-only variants (British ↔ American) with an explicit rationale; the
script never auto-accepts a control rewrite.

## 4. Format accounting (kept separate)

For every raw response the script records independently:

- `parse_status`: `direct` (the trimmed response parses as JSON by itself),
  `recoverable` (parses only after removing a fenced block and/or extracting
  the balanced `{…}` span), or `invalid` (unparseable).
- `has_fence`: triple-backtick block present.
- `text_outside_json`: non-whitespace text before/after the JSON object
  (commentary, greetings, explanations).
- `schema_valid` + `schema_errors`: the parsed object checked against the
  strict response schema (`is_correct` boolean; `corrected_text` string;
  `errors` array of `original`/`correction`/`type`/`explanation` non-empty
  strings; `feedback` string).
- `strict_json_compliant`: true **only** when `direct` + `schema_valid` +
  no fences + no outside text. **Extra text around the JSON is never
  reinterpreted as strict compliance**; it is at best `recoverable`.

## 5. No semantic presumption from string similarity

- A `corrected_text` equal only to a gold `acceptable_alternatives` entry, or
  a correction matched only via `acceptable_corrections` (not the primary),
  yields at most `PARTIAL` (provisional) and is queued for human review —
  never auto-`CORRECT`.
- Case-insensitive / punctuation-insensitive resemblance (`fuzzy_only`) is
  reported as a review hint and never counts as a TP.
- Cases whose gold carries an `evaluation_note`, shared licensed strings
  across gold errors, undeclared fixes, or declared-but-unrealized
  corrections are flagged `needs_human_review` with a machine-readable reason.

## 6. Meaning and explanations need explicit human judgment

Automatic checks verify that explanations are present and non-empty; they
cannot verify that an explanation is *correct* or that the student's meaning
was preserved. Therefore:

- Every provisional `CORRECT` on an incorrect case carries
  `meaning_explanation_unconfirmed` and `needs_human_review=true`.
- Confirmation requires a human evaluation record with `reviewer`,
  `rationale`, and the `meaning_preserved` / `explanations_ok` judgments.
  Records without reviewer + rationale are ignored (flagged
  `human_evaluation_missing_traceability`) and the score stays provisional.
- The summary always reports `human_confirmed_cases` alongside provisional
  counts, and per-case output keeps `verdict_provisional` next to
  `verdict_final` plus a `provisional` boolean.

## 7. Comparison table (never a single score)

The summary JSON reports, for the scored (non-invalid) cases: final and
provisional verdict counts; format/schema counts; micro TP/FP/FN with
precision/recall/F0.5 over incorrect cases; CTMR/CFAR/preserved rates;
`needs_human_review` count; and breakdowns by level (A1/A2 with their own
verdicts + detection), by gold error taxonomy (per-type recall), by gold
error count (1 / 2 / 3 / 4+), and by student-text length
(short ≤30 / medium 31–60 / long >60 words). Raw-row telemetry
(latency, tokens) is passed through as descriptive statistics only and never
affects verdicts.

## 8. Invalid-case and freeze rules

- A case found defective after freezing is marked invalid for every model and
  excluded from every aggregate and comparison. Its gold text is never edited
  after model outputs were observed.
- Duplicate raw rows for one case abort the run instead of guessing; raw rows
  referencing unknown case IDs abort as well.

## 9. Worked synthetic examples (not benchmark texts)

Assume gold error `have → has` with `acceptable_corrections: ["has"]`.

1. Model returns strict JSON, `is_correct:false`,
   `corrected_text` = fixed sentence containing `has`, one error entry
   (`have → has`). → TP=1, FP=0, FN=0, `exact_primary` → provisional `CORRECT`,
   review queued for meaning/explanations.
2. Same but the entry declares `have → 's got` (unlicensed) while the text
   contains `has`. → FN=1 (`undeclared_fix`), FP=1 → provisional `PARTIAL`,
   review queued.
3. Control text returned with an added comma and `is_correct:true`,
   `errors:[]`. → CTMR counts it, CFAR does not, verdict `INCORRECT`
   provisional, reviewable for a human dialect/style call.
4. Response `Sure! ```json {...} ``` You're welcome`. → `recoverable`,
   `has_fence:true`, `text_outside_json:true`, never strict; scored on the
   extracted object.
