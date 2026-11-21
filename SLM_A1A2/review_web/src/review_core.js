(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.ReviewCore = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SCHEMA_VERSION = "human_review_v2/1.0";
  const BACKUP_SCHEMA_VERSION = "human_review_web.backup/1.0";
  const CRITERIA = Object.freeze([
    "detection",
    "correction",
    "meaning_preservation",
    "level_appropriateness",
    "grammatical_explanation",
    "pedagogical_clarity",
    "clean_text_handling",
  ]);
  const FIELDS = Object.freeze([
    "schema_version",
    "reviewer_id",
    "review_date",
    "response_assessable",
    "rationale",
    ...CRITERIA,
    "meaning_preserved",
    "explanations_ok",
    "verdict",
  ]);
  const VERDICTS = new Set(["CORRECT", "PARTIAL", "INCORRECT", "INVALID_CASE"]);
  const HEX_SHA256_RE = /^[0-9a-f]{64}$/;
  const ENTRY_FIELDS = Object.freeze([
    "blind_output_id",
    "review",
    "original_has_errors",
    "completed",
  ]);
  const BACKUP_FIELDS = Object.freeze([
    "schema_version",
    "packet_sha256",
    "profile",
    "entries",
    "current_id",
  ]);
  const PROFILE_FIELDS = Object.freeze(["reviewer_id", "review_date"]);

  function hasOwn(object, key) {
    return Object.prototype.hasOwnProperty.call(object, key);
  }

  function isObject(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  function sortedKeys(value) {
    return Object.keys(value).sort();
  }

  function compareExactKeys(value, expected, label, errors) {
    const supplied = new Set(Object.keys(value));
    const wanted = new Set(expected);
    const missing = expected.filter((key) => !supplied.has(key)).sort();
    const unknown = [...supplied].filter((key) => !wanted.has(key)).sort();
    if (missing.length) {
      errors.push(`${label}: faltan campos obligatorios: ${missing.join(", ")}.`);
    }
    if (unknown.length) {
      errors.push(`${label}: campos no permitidos: ${unknown.join(", ")}.`);
    }
  }

  function collectNonFinite(value, path, errors, active) {
    if (typeof value === "number" && !Number.isFinite(value)) {
      errors.push(`Hay un número no finito en ${path}.`);
      return;
    }
    if (value === null || typeof value !== "object") return;
    if (active.has(value)) {
      errors.push(`Hay una referencia circular en ${path}.`);
      return;
    }
    active.add(value);
    if (Array.isArray(value)) {
      value.forEach((item, index) => collectNonFinite(item, `${path}[${index}]`, errors, active));
    } else {
      Object.keys(value).forEach((key) => {
        collectNonFinite(value[key], `${path}.${key}`, errors, active);
      });
    }
    active.delete(value);
  }

  function isISODate(value) {
    if (typeof value !== "string") return false;
    const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value);
    if (!match) return false;
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    if (year < 1 || month < 1 || month > 12) return false;
    const leap = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
    const monthDays = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    return day >= 1 && day <= monthDays[month - 1];
  }

  function isRating(value) {
    return (typeof value === "number" && Number.isInteger(value) && [0, 1, 2].includes(value)) || value === "NA";
  }

  function blankReview(item) {
    if (!isObject(item) || !isObject(item.review_template)) {
      throw new TypeError("El elemento debe incluir una plantilla de revisión.");
    }
    const template = item.review_template;
    const missing = FIELDS.filter((field) => !hasOwn(template, field));
    const unknown = Object.keys(template).filter((field) => !FIELDS.includes(field));
    if (missing.length || unknown.length) {
      throw new TypeError("La plantilla de revisión no coincide con el esquema esperado.");
    }
    const copy = {};
    FIELDS.forEach((field) => {
      copy[field] = template[field];
    });
    return copy;
  }

  function parseJSONStrict(raw) {
    if (typeof raw !== "string") {
      throw new TypeError("El contenido JSON debe ser texto.");
    }

    // JSON.parse checks the complete JSON grammar and rejects NaN/Infinity.
    // A small second pass is needed because the built-in parser keeps only the
    // final value for duplicate object keys.
    const parsed = JSON.parse(raw);
    let index = 0;

    function skipWhitespace() {
      while (index < raw.length && /[\u0009\u000a\u000d\u0020]/.test(raw[index])) index += 1;
    }

    function scanStringToken() {
      const start = index;
      index += 1; // opening quote
      while (index < raw.length) {
        const character = raw[index];
        if (character === "\\") {
          index += 2;
        } else if (character === '"') {
          index += 1;
          return raw.slice(start, index);
        } else {
          index += 1;
        }
      }
      // JSON.parse already validated the input; keep this guard for clarity.
      throw new SyntaxError("Cadena JSON sin cerrar.");
    }

    function scanValue() {
      skipWhitespace();
      const character = raw[index];
      if (character === '"') {
        scanStringToken();
        return;
      }
      if (character === "{") {
        scanObject();
        return;
      }
      if (character === "[") {
        scanArray();
        return;
      }
      while (index < raw.length && !/[\u0009\u000a\u000d\u0020,\]}]/.test(raw[index])) index += 1;
    }

    function scanObject() {
      index += 1; // opening brace
      skipWhitespace();
      if (raw[index] === "}") {
        index += 1;
        return;
      }
      const keys = new Set();
      while (index < raw.length) {
        skipWhitespace();
        const keyToken = scanStringToken();
        const key = JSON.parse(keyToken);
        if (keys.has(key)) {
          throw new SyntaxError(`Clave JSON duplicada: ${JSON.stringify(key)}.`);
        }
        keys.add(key);
        skipWhitespace();
        index += 1; // colon
        scanValue();
        skipWhitespace();
        if (raw[index] === "}") {
          index += 1;
          return;
        }
        index += 1; // comma
      }
      throw new SyntaxError("Objeto JSON sin cerrar.");
    }

    function scanArray() {
      index += 1; // opening bracket
      skipWhitespace();
      if (raw[index] === "]") {
        index += 1;
        return;
      }
      while (index < raw.length) {
        scanValue();
        skipWhitespace();
        if (raw[index] === "]") {
          index += 1;
          return;
        }
        index += 1; // comma
      }
      throw new SyntaxError("Lista JSON sin cerrar.");
    }

    scanValue();
    return parsed;
  }

  function validateReview(review, originalHasErrors) {
    const errors = [];
    if (!isObject(review)) return ["La revisión debe ser un objeto."];

    collectNonFinite(review, "revisión", errors, new Set());
    compareExactKeys(review, FIELDS, "Revisión", errors);

    if (review.schema_version !== SCHEMA_VERSION) {
      errors.push(`schema_version debe ser ${JSON.stringify(SCHEMA_VERSION)}.`);
    }

    if (typeof review.reviewer_id !== "string" || !review.reviewer_id.trim()) {
      errors.push("reviewer_id debe identificar a una persona y no puede estar vacío.");
    }
    if (typeof review.review_date !== "string" || !isISODate(review.review_date)) {
      errors.push("review_date debe ser una fecha válida en formato YYYY-MM-DD.");
    }
    const responseAssessable = review.response_assessable;
    if (typeof responseAssessable !== "boolean") {
      errors.push("response_assessable debe ser una decisión explícita (true o false).");
    }
    if (typeof review.rationale !== "string" || !review.rationale.trim()) {
      errors.push("rationale debe incluir una justificación no vacía.");
    }

    CRITERIA.forEach((criterion) => {
      if (hasOwn(review, criterion) && !isRating(review[criterion])) {
        errors.push(`${criterion} debe ser 0, 1, 2 o "NA"; los booleanos no son notas.`);
      }
    });

    if (originalHasErrors !== null && typeof originalHasErrors !== "boolean") {
      errors.push("original_has_errors debe ser true, false o null.");
    }
    if (originalHasErrors === null && responseAssessable !== false) {
      errors.push("Debe indicar si el texto original tiene errores cuando la respuesta es evaluable.");
    }
    const conditionKnown = typeof originalHasErrors === "boolean";

    if (responseAssessable === false) {
      CRITERIA.forEach((criterion) => {
        if (hasOwn(review, criterion) && review[criterion] !== "NA") {
          errors.push(`${criterion} debe ser "NA" cuando la respuesta no es evaluable.`);
        }
      });
      ["meaning_preserved", "explanations_ok"].forEach((field) => {
        if (hasOwn(review, field) && review[field] !== "NA") {
          errors.push(`${field} debe ser "NA" cuando la respuesta no es evaluable.`);
        }
      });
    } else if (responseAssessable === true && conditionKnown && originalHasErrors === false) {
      ["detection", "correction"].forEach((criterion) => {
        if (hasOwn(review, criterion) && review[criterion] !== "NA") {
          errors.push(`${criterion} debe ser "NA" para un texto original correcto.`);
        }
      });
      if (hasOwn(review, "clean_text_handling") && ![0, 1, 2].includes(review.clean_text_handling)) {
        errors.push("clean_text_handling debe ser 0, 1 o 2 para un control evaluable.");
      }
      ["meaning_preservation", "level_appropriateness", "pedagogical_clarity"].forEach((criterion) => {
        if (hasOwn(review, criterion) && ![0, 1, 2].includes(review[criterion])) {
          errors.push(`${criterion} debe ser 0, 1 o 2 para un control evaluable.`);
        }
      });
      if (hasOwn(review, "grammatical_explanation")) {
        if (review.explanations_ok === "NA" && review.grammatical_explanation !== "NA") {
          errors.push("grammatical_explanation debe ser \"NA\" si explanations_ok es \"NA\" en un control.");
        }
        if (typeof review.explanations_ok === "boolean" && ![0, 1, 2].includes(review.grammatical_explanation)) {
          errors.push("grammatical_explanation debe ser 0, 1 o 2 cuando el control incluye una explicación.");
        }
      }
    } else if (responseAssessable === true && conditionKnown && originalHasErrors === true) {
      ["detection", "correction"].forEach((criterion) => {
        if (hasOwn(review, criterion) && ![0, 1, 2].includes(review[criterion])) {
          errors.push(`${criterion} debe ser 0, 1 o 2 para un texto original con errores.`);
        }
      });
      if (hasOwn(review, "clean_text_handling") && review.clean_text_handling !== "NA") {
        errors.push("clean_text_handling debe ser \"NA\" para un texto original con errores.");
      }
      ["meaning_preservation", "level_appropriateness", "grammatical_explanation", "pedagogical_clarity"].forEach((criterion) => {
        if (hasOwn(review, criterion) && ![0, 1, 2].includes(review[criterion])) {
          errors.push(`${criterion} debe ser 0, 1 o 2 para un texto original con errores.`);
        }
      });
    }

    ["meaning_preserved", "explanations_ok"].forEach((field) => {
      const value = review[field];
      if (typeof value !== "boolean" && value !== "NA") {
        errors.push(`${field} debe ser un booleano o "NA".`);
      }
    });

    if (conditionKnown && originalHasErrors === true && responseAssessable === true) {
      ["meaning_preserved", "explanations_ok"].forEach((field) => {
        if (typeof review[field] !== "boolean") {
          errors.push(`${field} debe ser un booleano explícito cuando hay errores y la respuesta es evaluable.`);
        }
      });
    } else if (conditionKnown && originalHasErrors === false && responseAssessable === true) {
      if (typeof review.meaning_preserved !== "boolean") {
        errors.push("meaning_preserved debe ser un booleano explícito para un control evaluable.");
      }
      if (typeof review.explanations_ok !== "boolean" && review.explanations_ok !== "NA") {
        errors.push("explanations_ok debe ser un booleano o \"NA\" para un control evaluable.");
      }
    }

    if (responseAssessable === true) {
      if (review.explanations_ok === false && review.grammatical_explanation !== 0) {
        errors.push("explanations_ok=false requiere grammatical_explanation=0.");
      }
      if (review.explanations_ok === true && ![1, 2].includes(review.grammatical_explanation)) {
        errors.push("explanations_ok=true requiere grammatical_explanation=1 o 2.");
      }
      if (review.explanations_ok === "NA" && originalHasErrors === false && review.grammatical_explanation !== "NA") {
        errors.push("explanations_ok=\"NA\" en un control requiere grammatical_explanation=\"NA\".");
      }
    }

    if (typeof review.verdict !== "string" || !VERDICTS.has(review.verdict)) {
      errors.push("verdict debe ser CORRECT, PARTIAL, INCORRECT o INVALID_CASE.");
    }
    if (review.verdict === "CORRECT") {
      if (review.meaning_preserved === false) {
        errors.push("verdict CORRECT contradice meaning_preserved=false.");
      }
      if (review.explanations_ok === false) {
        errors.push("verdict CORRECT contradice explanations_ok=false.");
      }
      const applicableScores = CRITERIA
        .map((criterion) => review[criterion])
        .filter((score) => score !== "NA");
      if (applicableScores.some((score) => typeof score === "number" && Number.isInteger(score) && score === 0)) {
        errors.push("verdict CORRECT contradice una nota 0 en un criterio aplicable.");
      }
      if (applicableScores.length === 0) {
        errors.push("verdict CORRECT no se puede asignar cuando todos los criterios son NA.");
      }
    }
    if (review.verdict === "CORRECT" && responseAssessable === false) {
      errors.push("Una respuesta no evaluable no puede recibir verdict CORRECT.");
    }
    if (responseAssessable === false && !["INCORRECT", "INVALID_CASE"].includes(review.verdict)) {
      errors.push("Una respuesta no evaluable requiere verdict INCORRECT o INVALID_CASE.");
    }

    return errors;
  }

  function serializeCompletedReviews(entries) {
    if (!Array.isArray(entries)) {
      throw new TypeError("entries debe ser una lista.");
    }
    const errors = [];
    const seen = new Set();
    const records = [];

    entries.forEach((entry, index) => {
      const label = `Entrada ${index + 1}`;
      if (!isObject(entry)) {
        errors.push(`${label}: debe ser un objeto.`);
        return;
      }
      compareExactKeys(entry, ENTRY_FIELDS, label, errors);
      if (typeof entry.blind_output_id !== "string" || !entry.blind_output_id.trim()) {
        errors.push(`${label}: blind_output_id debe ser un texto no vacío.`);
      } else if (seen.has(entry.blind_output_id)) {
        errors.push(`${label}: blind_output_id duplicado: ${entry.blind_output_id}.`);
      } else {
        seen.add(entry.blind_output_id);
      }
      if (typeof entry.completed !== "boolean") {
        errors.push(`${label}: completed debe ser true o false.`);
        return;
      }
      if (entry.original_has_errors !== null && typeof entry.original_has_errors !== "boolean") {
        errors.push(`${label}: original_has_errors debe ser true, false o null.`);
      }
      if (!entry.completed) return;

      const reviewErrors = validateReview(entry.review, entry.original_has_errors);
      if (reviewErrors.length) {
        errors.push(`${label} (${entry.blind_output_id || "sin ID"}): ${reviewErrors.join(" ")}`);
        return;
      }
      const record = { blind_output_id: entry.blind_output_id };
      FIELDS.forEach((field) => {
        record[field] = entry.review[field];
      });
      records.push(record);
    });

    if (errors.length) throw new Error(errors.join("\n"));
    const text = records.map((record) => JSON.stringify(record)).join("\n");
    return { text: text ? `${text}\n` : "", records };
  }

  function validateDraftReview(review, label, errors) {
    if (!isObject(review)) {
      errors.push(`${label}: review debe ser un objeto.`);
      return;
    }
    collectNonFinite(review, `${label}.review`, errors, new Set());
    compareExactKeys(review, FIELDS, `${label}.review`, errors);
    if (review.schema_version !== SCHEMA_VERSION) {
      errors.push(`${label}.review: schema_version debe ser ${JSON.stringify(SCHEMA_VERSION)}.`);
    }
    ["reviewer_id", "review_date", "rationale"].forEach((field) => {
      if (review[field] !== null && typeof review[field] !== "string") {
        errors.push(`${label}.review: ${field} debe ser texto o null en un borrador.`);
      }
    });
    if (review.response_assessable !== null && typeof review.response_assessable !== "boolean") {
      errors.push(`${label}.review: response_assessable debe ser booleano o null en un borrador.`);
    }
    CRITERIA.forEach((criterion) => {
      if (review[criterion] !== null && !isRating(review[criterion])) {
        errors.push(`${label}.review: ${criterion} debe ser 0, 1, 2, "NA" o null en un borrador.`);
      }
    });
    ["meaning_preserved", "explanations_ok"].forEach((field) => {
      const value = review[field];
      if (value !== null && typeof value !== "boolean" && value !== "NA") {
        errors.push(`${label}.review: ${field} debe ser booleano, "NA" o null en un borrador.`);
      }
    });
    if (review.verdict !== null && (typeof review.verdict !== "string" || !VERDICTS.has(review.verdict))) {
      errors.push(`${label}.review: verdict debe ser un veredicto permitido o null en un borrador.`);
    }
  }

  function validateBackup(data, packetSHA, validIDs) {
    const errors = [];
    if (!isObject(data)) return ["El respaldo debe ser un objeto."];
    collectNonFinite(data, "respaldo", errors, new Set());
    const expectedBackupFields = hasOwn(data, "current_id")
      ? BACKUP_FIELDS
      : BACKUP_FIELDS.filter((field) => field !== "current_id");
    compareExactKeys(data, expectedBackupFields, "Respaldo", errors);

    if (data.schema_version !== BACKUP_SCHEMA_VERSION) {
      errors.push(`schema_version del respaldo debe ser ${JSON.stringify(BACKUP_SCHEMA_VERSION)}.`);
    }
    if (typeof packetSHA !== "string" || !HEX_SHA256_RE.test(packetSHA)) {
      errors.push("El SHA-256 del paquete cargado debe tener 64 caracteres hexadecimales minúsculos.");
    }
    if (typeof data.packet_sha256 !== "string" || !HEX_SHA256_RE.test(data.packet_sha256)) {
      errors.push("packet_sha256 debe tener 64 caracteres hexadecimales minúsculos.");
    } else if (typeof packetSHA === "string" && data.packet_sha256 !== packetSHA) {
      errors.push("packet_sha256 no coincide con el paquete ciego cargado.");
    }

    if (!isObject(data.profile)) {
      errors.push("profile debe contener reviewer_id y review_date.");
    } else {
      compareExactKeys(data.profile, PROFILE_FIELDS, "profile", errors);
      PROFILE_FIELDS.forEach((field) => {
        const value = data.profile[field];
        if (value !== null && typeof value !== "string") {
          errors.push(`profile.${field} debe ser texto o null.`);
        }
      });
      if (typeof data.profile.review_date === "string" && data.profile.review_date !== "" && !isISODate(data.profile.review_date)) {
        errors.push("profile.review_date debe estar vacío o usar una fecha válida YYYY-MM-DD.");
      }
    }

    let idSet = null;
    if (Array.isArray(validIDs) || validIDs instanceof Set) {
      const values = [...validIDs];
      if (values.some((id) => typeof id !== "string" || !id.trim())) {
        errors.push("La lista de IDs válidos contiene un ID vacío o no textual.");
      }
      idSet = new Set(values);
    } else {
      errors.push("validIDs debe ser una lista o un conjunto de IDs ciegos.");
    }

    if (hasOwn(data, "current_id") && data.current_id !== null) {
      if (typeof data.current_id !== "string" || !data.current_id.trim()) {
        errors.push("current_id debe ser un ID ciego válido o null.");
      } else if (idSet && !idSet.has(data.current_id)) {
        errors.push("current_id no pertenece al paquete ciego cargado.");
      }
    }

    if (!Array.isArray(data.entries)) {
      errors.push("entries debe ser una lista.");
      return errors;
    }
    const seen = new Set();
    data.entries.forEach((entry, index) => {
      const label = `entries[${index}]`;
      if (!isObject(entry)) {
        errors.push(`${label} debe ser un objeto.`);
        return;
      }
      compareExactKeys(entry, ENTRY_FIELDS, label, errors);
      const id = entry.blind_output_id;
      if (typeof id !== "string" || !id.trim()) {
        errors.push(`${label}.blind_output_id debe ser texto no vacío.`);
      } else {
        if (seen.has(id)) errors.push(`${label}: blind_output_id duplicado: ${id}.`);
        seen.add(id);
        if (idSet && !idSet.has(id)) errors.push(`${label}: blind_output_id desconocido para el paquete cargado.`);
      }
      if (typeof entry.completed !== "boolean") {
        errors.push(`${label}.completed debe ser true o false.`);
      }
      if (entry.original_has_errors !== null && typeof entry.original_has_errors !== "boolean") {
        errors.push(`${label}.original_has_errors debe ser true, false o null.`);
      }
      if (entry.completed === true) {
        const reviewErrors = validateReview(entry.review, entry.original_has_errors);
        reviewErrors.forEach((problem) => errors.push(`${label}: ${problem}`));
      } else if (entry.completed === false) {
        validateDraftReview(entry.review, label, errors);
      }
    });

    return errors;
  }

  return Object.freeze({
    CRITERIA,
    FIELDS,
    parseJSONStrict,
    blankReview,
    validateReview,
    serializeCompletedReviews,
    validateBackup,
  });
});
