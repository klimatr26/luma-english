# A1 Editorial Audit — benchmark_120 reviewed set (60 cases)

Scope: `benchmark_120/reviewed/A1_cases.json` (60 cases: A1-E001..E045 incorrect,
A1-C001..C015 controls) audited against `benchmark_120/drafts/A1_*.json`.
Read-only sources: drafts, `scripts/normalize_benchmark_drafts.py`,
`scripts/validate_benchmark_120.py`, `benchmark_smoke_test_v2.json`
(similarity comparison only — nothing copied or paraphrased from it).
Raw drafts, normalizer and validator were NOT edited.

> This is an editorial audit, NOT a final validation. Final schema validation,
> freezing and sign-off belong to the integrators.

## 1. Mechanical checks performed (local script, read-only on all other files)

- 60 cases, exact ID set A1-E001..E045 + A1-C001..C015, no duplicates.
- Top-level fields per case: id, level, condition, task, student_text, gold,
  length_words, english_variant (`unspecified; British and American variants accepted`).
- Gold shape: `{is_correct, corrected_text, errors[{original, correction,
  acceptable_corrections (non-empty list), type, subtype, explanation}],
  acceptable_alternatives}`.
- Every `length_words` equals `count_words` per the validator regex
  `\b[\w]+(?:['’][\w]+)*\b`; all texts within 15–60 words (observed min 23,
  median 27.5, max 45).
- Every `original` is a literal substring of its student_text; error spans do
  not overlap; every `correction` is a substring of `corrected_text`;
  applying all replacements to student_text reproduces `corrected_text`
  exactly (splice-verified for all 45 incorrect cases).
- All 75 error `type` values belong to the validator TAXONOMY; no
  `QUESTION_FORMATION`, `NUMBER_AGREEMENT`, `POSSESSIVE_APOSTROPHE`,
  `BE_AGREEMENT` or `VERB_FORM_AFTER_DO` labels remain (they would only
  survive via inference — now canonical, see §4).
- Controls: `errors == []`, `corrected_text == student_text`,
  `acceptable_alternatives == []`.
- No duplicate normalized student_text inside the 60.
- Exclusion vs the 40 smoke texts: no exact reuse; max normalized similarity
  0.554 (A1-E019 vs A1-E13), no candidate ≥ 0.78.

## 2. Distribution (incorrect cases only)

| errors/text | cases | instances |
|---|---|---|
| 1 | 25 | 25 |
| 2 | 12 | 24 |
| 3 | 6 | 18 |
| 4 | 2 | 8 |
| total | 45 | 75 |

2-error: E001, E002, E003, E004, E005, E007, E008, E013, E021, E024, E026, E027.
3-error: E006, E012, E022, E031, E033, E042. 4-error: E029, E045.
1-error: E009, E010, E011, E014, E015, E016, E017, E018, E019, E020, E023,
E025, E028, E030, E032, E034, E035, E036, E037, E038, E039, E040, E041,
E043, E044.

Type instances (75): SUBJECT_VERB_AGREEMENT 6, SINGULAR_PLURAL 5, ARTICLE 4,
SUBJECT_PRONOUN 1, OBJECT_PRONOUN 2, POSSESSIVE 3, PREPOSITION_TIME 1,
PREPOSITION_PLACE 2, VERB_PREPOSITION 2, WORD_ORDER 4, QUESTION_FORM 4,
NEGATION 2, PRESENT_SIMPLE 1, COMPARATIVE 1, SUPERLATIVE 1, SOME_ANY 1,
MUCH_MANY 1, COUNTABLE_UNCOUNTABLE 2, BASIC_LEXICAL_CHOICE 3, SPELLING 2,
CAPITALIZATION 5, PUNCTUATION 4, BASIC_CONNECTOR 3, BASIC_FUTURE 8,
PAST_SIMPLE 3, PRESENT_CONTINUOUS 2, BE_FORM 2.
Required coverage present: BE_FORM (E013×2), BASIC_FUTURE (8×),
SINGULAR_PLURAL (5×), QUESTION_FORM (4×), COUNTABLE_UNCOUNTABLE (E005, E031),
CAPITALIZATION (5×), BASIC_CONNECTOR (E006, E026, E045) — each an
unequivocal A1-level error (see per-ID notes).

## 3. Dialectal / style policy applied

Per the smoke policy (BrE and AmE accepted; a valid BrE↔AmE change is
acceptable but unnecessary and never an error): `practise` (E004, C015),
`favorite` (E018), `At the weekend` (C013), `neighbour` (C002 task),
`maths` (E009), `lift` (C002) are left unflagged. Full-text BrE/AmE
alternatives are recorded only where the corrected text itself has a genuine
variant: E004 (`practise`→`practice`) and E018 (`favorite`→`favourite`) in
`acceptable_alternatives`. No stylistic rewriting anywhere (minimum change).

## 4. Per-ID changes and linguistic judgment

Untouched student_text + task, gold normalized to canonical type/subtype
(acceptable_corrections filled, subtypes added): E001, E003, E004, E008,
E009, E011, E013, E014, E015, E016, E018, E019, E020, E023,
E025, E028, E030, E034, E035, E036, E037, E038, E039, E040, E041,
E043, E044, and all controls C001–C015 (flat draft shape wrapped into
`gold`; one count corrected: C009 `hide-and-seek` = 3 tokens → 36 words).
Notable typing decisions:

- E002 `NUMBER_AGREEMENT` → SINGULAR_PLURAL (×2); E005/E037
  `POSSESSIVE_APOSTROPHE` → POSSESSIVE; E008/E027/E038 `QUESTION_FORMATION`
  → QUESTION_FORM (deliberately explicit: the validator's inference order
  would otherwise map "present simple question word order" to WORD_ORDER).
- E013 `BE_AGREEMENT` → BE_FORM (×2): only the be-form is wrong, the -ing
  forms are intact, so BE_FORM — not PRESENT_CONTINUOUS — is the minimal
  label. This also avoids tagging every agreement slip as
  SUBJECT_VERB_AGREEMENT.
- E023 `POSSESSIVE_DETERMINER` → POSSESSIVE (`its` vs `it's`).
- E028 `VERB_FORM_AFTER_DO` → PRESENT_SIMPLE (`doesn't eats` → `doesn't
  eat`).
- E021 fragments widened (`class go`→`class went`, `We see`→`We saw`) so
  originals are unambiguous; both PAST_SIMPLE irregular.
- E007 rewritten (stricter review): the former adverb-placement errors
  (`we in the playground often play`, `sometimes with us sits`) were
  marked-but-grammatical orders, so flagging them violated the no-style-
  correction rule — a false positive the initial audit missed (see §5).
  Both errors are now unequivocal phrase breaks: `a word in the
  playground game` → `a word game in the playground` (split noun phrase;
  the `a word game` content is preserved literally) and `questions animals
  about` → `questions about animals` (preposition stranded after its
  object). The rest of the text (`sometimes sits with us`) is now
  correctly left unflagged. → 2 errors.
- E024 keeps `fewer pockets` (grammatical; register is not an error — no
  style rewrite). C004 keeps `he wants no lettuce` (grammatical, deliberately
  non-canonical phrasing as a hard control).

Student_text extended with natural learner errors (same topic/task, still
15–60 words, varied mechanisms — no repeated template):

- E010 redesigned (stricter review): `don't have some paper plates` admits
  a valid specific-subset scope reading, so it was not a gold error.
  Replaced by a broken partitive `any of paper plates` → `any paper
  plates` (SOME_ANY, subtype `partitive_any_determiner`; `any of the paper
  plates` licensed in `acceptable_corrections`). → 1 error, 26 words.
- E017 redesigned (stricter review): stative `at the table drawer` admits
  a valid next-to-the-drawer location reading. Replaced by `into the table
  drawer` → `in the table drawer` (PREPOSITION_PLACE; `into` is incompatible
  with the stative `are`). → 1 error.

- E005 (+1): appended `There is a nice furniture near the window.` →
  COUNTABLE_UNCOUNTABLE. Joins the possessive error → 2 errors.
- E006 (+2): `and but choose` → BASIC_CONNECTOR (structural double
  coordinator; correction keeps `and choose`. Replaces the former `but→and`
  swap after R1: a concessive reading of lone `but` could not be excluded,
  while `and but` is ungrammatical under every reading); appended
  `My grandmother buy me…` → SUBJECT_VERB_AGREEMENT. → 3 errors.
- E012 (+1): appended `Tomorrow we will plays it again after lunch` (no final
  stop) → BASIC_FUTURE + sentence-final PUNCTUATION. → 3 errors. (Caught and
  fixed during audit: the appended sentence initially carried a period,
  which would have voided the punctuation error.)
- E022 (+2): appended `Next week we will swims in the big pool. i am very
  happy about it.` → BASIC_FUTURE + CAPITALIZATION (`I`). → 3 errors.
- E024 (+1): `it has` sentence-initial → CAPITALIZATION. → 2 errors.
- E026 (+1): `and but I have` → BASIC_CONNECTOR (structural double
  coordinator; correction keeps `and I have`. Replaces the former `but→and`
  swap after R1 for the same reason as E006). The `after school.` → `?`
  PUNCTUATION error is kept as valid (R3 accepted). → 2 errors.
- E027 (+1): appended `We will to sing it together.` → BASIC_FUTURE. →
  2 errors.
- E029 reordered (stricter review): the former `I by bicycle go` is a
  marked-but-grammatical fronting, so it became `I go bicycle by` →
  `I go by bicycle` (WORD_ORDER; `bicycle by` is ungrammatical under every
  reading). Appended `tomorrow we will to visit a new sports hall with
  rooms for childs to play.` → CAPITALIZATION + BASIC_FUTURE +
  SINGULAR_PLURAL (irregular `children`). → 4 errors.
- E031 redesigned (stricter review): `a bread` admits a kind/loaf coercion
  reading at a bakery. Replaced by `many bread` → `some bread`
  (COUNTABLE_UNCOUNTABLE, subtype `quantifier_plural_mass`; `a lot of
  bread` licensed too; a plural `breads` kind reading would change the
  meaning, so it is not the primary correction). `on saturdays` →
  CAPITALIZATION (day name); appended `Tomorrow I will buys a cake…` →
  BASIC_FUTURE. → 3 errors.
- E032 redesigned (stricter review): `in the chair` admits a storage-
  compartment reading. Replaced by `onto the chair` → `on the chair`
  (PREPOSITION_PLACE; `onto` expresses movement and is incompatible with
  the stative `are`). → 1 error.
- E033 (+2): `at shop` (article omission) → ARTICLE; appended `Tomorrow we
  will rides to the lake.` → BASIC_FUTURE. → 3 errors.
- E042 reordered (stricter review): the former `I by bus visit` is a
  marked-but-grammatical fronting, so it became `I visit by my grandmother
  bus` → `I visit my grandmother by bus` (WORD_ORDER; `by my grandmother
  bus` is not a valid phrase under any reading). Appended `Next Sunday we
  will to bring a cake, and my sister and I helps her in the kitchen.` →
  BASIC_FUTURE + SUBJECT_VERB_AGREEMENT (plural subject + base form, not a
  be-error). → 3 errors.
- E045 reordered (stricter review): the former `because of … → so` fix
  changed the cause/result relation and was not minimal. Same topic, still
  exactly 4 errors (capital/connector/future/punct, no overlap): `Hi ben`
  → CAPITALIZATION; `because of my swimming lesson` → `because my swimming
  lesson` (BASIC_CONNECTOR — removes `of`; `because of` never takes a full
  clause, so the error is structural while the causal meaning is preserved);
  `will to be` → BASIC_FUTURE; final `at six` → `at six.` PUNCTUATION (R3
  accepted). Corrected: `…I will be there at seven because my swimming
  lesson finishes at six.` — fully natural, no comma splice.

Controls C001–C015 kept verbatim (all genuinely correct): negation-adjacent
`nobody hides` (C009), adverb placement `often/sometimes/usually`
(C001/C005/C012), `get off` + `near` (C011), time expressions `half past
three` (C003), `in May` (C007), BrE `At the weekend` (C013) and `practise`
(C015) as no-touch dialect traps, past-simple narrative (C014), and the
stylistically marked but grammatical `wants no lettuce` (C004).

## 5. Open points / blockers

- Stricter-review resolution (this revision): 8 cases reworked because the
  flagged spans were marked-but-grammatical English, which the no-style-
  correction rule forbids flagging — a false-positive class the initial
  audit missed. Why it was missed: (a) adverbial fronting (`in the
  playground often play`, `I by bicycle go`, `I by bus visit`) and the
  canonical `sometimes sits with us` are stylistically marked yet
  grammatical, and the first pass judged markedness as error; (b) stative
  prepositions are polysemous (`at` ≈ next to, `in` ≈ inside a compartment),
  so only movement prepositions (`into`, `onto`) with stative `be` are
  reading-independent errors; (c) `some` under negation has a valid
  specific-subset scope reading, and `a` + mass noun has a kind/loaf
  coercion reading — both rescued by semantics, unlike the broken partitive
  (`any of` + bare noun) and `many` + mass noun that replace them;
  (d) the E045 `because of → so` fix rewrote the causal relation instead of
  the minimal `of`-deletion. All replacements are categorially
  ungrammatical under every reading (split noun phrase, `bicycle by`,
  invalid `by`-phrase, `into`/`onto` + stative, of-less partitive,
  `many` + mass, `because of` + clause). Distribution
  (25×1/12×2/6×3/2×4, 75 instances), type counts, BASIC_CONNECTOR coverage
  (3: E006, E026, E045), word counts, fragment literals and gold
  reconstruction re-verified after the change (global min/med/max
  23/27.5/45; only E010 moved, 25→26 words).
- `A1_cases.json` is now formatted with indent 2 + newlines (was one compact
  line); content identical apart from the 8 reworked cases.
- R3 accepted without change: `?`/`!`-convention PUNCTUATION in E012/E026
  (and the E045 final stop) stands; these cases alone must not evidence
  grammar recall.
- R8 accepted without change: control A1-C004 (`he wants no lettuce`)
  untouched — grammatical hard control, NOT an error.
- No blocking linguistic issue remains in these 2 files to my knowledge.
- Environment note: the `grep` tool is unusable in this session (PowerShell
  `Microsoft.PowerShell.Archive` module failure); all verification was done
  with `read` and a local throwaway script in the temp dir.
- No rate limit encountered.
- Not done here (other agents / integrators): A2 set, runtime, evaluation,
  official validator run over the assembled set, freeze/sign-off — hence no
  final-validation claim.
