# Independent editorial review — benchmark_120 reviewed set (120 cases)

Scope: `SLM_A1A2/benchmark_120/reviewed/A1_cases.json` (60: A1-E001…E045 + A1-C001…C015)
and `SLM_A1A2/benchmark_120/reviewed/A2_cases.json` (60: A2-E001…E045 + A2-C001…C015).
Read-only audit. No case file was edited. This report
(`SLM_A1A2/benchmark_120/reviewed/independent_editorial_review.md`) is the ONLY file produced.

Independence: I read the prior audits (`A1_editorial_audit.md`, `A2_editorial_audit.md`)
as context, but all judgments below are my own from re-reading every
`task` / `student_text` / `gold.errors` / `corrected_text` /
`acceptable_alternatives` / `acceptable_corrections` / `control` triple.
I did not copy or paraphrase any smoke text. I did not look at any model output.
No inference, no ~200 test set, no phase-40 change.

Method (tools: `read` + `shell` only; `grep`/`glob` unusable in this environment):
re-read all 120 cases in full via `shell`+Python; verified IDs/uniqueness,
`length_words` with the validator regex `\b[\w]+(?:['’][\w]+)*\b`,
literal occurrence ×1 / non-overlap of every `original`, presence of every
`correction` in `corrected_text`, simultaneous-splice reconstruction of
`corrected_text` (45+45 incorrect), control identity
(`errors==[]`, `corrected_text==student_text`), BrE/AmE spans, task–text fit,
meaning preservation, minimal-edit discipline, classification plausibility,
A1/A2 length/naturalness; normalized + `SequenceMatcher` similarity vs the 40
smoke texts (threshold 0.78) and internally (A1×A1, A2×A2, A1×A2 lexical +
manual thematic/paraphrase read). No rate limit encountered.

## 1. Mechanical result (computed, not declared)

- IDs: 60/60 A1 + 60/60 A2 exact, no duplicates, no missing.
- `length_words`: 120/120 match the validator regex. A1 observed ~23–45 words
  (within 15–60); A2 ~35–59 words (within 25–100). No out-of-range case.
- Fragments: every `original` occurs literally exactly once in its
  `student_text`; every `correction` occurs in `corrected_text`; no overlaps;
  splice-reconstruction reproduces `corrected_text` in all 90 incorrect cases.
- Controls: 30/30 with `errors==[]` and `corrected_text==student_text`.
- `english_variant`: `unspecified; British and American variants accepted` throughout.
- No exact reuse of smoke texts. Max normalized similarity A1-E019 vs smoke
  A1-E13 ≈ 0.55; A1-E010 vs A1-E13 ≈ 0.51; rest lower; 0 candidates ≥ 0.78;
  0 internal duplicates ≥ 0.60 (lexical). Manual thematic read: no close
  paraphrase of any smoke item (see §4).

## 2. Severity scale used

- **BLOCKER**: case defective as frozen (grammatical `original` flagged as error,
  unflagged real error forcing re-annotation, meaning change, wrong span that
  breaks scoring). Must be fixed before freeze.
- **REVIEW**: usable but needs an integrator decision (pragmatic dependence,
  thin error, incomplete alternatives, task–text drift, unnatural control).
- **info**: observation, no action required.

**Verdict: 0 BLOCKERs.** All flagged errors are real errors; all corrections are
minimal and meaning-preserving; all classifications are defensible; all 30
controls are genuinely correct. Findings below are REVIEW/info only.

## 3. Findings

### 3.1 REVIEW (needs integrator decision, not blocking)

- **R1 — Injected additive connectors, pragmatic dependence (A1-E006, A1-E026).**
  E006 `plants but choose → plants and choose`, E026 `us, but I have → us, and I have`.
  Reading as addition (look+choose; puzzle+lemonade) `and` is correct, but a
  concessive reading of `but` is not logically impossible without wider context.
  At A1 this is the intended `and`/`but` confusion and I judge it acceptable,
  yet it relies on pragmatic intent. Proposal: keep, document as intentionally
  injected; do NOT add a `but`-preserving alternative.
- **R2 — Injected result connector (A1-E045).** `finishes at six, because I will
  be there at seven → so I will be there`. `because` reverses cause/result, so
  `so` is right, but the judgment needs the 6→7 temporal chain. Fine at A1 as a
  taught `so`/`because` contrast, but flag as the hardest A1 connector.
  Proposal: keep; optionally simplify task cue to make the sequence explicit.
- **R3 — `?` vs `.` counted as error (A1-E012, A1-E026).**
  `can you bring … after class. → after class?` Direct `can you` requests
  conventionally take `?` at A1, so I accept the PUNCTUATION error, but `.` is an
  orthographic convention, not grammar. Proposal: keep (benchmark explicitly has
  a PUNCTUATION type); do not use these two cases alone to claim grammar recall.
- **R4 — Single-error punctuation case (A2-E029).** Entire case is one missing
  final `.` (`arrive → arrive.`). Unequivocal but thin at A2; typographic rather
  than grammatical, low discrimination. Proposal: keep as a control-adjacent
  punctuation check OR replace before freeze with a grammatical A2 error if a
  slot opens; do not treat E029 as evidence of A2 grammar coverage.
- **R5 — Fronted time-adverbial alternative missing (A2-E004, A2-E015).**
  E004 `My sister every evening practises … → … every evening` (end position);
  E015 `I practise every evening the difficult parts … → … every evening`
  (verb–object split, unequivocal). End position is the natural minimal fix, but
  fronted `Every evening, …` is also grammatical and not listed in
  `acceptable_corrections` (only BrE/AmE `practise`/`practice` variants are).
  Proposal: add `Every evening, …` full-clause alternative to each error's
  `acceptable_corrections` (or document that fronting is dispreferred for
  minimal-edit scoring).
- **R6 — Task–text drift (A2-E008).** Task: borrowing things from a neighbor;
  text: feeding the neighbor's cat + returning keys. Keys could pass as borrowed,
  but cat-sitting is not borrowing. Language and OBJECT_PRONOUN errors
  (`sent she → her`, `to they → them`) are unaffected. Proposal: keep text
  (valid A2), optionally retitle task to pet-sitting/returning things.
- **R7 — Subtle article (A2-E026 `by water → by the water`).** Specific-reference
  `the` (the lake water) is the natural reading, so I accept the ARTICLE error,
  but bare `by water` is odd rather than starkly ungrammatical. Proposal: keep;
  do not use E026-article alone to claim article mastery.
- **R8 — Unnatural-but-grammatical control (A1-C004).** `he wants no lettuce`
  (`want no + noun`) is grammatical, deliberately marked. Correct to leave
  unflagged, but as an A1 model sentence it teaches a rare pattern. Proposal:
  keep as a hard control OR normalize to `doesn't want any lettuce` if a more
  natural control is preferred; either way it is NOT an error.

### 3.2 info (no action required)

- **I1 — Future-sentence injections are natural and form-unequivocal.**
  A1-E012/E022/E027/E029/E031/E033/E042/E045 (`Tomorrow/Next week/Next Sunday +
  will`), A2-E016/E032. Tasks do not always cue the future, but learners
  extending with a plan is natural; the error is always the `will` form
  (`will plays/swims/buys/rides/to V`), never the choice of `will` itself, so no
  ambiguity voids the error. Present-simple-for-schedule (`Tomorrow we play`)
  would still leave `will + -s/to` wrong.
- **I2 — Present perfect is well-formed (A2-E012, A2-E026).** `have draw → have
  drawn`, `have went → have gone` with present-relevance contexts
  (poster project; `several times / again this year`). Keeping `have` and fixing
  the participle is the minimal edit (deleting `have` to force past simple would
  violate minimality). Controls C001/C006 (`has been`, `have already chosen …
  yet`) are correct hard perfect controls.
- **I3 — Double-connector errors are unequivocal (A2-E016/E026/E032).**
  `Although …, but …` and `because …, so …` with both-licensed removals in
  `acceptable_corrections` — exemplary handling. A1 injected singles (R1/R2)
  intentionally license only one direction, which is correct for `and`/`so`.
- **I4 — Duplicate mechanism, distinct texts (A2-E014/E023 `enjoy to V → enjoy
  V-ing`).** Same subtype twice with different topics (cooking vs. toys).
  Acceptable for pattern coverage; noted for coverage accounting.
- **I5 — Tense mix left unflagged (A2-E033).** Generic present
  (`you need / cuts / heat`) + past narrative (`added / cooked / tasted`) reads as
  generic instruction followed by last-time report — defensible, not an error.
- **I6 — Backshift nuance (A2-E036).** `nobody have → nobody has` is the
  unequivocal error; keeping present perfect inside reported `asked if …` is
  defensible as the receptionist's result. No additional error.
- **I7 — Variant policy is consistent in effect.** A1 records full-text BrE↔AmE
  alts where the corrected text itself varies (E004 `practise/practice`, E018
  `favorite/favourite`); A2 licenses variants per-error (`further`, `practice`,
  `favorite`, `kilometers`, `It is`, `did not`, `that day`). Per the rubric both
  routes yield at most PARTIAL pending human review — no scoring asymmetry.
  Witnesses left correctly unflagged: `maths` (E009), `lift` (C002),
  `At the weekend` (C013), `practise` (C015/E004/E015), `favourite/colourful/
  travelled/tyres/programme` (A2), `neighbors/center` (AmE, unspecified).
- **I8 — `café` (A1-C011) is intact UTF-8 (`caf\xc3\xa9`); shell display of `é`
  as `�` is a font artifact, not file corruption.
- **I9 — Punctuation spans without the mark in `original`** (A1-E012/E026/E045,
  A2-E029, e.g. `after class. → after class?`, `at seven → at seven.`) are an
  established convention in this set (span = words, correction adds the mark).
  Mechanical checks pass; keep convention stable.

## 4. Similarity / paraphrase (no copying)

- Smoke-40: 0 exact reuses, 0 ≥ 0.78, max ≈ 0.55 (A1-E019), next ≈ 0.51
  (A1-E010) — both share only generic grocery vocabulary with smoke A1-E13, with
  different syntax, errors, and tasks. Manual read: recurring everyday themes
  (bus, picnic, cat, market) overlap at topic level only; no near-paraphrase of
  any smoke text in wording, structure, or error design.
- Internal 120: 0 pairs ≥ 0.60 lexically. Thematic neighbors are distinct:
  A1-E022 vs A1-E029 vs A2-E032 (bus; different routes/errors),
  A1-E014/A2-E006 (party; different errors), A1-E010/A2-E033 (food; different
  errors), A2-E014/A2-E023 (`enjoy`; different topics, I4). No intra-set
  paraphrase.

## 5. Audit table (120/120 read; verdict per case)

`OK` = no finding; `R*`/`I*` = finding above applies but case stays usable.
No BLOCKER in any row.

| ID | Verdict | ID | Verdict | ID | Verdict | ID | Verdict |
|---|---|---|---|---|---|---|---|
| A1-E001 | OK | A1-E016 | OK | A1-E031 | OK | A2-E016 | OK |
| A1-E002 | OK | A1-E017 | OK | A1-E032 | OK | A2-E017 | OK |
| A1-E003 | OK | A1-E018 | OK | A1-E033 | OK | A2-E018 | OK |
| A1-E004 | OK | A1-E019 | OK | A1-E034 | OK | A2-E019 | OK |
| A1-E005 | OK | A1-E020 | OK | A1-E035 | OK | A2-E020 | OK |
| A1-E006 | R1 | A1-E021 | OK | A1-E036 | OK | A2-E021 | OK |
| A1-E007 | OK | A1-E022 | OK (I1) | A1-E037 | OK | A2-E022 | OK |
| A1-E008 | OK | A1-E023 | OK | A1-E038 | OK | A2-E023 | OK (I4) |
| A1-E009 | OK | A1-E024 | OK | A1-E039 | OK | A2-E024 | OK |
| A1-E010 | OK | A1-E025 | OK | A1-E040 | OK | A2-E025 | OK |
| A1-E011 | OK | A1-E026 | R1+R3 | A1-E041 | OK | A2-E026 | R7 (I2) |
| A1-E012 | R3 (I1) | A1-E027 | OK (I1) | A1-E042 | OK (I1) | A2-E027 | OK |
| A1-E013 | OK | A1-E028 | OK | A1-E043 | OK | A2-E028 | OK |
| A1-E014 | OK | A1-E029 | OK (I1) | A1-E044 | OK | A2-E029 | R4 |
| A1-E015 | OK | A1-E030 | OK | A1-E045 | R2+R3 (I1) | A2-E030 | OK |
| A1-C001 | OK | A1-C006 | OK | A1-C011 | OK (I8) | A2-E031 | OK |
| A1-C002 | OK | A1-C007 | OK | A1-C012 | OK | A2-E032 | OK (I1) |
| A1-C003 | OK | A1-C008 | OK | A1-C013 | OK | A2-E033 | OK (I5) |
| A1-C004 | R8 | A1-C009 | OK | A1-C014 | OK | A2-E034 | OK |
| A1-C005 | OK | A1-C010 | OK | A1-C015 | OK | A2-E035 | OK |
| A2-E001 | OK | A2-E006 | OK | A2-E011 | OK | A2-E036 | OK (I6) |
| A2-E002 | OK | A2-E007 | OK | A2-E012 | OK (I2) | A2-E037 | OK |
| A2-E003 | OK | A2-E008 | R6 | A2-E013 | OK | A2-E038 | OK |
| A2-E004 | R5 | A2-E009 | OK | A2-E014 | OK (I4) | A2-E039 | OK |
| A2-E005 | OK | A2-E010 | OK | A2-E015 | R5 | A2-E040 | OK |
| A2-C001 | OK | A2-C006 | OK | A2-C011 | OK | A2-E041 | OK |
| A2-C002 | OK | A2-C007 | OK | A2-C012 | OK | A2-E042 | OK |
| A2-C003 | OK | A2-C008 | OK | A2-C013 | OK | A2-E043 | OK |
| A2-C004 | OK | A2-C009 | OK | A2-C014 | OK | A2-E044 | OK |
| A2-C005 | OK | A2-C010 | OK | A2-C015 | OK | A2-E045 | OK |

Counts: A1 incorrect 45 + controls 15; A2 incorrect 45 + controls 15. All 120 opened and judged.

## 6. Limitations (explicit)

- Read-only linguistic audit; no files edited, no validator/official freeze run
  (integrators own schema validation, freezing, sign-off).
- No model outputs, no inferences, no ~200-case test set examined; no
  difficulty/discrimination or reliability claims.
- No phase-40 change or re-annotation performed; proposals in §3 are for the
  integrators.
- Similarity is normalized-text `SequenceMatcher` + manual thematic read, not an
  exhaustive paraphrase detector; threshold 0.78 matches prior audits.
- `grep`/`glob` tools were broken in this session; all evidence came from
  `read` + `shell`+Python. No rate limit was hit (nothing retried).
