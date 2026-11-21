"use strict";

const assert = require("node:assert/strict");
const ReviewCore = require("./src/review_core.js");

const SCHEMA_VERSION = "human_review_v2/1.0";
const BACKUP_SCHEMA_VERSION = "human_review_web.backup/1.0";
const PACKET_SHA = "a".repeat(64);

function blankReview() {
  return {
    schema_version: SCHEMA_VERSION,
    reviewer_id: null,
    review_date: null,
    response_assessable: null,
    rationale: null,
    detection: null,
    correction: null,
    meaning_preservation: null,
    level_appropriateness: null,
    grammatical_explanation: null,
    pedagogical_clarity: null,
    clean_text_handling: null,
    meaning_preserved: null,
    explanations_ok: null,
    verdict: null,
  };
}

function completeReview(originalHasErrors, overrides = {}) {
  const review = {
    schema_version: SCHEMA_VERSION,
    reviewer_id: "reviewer-ana",
    review_date: "2026-10-11",
    response_assessable: true,
    rationale: "La respuesta se entiende y la corrección es adecuada.",
    detection: originalHasErrors ? 2 : "NA",
    correction: originalHasErrors ? 2 : "NA",
    meaning_preservation: 2,
    level_appropriateness: 2,
    grammatical_explanation: 2,
    pedagogical_clarity: 2,
    clean_text_handling: originalHasErrors ? "NA" : 2,
    meaning_preserved: true,
    explanations_ok: true,
    verdict: "CORRECT",
  };
  return { ...review, ...overrides };
}

function blankPacketItem() {
  return {
    review_template: blankReview(),
  };
}

function validBackup() {
  return {
    schema_version: BACKUP_SCHEMA_VERSION,
    packet_sha256: PACKET_SHA,
    profile: { reviewer_id: "", review_date: "" },
    current_id: "blind-2",
    entries: [
      {
        blind_output_id: "blind-1",
        review: completeReview(false),
        original_has_errors: false,
        completed: true,
      },
      {
        blind_output_id: "blind-2",
        review: blankReview(),
        original_has_errors: null,
        completed: false,
      },
    ],
  };
}

assert.deepEqual(ReviewCore.CRITERIA, [
  "detection",
  "correction",
  "meaning_preservation",
  "level_appropriateness",
  "grammatical_explanation",
  "pedagogical_clarity",
  "clean_text_handling",
]);
assert.deepEqual(ReviewCore.FIELDS, [
  "schema_version",
  "reviewer_id",
  "review_date",
  "response_assessable",
  "rationale",
  ...ReviewCore.CRITERIA,
  "meaning_preserved",
  "explanations_ok",
  "verdict",
]);

assert.deepEqual(ReviewCore.parseJSONStrict('{"x":1,"items":[true,null]}'), { x: 1, items: [true, null] });
assert.throws(
  () => ReviewCore.parseJSONStrict('{"x":1,"x":2}'),
  /Clave JSON duplicada/,
  "duplicate root keys must be rejected",
);
assert.throws(
  () => ReviewCore.parseJSONStrict(String.raw`{"outer":{"x":1,"\u0078":2}}`),
  /Clave JSON duplicada/,
  "nested keys with equivalent escaped names must be rejected",
);
assert.throws(() => ReviewCore.parseJSONStrict('{"value":NaN}'), SyntaxError, "NaN is not valid JSON");
assert.throws(() => ReviewCore.parseJSONStrict('{"value":Infinity}'), SyntaxError, "Infinity is not valid JSON");
assert.throws(() => ReviewCore.parseJSONStrict('(()=>{ return 1; })()'), SyntaxError, "JSON input must never be evaluated as code");

const clonedBlank = ReviewCore.blankReview(blankPacketItem());
assert.deepEqual(clonedBlank, blankReview());
clonedBlank.reviewer_id = "changed";
assert.equal(blankPacketItem().review_template.reviewer_id, null, "blankReview must clone the template");

assert.deepEqual(ReviewCore.validateReview(completeReview(false), false), [], "control review should validate");
assert.deepEqual(ReviewCore.validateReview(completeReview(true), true), [], "incorrect-text review should validate");
assert.deepEqual(
  ReviewCore.validateReview(completeReview(false, { detection: 1 }), false).some((error) => error.includes("detection debe ser \"NA\"")),
  true,
  "controls require NA for detection",
);
assert.deepEqual(
  ReviewCore.validateReview(completeReview(true, { clean_text_handling: 1 }), true).some((error) => error.includes("clean_text_handling debe ser \"NA\"")),
  true,
  "incorrect-text cases require NA for clean-text handling",
);

const invalidDate = ReviewCore.validateReview(completeReview(false, { review_date: "2026-02-29" }), false);
assert.ok(invalidDate.some((error) => error.includes("fecha válida")), "invalid calendar dates must fail");
assert.deepEqual(ReviewCore.validateReview(completeReview(false, { review_date: "2024-02-29" }), false), [], "leap dates must pass");

const boolRating = ReviewCore.validateReview(completeReview(false, { clean_text_handling: true }), false);
assert.ok(boolRating.some((error) => error.includes("los booleanos no son notas")), "true must not count as rating 1");

const unassessable = {
  ...completeReview(false),
  response_assessable: false,
  rationale: "La respuesta está vacía y no se puede valorar.",
  detection: "NA",
  correction: "NA",
  meaning_preservation: "NA",
  level_appropriateness: "NA",
  grammatical_explanation: "NA",
  pedagogical_clarity: "NA",
  clean_text_handling: "NA",
  meaning_preserved: "NA",
  explanations_ok: "NA",
  verdict: "INVALID_CASE",
};
assert.deepEqual(ReviewCore.validateReview(unassessable, null), [], "unassessable reviews may omit original condition");
assert.ok(
  ReviewCore.validateReview(completeReview(false), null).some((error) => error.includes("Debe indicar si el texto original")),
  "assessable reviews require the human auxiliary condition choice",
);
assert.ok(
  ReviewCore.validateReview({ ...unassessable, detection: 0 }, null).some((error) => error.includes("debe ser \"NA\" cuando la respuesta no es evaluable")),
  "unassessable reviews require all criterion anchors to be NA",
);

const serialized = ReviewCore.serializeCompletedReviews([
  {
    blind_output_id: "draft-only",
    review: blankReview(),
    original_has_errors: null,
    completed: false,
  },
  {
    blind_output_id: "blind-1",
    review: completeReview(false),
    original_has_errors: false,
    completed: true,
  },
]);
assert.equal(serialized.records.length, 1, "drafts must not be exported");
assert.ok(serialized.text.endsWith("\n"), "nonempty JSONL must end with a newline");
assert.deepEqual(Object.keys(serialized.records[0]), ["blind_output_id", ...ReviewCore.FIELDS]);
assert.ok(!("original_has_errors" in serialized.records[0]), "the auxiliary condition must not enter review records");
assert.ok(!("case_id" in serialized.records[0]) && !("config_id" in serialized.records[0]));
assert.ok(!serialized.text.includes("draft-only"), "incomplete entries must never be exported");
assert.equal(serialized.text.split("\n").filter(Boolean).length, 1);
assert.throws(
  () => ReviewCore.serializeCompletedReviews([
    { blind_output_id: "same", review: blankReview(), original_has_errors: null, completed: false },
    { blind_output_id: "same", review: completeReview(false), original_has_errors: false, completed: true },
  ]),
  /duplicado/,
  "duplicate IDs must be rejected even when one entry is a draft",
);
assert.throws(
  () => ReviewCore.serializeCompletedReviews([
    { blind_output_id: "incomplete", review: blankReview(), original_has_errors: null, completed: true },
  ]),
  /reviewer_id/,
  "completed but incomplete reviews must not be exported",
);
assert.deepEqual(ReviewCore.serializeCompletedReviews([]), { text: "", records: [] });

assert.deepEqual(ReviewCore.validateBackup(validBackup(), PACKET_SHA, ["blind-1", "blind-2"]), []);

const wrongPacketSHA = validBackup();
wrongPacketSHA.packet_sha256 = "b".repeat(64);
assert.ok(
  ReviewCore.validateBackup(wrongPacketSHA, PACKET_SHA, ["blind-1", "blind-2"]).some((error) => error.includes("no coincide")),
  "backup must be bound to the exact packet digest",
);

const wrongSchema = validBackup();
wrongSchema.schema_version = "human_review_web.backup/0.9";
assert.ok(ReviewCore.validateBackup(wrongSchema, PACKET_SHA, ["blind-1", "blind-2"]).some((error) => error.includes("schema_version")));

const duplicateBackupID = validBackup();
duplicateBackupID.entries[1].blind_output_id = "blind-1";
assert.ok(ReviewCore.validateBackup(duplicateBackupID, PACKET_SHA, ["blind-1", "blind-2"]).some((error) => error.includes("duplicado")));

const unknownBackupID = validBackup();
unknownBackupID.entries[1].blind_output_id = "not-in-packet";
assert.ok(ReviewCore.validateBackup(unknownBackupID, PACKET_SHA, ["blind-1", "blind-2"]).some((error) => error.includes("desconocido")));

const extraBackupField = validBackup();
extraBackupField.entries[1].private_identity = "must-not-be-here";
assert.ok(ReviewCore.validateBackup(extraBackupField, PACKET_SHA, ["blind-1", "blind-2"]).some((error) => error.includes("campos no permitidos")));

const invalidBackupType = validBackup();
invalidBackupType.entries[1].original_has_errors = "false";
assert.ok(ReviewCore.validateBackup(invalidBackupType, PACKET_SHA, ["blind-1", "blind-2"]).some((error) => error.includes("original_has_errors debe ser true, false o null")));

const backupPrivateReviewField = validBackup();
backupPrivateReviewField.entries[1].review.case_id = "case-should-not-be-present";
assert.ok(ReviewCore.validateBackup(backupPrivateReviewField, PACKET_SHA, ["blind-1", "blind-2"]).some((error) => error.includes("campos no permitidos")));

const completedBadBackup = validBackup();
completedBadBackup.entries[0].review.detection = true;
assert.ok(
  ReviewCore.validateBackup(completedBadBackup, PACKET_SHA, ["blind-1", "blind-2"]).some((error) => error.includes("los booleanos no son notas")),
  "completed backup entries must pass the full review contract",
);

assert.throws(() => ReviewCore.blankReview({ review_template: { schema_version: SCHEMA_VERSION } }), /no coincide/);

process.stdout.write("review_core tests passed\n");
