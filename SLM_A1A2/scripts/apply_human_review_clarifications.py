"""Apply investigator-confirmed amendments to a copy, validate and import it.

The original backup, original comments/dates, gold and automatic scores remain
unchanged. Each amendment requires an exact old value and a bound source hash.
"""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import analyze_human_review_backup as analysis
import human_review_v2 as human
import prepare_human_review_v2 as prep
import validate_human_review_web_export as web_export

ALLOWED_FIELDS = {"original_has_errors", "review.detection", "review.correction", "review.clean_text_handling",
                  "review.grammatical_explanation", "review.explanations_ok", "review.verdict"}


def apply_changes(backup, ledger, source_sha256):
    if (ledger.get("schema_version") != "human_review_clarifications/1.0"
            or ledger.get("status") != "USER_CONFIRMED"
            or ledger.get("source_backup_sha256") != source_sha256
            or not ledger.get("confirmation", {}).get("user_reply_verbatim")):
        raise ValueError("Amendments require user confirmation and the exact source hash")
    amended = copy.deepcopy(backup)
    identities = [entry["blind_output_id"] for entry in amended["entries"]]
    if len(identities) != len(set(identities)):
        raise ValueError("Duplicate source IDs")
    by_id = {entry["blind_output_id"]: entry for entry in amended["entries"]}
    seen = set()
    for change in ledger["changes"]:
        bid = change["blind_output_id"]
        if bid in seen or bid not in by_id:
            raise ValueError("Unknown or repeated amendment identity")
        seen.add(bid)
        entry = by_id[bid]
        if entry["review"]["reviewer_id"] != ledger["reviewer_id"] or entry["completed"] is not True:
            raise ValueError("Reviewer or completion mismatch")
        fields = set()
        for patch in change["patches"]:
            field = patch["field"]
            if field not in ALLOWED_FIELDS or field in fields:
                raise ValueError("Forbidden or repeated amendment field")
            fields.add(field)
            target, key = (entry["review"], field[7:]) if field.startswith("review.") else (entry, field)
            if type(target[key]) is not type(patch["before"]) or target[key] != patch["before"]:
                raise ValueError("Source value differs from the confirmed before-value")
            target[key] = copy.deepcopy(patch["after"])
    return amended


def layer_provenance(backup_path, ledger_path, ledger):
    return {"schema_version": "human_review_layer.clarification_provenance/1.0",
            "original_backup_sha256": analysis.sha(backup_path),
            "ledger_path": str(Path(ledger_path).resolve()), "ledger_sha256": analysis.sha(ledger_path),
            "clarification_date": ledger["clarification_date"], "reviewer_id": ledger["reviewer_id"],
            "clarified_blind_output_ids": [c["blind_output_id"] for c in ledger["changes"]],
            "original_comments_and_declared_review_dates_preserved": True,
            "read_original_comments_with_confirmed_clarifications": True}


def report(result, original, ledger, layer_name):
    lines = ["# Revisión humana aclarada — 9 de noviembre de 2026", "",
             "**Estado: 180 fichas validadas e importadas, con ocho aclaraciones confirmadas por el investigador.** Este cierre corresponde a la revisión de desarrollo, no al test final.", "",
             f"Revisor: `{ledger['reviewer_id']}`. El respaldo original conserva SHA-256 `{ledger['source_backup_sha256']}` y no se ha editado. Las fichas conservan fecha declarada `2026-10-19`; las aclaraciones tienen fecha `2026-11-09` en un registro separado. Sus comentarios originales también se conservan.", "",
             "## Puntuaciones después de las aclaraciones", "",
             "Para cada ficha se promedian sus criterios numéricos 0–2; NA se omite y no se transforma en cero. La media del modelo da igual peso a cada ficha con notas. Puntos /100 = media ×50: no es porcentaje de precisión ni F0.5.", "",
             "| Configuración | Media /2 | Puntos /100 | Fichas con nota /60 | CORRECT | PARTIAL | INCORRECT |", "|---|---:|---:|---:|---:|---:|---:|"]
    for cid, name in analysis.NAMES.items():
        summary = result["summaries"][cid]["as_entered"]
        counts = summary["verdict_counts"]
        lines.append(f"| {name} | {summary['mean_per_output_0_2']:.4f} | {summary['normalized_rubric_points_0_100']:.4f} | {summary['scored_outputs']}/60 | {counts.get('CORRECT', 0)} | {counts.get('PARTIAL', 0)} | {counts.get('INCORRECT', 0)} |")
    lines += ["", "MiniCPM mantiene una ficha marcada no evaluable, con todas las notas NA y veredicto INCORRECT. No se inventa una nota para ella: la media es condicional a 59 fichas con nota. Los tres modelos conservan los mismos 60 casos; no quedan propuestas INVALID_CASE ni se excluye ningún caso.", "",
              "## Notas por criterio", "", "Se muestra media /2 y denominador numérico n. Las diferencias de denominador reflejan NA y la ficha no evaluable, no resultados omitidos sin declarar.", "",
              "| Criterio | Qwen4B Q4 | Gemma UD-Q4 | MiniCPM Q4 |", "|---|---:|---:|---:|"]
    for criterion in human.CRITERIA:
        cells = []
        for cid in analysis.NAMES:
            score = result["summaries"][cid]["as_entered"]["criteria"][criterion]
            cells.append(f"{score['mean']:.4f} (n={score['n']})" if score["mean"] is not None else "NA")
        lines.append(f"| `{criterion}` | " + " | ".join(cells) + " |")
    lines += ["", "## Cambios confirmados", "",
              "Los ocho registros siguen siendo controles: detección/corrección se mantienen o pasan a NA y `original_has_errors=false`. Esto no cambia el gold. Las notas que no se enumeran a continuación permanecen intactas.", "",
              "| Ficha | Aclaración aplicada |", "|---|---|"]
    for change in ledger["changes"]:
        patches = "; ".join(f"`{p['field']}`: `{p['before']}` → `{p['after']}`" for p in change["patches"])
        lines.append(f"| {change['label']} | {patches}. {change['clarification']} |")
    lines += ["", "La propuesta numérica para las cuatro últimas fichas fue expuesta completa en el chat y el investigador respondió: «Sí, esas notas reflejan mi juicio». No se sustituyó ese consentimiento por un juicio de IA. Las cuatro primeras se aplicaron conforme a su aclaración explícita sobre originales correctos y notas 2/true.", "",
              "La convención del investigador acepta 2/true en explicación para controles con feedback vacío o sin explicación de un error real. Se conserva su decisión; no debe interpretarse como evidencia de que se produjo una explicación gramatical. NA tampoco se convierte en 2 en otras fichas.", "",
              "En Gemma A2-C013, CORRECT es el juicio humano sobre el contenido lingüístico. El objeto vacío en `errors` y la envoltura Markdown siguen siendo problemas técnicos: este juicio no vuelve estricto o coherente su JSON. En Qwen A2-C013 se conserva INCORRECT por la corrección propuesta y su desincronización. En A2-C008/C010, PARTIAL permite reconocer el posible valor del consejo sin aceptar que una preferencia estilística sea un error del original.", "",
              "## Comparación con el ingreso original", "",
              "| Configuración | Media original /2 | Media aclarada /2 |", "|---|---:|---:|"]
    for cid, name in analysis.NAMES.items():
        before = original["summaries"][cid]["as_entered"]["mean_per_output_0_2"]
        after = result["summaries"][cid]["as_entered"]["mean_per_output_0_2"]
        lines.append(f"| {name} | {before:.4f} | {after:.4f} |")
    lines += ["", "Las medias de las cuatro primeras fichas siguen siendo 2: cambió la aplicabilidad de criterios, no su juicio favorable. Las cifras antiguas y el subconjunto provisional de 53 casos se conservan en [el informe de ingreso](human_review_results_20261109.md), superado para este cierre por el presente documento.", "",
              "## Trazabilidad y límites", "",
              f"Capa importada: `analysis_v2/results_120/human_layers/{layer_name}/`. Respaldo derivado, JSONL, metadatos, registro de cambios e informe estructurado: `analysis_v2/human_review_20261109/clarified_v1/`. Ledger de confirmación: `analysis_v2/human_review_20261109/clarifications_v1.json`.", "",
              "Los cambios se aplican solo si coinciden el SHA del respaldo, el revisor, el ID y cada valor anterior. Después se valida el contrato completo, el crosswalk, los hashes de respuestas, el JSONL y sus metadatos. Los 172 registros no señalados permanecen exactamente iguales. La capa humana es independiente: no se actualizan las métricas automáticas ni sus flags históricos de confirmación.", "",
              "La muestra son 60 casos de desarrollo repetidos en tres configuraciones, enriquecida en controles, con un único revisor que es el investigador. No hay evidencia de acuerdo interevaluador, superioridad estadística ni precisión poblacional. Los puntajes no se extrapolan a otras cuantizaciones o a LFM. No se ejecutaron inferencias ni se accedió al test final.", "",
              "La política de sugerencias opcionales y los prompts nuevos permanecen documentados en [el seguimiento de prompts](human_review_prompt_followup_20261109.md). Esta aclaración de notas anteriores no demuestra que los prompts nuevos mejoren las respuestas.", ""]
    return "\n".join(lines)


def finalize(backup_path, ledger_path, output_dir, report_path, layer_name):
    backup_path, ledger_path, output_dir = map(Path, (backup_path, ledger_path, output_dir))
    if not layer_name or not all(c.isalnum() or c in "-_" for c in layer_name):
        raise ValueError("Invalid human layer name")
    if output_dir.exists() or Path(report_path).exists() or (prep.v2.OUTPUT / "results_120/human_layers" / layer_name).exists():
        raise ValueError("Refusing to overwrite an existing clarification delivery")
    backup = human._strict_json_loads(backup_path.read_text(encoding="utf-8"))
    ledger = human._strict_json_loads(ledger_path.read_text(encoding="utf-8"))
    amended = apply_changes(backup, ledger, analysis.sha(backup_path))
    records = [{"blind_output_id": entry["blind_output_id"], **entry["review"]} for entry in amended["entries"]]
    crosswalk = prep.load_verified_crosswalk(analysis.CROSSWALK)
    _, bound_rows = prep.load_bound_rows("results_120")
    prep.validate_records(records, bound_rows, crosswalk)
    if any(record["verdict"] == "INVALID_CASE" for record in records):
        raise ValueError("This closure still contains unresolved invalid-case proposals")
    output_dir.mkdir(parents=True)
    derived = output_dir / "clarified_backup.json"
    derived.write_text(json.dumps(amended, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    result = analysis.analyze(derived)
    if result["pending_common_case_ids"]:
        raise ValueError("Amended records still contain unresolved conflicts")
    original = analysis.analyze(backup_path)
    review_path = output_dir / "reviews.jsonl"
    content = "".join(json.dumps(record, ensure_ascii=False, allow_nan=False)+"\n" for record in records)
    review_path.write_bytes(content.encode("utf-8"))
    metadata = {"schema_version": "human_review_web.export/1.0", "packet_sha256": amended["packet_sha256"],
                "reviews_sha256": analysis.sha(review_path), "reviews_filename": review_path.name,
                "reviews_byte_count": len(review_path.read_bytes()), "record_count": len(records),
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "original_judgments": [{"blind_output_id": e["blind_output_id"], "original_has_errors": e["original_has_errors"]} for e in amended["entries"]]}
    metadata_path = output_dir / "reviews.metadata.json"
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    validation = web_export.validate_export(review_path, metadata_path, analysis.CROSSWALK)
    if validation["status"] != "VALID":
        raise ValueError("Export failed identity/condition validation")
    prep.import_reviews("results_120", review_path, layer_name, analysis.CROSSWALK)
    layer = prep.v2.OUTPUT / "results_120/human_layers" / layer_name
    (layer / "clarification_provenance.json").write_text(
        json.dumps(layer_provenance(backup_path, ledger_path, ledger), ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    result.update(status="COMPLETE_WITH_INVESTIGATOR_CLARIFICATIONS", human_layer_imported=True,
                  original_backup_sha256=analysis.sha(backup_path), clarification_ledger_sha256=analysis.sha(ledger_path),
                  derived_ratings_amended_by_user_confirmation=True, human_layer_name=layer_name)
    (output_dir / "scores.json").write_text(json.dumps(result, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    Path(report_path).write_text(report(result, original, ledger, layer_name), encoding="utf-8")
    receipt = {"status": result["status"], "clarified_records": len(ledger["changes"]), "review_records_imported": len(records),
               "original_backup_sha256": analysis.sha(backup_path), "ledger_sha256": analysis.sha(ledger_path),
               "derived_backup_sha256": analysis.sha(derived), "reviews_sha256": analysis.sha(review_path),
               "metadata_sha256": analysis.sha(metadata_path), "scores_sha256": analysis.sha(output_dir / "scores.json"),
               "report_sha256": analysis.sha(report_path), "human_layer": layer_name, "invalidations_applied": False,
               "old_gold_and_automatic_scores_modified": False, "new_inferences": 0, "final_test_access": False}
    (output_dir / "closure_record.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return receipt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--layer-name", required=True)
    args = parser.parse_args()
    print(json.dumps(finalize(args.backup, args.ledger, args.output_dir, args.report, args.layer_name)))
