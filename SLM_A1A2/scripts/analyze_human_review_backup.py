"""Summarize investigator ratings without regrading or importing human claims.

Frozen prompts, gold, responses and automatic scores are read-only. Contract
conflicts and INVALID_CASE proposals remain pending explicit adjudication.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from statistics import mean

import human_review_v2 as human
import prepare_human_review_v2 as prep

LAB = Path(__file__).resolve().parents[1]
REPO = LAB.parent
PACKET = LAB / "analysis_v2/human_review_development60/reviewer_materials/blind_packet.json"
CROSSWALK = LAB / "analysis_v2/human_review_development60/coordinator_only/identity_crosswalk.json"
NAMES = {
    "11-qwen35-4b-q4-k-m": "Qwen3.5-4B Q4_K_M",
    "13-gemma4-e2b-ud-q4-k-xl": "Gemma E2B UD-Q4_K_XL",
    "06-minicpm5-2b-q4-k-m": "MiniCPM5-2B Q4_K_M",
}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def case_score(review):
    """Equal weight per reviewed output, excluding NA rather than making it zero."""
    scores = [review[key] for key in human.CRITERIA if type(review[key]) is int]
    return mean(scores) if scores else None


def aggregate(rows):
    scores = [case_score(row["review"]) for row in rows]
    numeric = [score for score in scores if score is not None]
    criteria = {}
    for key in human.CRITERIA:
        values = [row["review"][key] for row in rows if type(row["review"][key]) is int]
        criteria[key] = {"n": len(values), "sum": sum(values), "mean": mean(values) if values else None,
                         "zero_count": values.count(0), "na_count": sum(row["review"][key] == "NA" for row in rows)}
    result = {"outputs": len(rows), "scored_outputs": len(numeric), "unscored_outputs": len(rows)-len(numeric),
              "mean_per_output_0_2": mean(numeric) if numeric else None,
              "normalized_rubric_points_0_100": 50*mean(numeric) if numeric else None,
              "verdict_counts": dict(Counter(row["review"]["verdict"] for row in rows)), "criteria": criteria}
    result["by_condition"] = {}
    for condition in ("correct", "incorrect"):
        selected = [row for row in rows if row["condition"] == condition]
        nums = [score for row in selected if (score := case_score(row["review"])) is not None]
        result["by_condition"][condition] = {"outputs": len(selected), "scored_outputs": len(nums), "mean_0_2": mean(nums) if nums else None}
    result["by_level"] = {level: {"outputs": sum(r["level"] == level for r in rows)} for level in ("A1", "A2")}
    return result


def analyze(backup_path):
    backup_path = Path(backup_path)
    backup = human._strict_json_loads(backup_path.read_text(encoding="utf-8"))
    if (not isinstance(backup, dict) or backup.get("schema_version") != "human_review_web.backup/1.0"
            or backup.get("packet_sha256") != sha(PACKET)):
        raise ValueError("Backup schema or packet binding mismatch")
    expected_top = {"schema_version", "packet_sha256", "profile", "entries", "current_id"}
    if set(backup) != expected_top or not isinstance(backup["entries"], list):
        raise ValueError("Unexpected backup fields")
    crosswalk = prep.load_verified_crosswalk(CROSSWALK)
    identities = {entry["blind_output_id"]: entry for entry in crosswalk["items"]}
    packet = human._strict_json_loads(PACKET.read_text(encoding="utf-8"))
    visible = {entry["blind_output_id"]: entry for entry in packet["items"]}
    _, bound_rows = prep.load_bound_rows("results_120")
    bound = {(row["config_id"], row["case_id"]): row for row in bound_rows}
    rows = []
    seen = set()
    for entry in backup["entries"]:
        if not isinstance(entry, dict) or set(entry) != {"blind_output_id", "review", "original_has_errors", "completed"}:
            raise ValueError("Unexpected entry fields")
        bid = entry["blind_output_id"]
        if bid in seen or bid not in identities:
            raise ValueError("Duplicate/unknown blind ID")
        seen.add(bid)
        if entry["completed"] is not True:
            raise ValueError("This intake requires explicitly completed records")
        if entry["original_has_errors"] is not None and type(entry["original_has_errors"]) is not bool:
            raise ValueError("Invalid auxiliary original_has_errors type")
        identity = identities[bid]
        source = bound[identity["config_id"], identity["case_id"]]
        if source["response_sha256"] != hashlib.sha256(visible[bid]["response_text"].encode("utf-8")).hexdigest():
            raise ValueError("Response hash mismatch")
        review = entry["review"]
        if not isinstance(review, dict) or set(review) != {"schema_version", *human.REVIEW_FIELDS}:
            raise ValueError("Review does not have the exact public review fields")
        if any(not human._is_rating(review[key]) for key in human.CRITERIA):
            raise ValueError("Ratings must be integers 0/1/2 or NA; booleans are not ratings")
        expected = {field: identity[field] for field in human.IDENTITY_FIELDS}
        errors = human.validate_human_record({**review, **expected}, expected, source["condition"])
        # Do not allow private identity overrides or missing/extra review fields.
        mismatch = (type(entry["original_has_errors"]) is bool
                    and entry["original_has_errors"] != (source["condition"] == "incorrect"))
        rows.append({"blind_output_id": bid, "config_id": identity["config_id"], "case_id": identity["case_id"],
                     "level": source["level"], "condition": source["condition"], "review": review,
                     "original_has_errors": entry["original_has_errors"], "contract_errors": errors,
                     "auxiliary_condition_disagreement": mismatch, "response_sha256": source["response_sha256"]})
    if seen != set(identities):
        raise ValueError("Expected the full fixed packet; IDs are missing")
    pending_cases = sorted({row["case_id"] for row in rows if row["contract_errors"]
                            or row["auxiliary_condition_disagreement"] or row["review"]["verdict"] == "INVALID_CASE"})
    grouped = defaultdict(list)
    for row in rows:
        grouped[row["config_id"]].append(row)
    summaries = {}
    for config, group in sorted(grouped.items()):
        summaries[config] = {
            "as_entered": aggregate(group),
            "contract_compatible": aggregate([r for r in group if not r["contract_errors"] and not r["auxiliary_condition_disagreement"]]),
            "paired_pending_cases_omitted": aggregate([r for r in group if r["case_id"] not in pending_cases]),
            "contract_conflicts": sum(bool(r["contract_errors"]) for r in group)}
    return {"schema_version": "human_review_intake/1.0", "status": "PROVISIONAL_AWAITING_INVESTIGATOR_CLARIFICATIONS",
            "source_backup": str(backup_path.resolve()), "source_backup_sha256": sha(backup_path),
            "packet_sha256": sha(PACKET), "crosswalk_sha256": sha(CROSSWALK),
            "scope": "results_120", "records": len(rows), "reviewers": dict(Counter(r["review"]["reviewer_id"] for r in rows)),
            "declared_review_dates": dict(Counter(r["review"]["review_date"] for r in rows)),
            "contract_conflicts": sum(bool(r["contract_errors"]) for r in rows),
            "invalid_case_proposals": [r["blind_output_id"] for r in rows if r["review"]["verdict"] == "INVALID_CASE"],
            "pending_common_case_ids": pending_cases, "summaries": summaries, "bound_reviews": rows,
            "original_ratings_modified": False, "original_gold_modified": False, "human_layer_imported": False,
            "new_inferences": 0, "final_test_access": False}


def format_num(value):
    return "NA" if value is None else f"{value:.4f}"


def markdown(result):
    lines = ["# Revisión del investigador — ingreso del 9 de noviembre de 2026", "",
             "**Estado: provisional; pendientes aclaraciones del investigador.** No se han corregido notas ni importado una capa humana definitiva.", "",
             f"Se recibieron {result['records']} fichas: 60 mismos casos × tres configuraciones. Revisor declarado: `kevin-01`. Las fichas declaran fecha `2026-10-19`; la recepción es del 9 de noviembre. La fecha del archivo es de exportación y no demuestra cuándo se realizó cada juicio.", "",
             f"SHA-256 del respaldo original: `{result['source_backup_sha256']}`. El paquete, crosswalk, respuestas y filas v2 quedaron vinculados y verificados. Hay {result['contract_conflicts']} conflictos del contrato humano y {len(result['invalid_case_proposals'])} propuestas INVALID_CASE.", "",
             "## Puntuaciones tal como fueron introducidas", "",
             "La puntuación de cada ficha es la media de sus criterios numéricos 0–2; NA no equivale a cero. La media del modelo da igual peso a cada ficha con alguna nota aplicable. El equivalente /100 es esa media ×50: son puntos de rúbrica, **no porcentaje de precisión**. Se publica aparte la cobertura. Esta tabla conserva incluso las notas cuya aplicabilidad está pendiente; no es el cierre validado.", "",
             "| Configuración | Media 0–2 | Puntos /100 | Fichas con nota /60 | CORRECT | PARTIAL | INCORRECT | INVALID_CASE |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for cid in NAMES:
        summary = result["summaries"][cid]["as_entered"]
        counts = summary["verdict_counts"]
        lines.append(f"| {NAMES[cid]} | {format_num(summary['mean_per_output_0_2'])} | {format_num(summary['normalized_rubric_points_0_100'])} | {summary['scored_outputs']}/60 | " + " | ".join(str(counts.get(k, 0)) for k in ("CORRECT", "PARTIAL", "INCORRECT", "INVALID_CASE")) + " |")
    lines += ["", "MiniCPM tiene una ficha marcada no evaluable, con todas las notas NA: se conserva su veredicto, pero no se inventa una puntuación. Las medias son condicionales a las fichas con nota; no ocultan esa falta de cobertura.", "",
              "## Comparación provisional en casos comunes sin pendientes", "",
              "Se omiten analíticamente de los tres modelos los mismos casos con conflictos de aplicabilidad o propuestas de invalidación no resueltas. Esto **no invalida** el benchmark ni modifica sus puntuaciones históricas; evita comparar modelos en casos diferentes mientras se aclaran las fichas.", "",
              "Casos apartados temporalmente: " + ", ".join(f"`{case}`" for case in result["pending_common_case_ids"]) + ".", "",
              "| Configuración | Fichas comparadas | Fichas con nota | Media 0–2 | Puntos /100 | CORRECT / comparadas |", "|---|---:|---:|---:|---:|---:|"]
    for cid in NAMES:
        summary = result["summaries"][cid]["paired_pending_cases_omitted"]
        lines.append(f"| {NAMES[cid]} | {summary['outputs']} | {summary['scored_outputs']} | {format_num(summary['mean_per_output_0_2'])} | {format_num(summary['normalized_rubric_points_0_100'])} | {summary['verdict_counts'].get('CORRECT', 0)}/{summary['outputs']} |")
    lines += ["", "## Criterios en la comparación común", "", "Cada celda indica media 0–2 y número de notas numéricas (n). No se equiparan los denominadores ni se transforma NA en éxito.", "",
              "| Criterio | Qwen4B Q4 | Gemma UD-Q4 | MiniCPM Q4 |", "|---|---:|---:|---:|"]
    for key in human.CRITERIA:
        cells = []
        for cid in NAMES:
            criterion = result["summaries"][cid]["paired_pending_cases_omitted"]["criteria"][key]
            cells.append(f"{format_num(criterion['mean'])} (n={criterion['n']})")
        lines.append(f"| `{key}` | " + " | ".join(cells) + " |")
    lines += ["", "## Aclaraciones que impiden el cierre", "",
              "Las fichas completas para revisar se encuentran en [casos pendientes](human_review_cases_pending_20261109.md). La siguiente lista conserva el veredicto y enumera errores de contrato; no decide lingüísticamente el caso ni reemplaza la revisión humana.", ""]
    for row in result["bound_reviews"]:
        if row["contract_errors"] or row["review"]["verdict"] == "INVALID_CASE":
            lines += [f"- `{row['config_id']}` / `{row['case_id']}` / `{row['blind_output_id']}` — `{row['review']['verdict']}`. " + ("; ".join(row["contract_errors"]) if row["contract_errors"] else "Propuesta de caso inválido pendiente de adjudicación.")]
    lines += ["", "## Interpretación y límites", "",
              "Qwen encabeza ambas medias descriptivas, seguido de Gemma y MiniCPM. No se afirma significación estadística, superioridad de toda la familia ni generalización a otras cuantizaciones: se revisaron solo estas tres configuraciones Q4, por un investigador y sobre una muestra enriquecida en controles (30 correctos/30 incorrectos), frente a 30/90 en el desarrollo completo. No se combinan estos números con los F0.5 automáticos ni se multiplican muestras por el número de modelos.", "",
              "Las observaciones de formato (Markdown, claves adicionales, JSON roto) se conservan aparte de las siete notas humanas: la rúbrica no incluye un criterio numérico de formato. Una ficha CORRECT con JSON recuperable no se convierte automáticamente en JSON estricto.", "",
              "El investigador ha pedido admitir recomendaciones opcionales de escritura aun cuando no existan errores. Esa política se implementa prospectivamente en el perfil `human-review-20261109`, sin reescribir los resultados del prompt anterior. Una recomendación de estilo no debe activar is_correct=false ni incorporarse a errors. El consejo también debe ser lingüísticamente válido. Los veredictos INVALID_CASE existentes siguen siendo propuestas hasta aclarar si se refieren al caso o al comportamiento del modelo.", "",
              "El prompt base, gold, RAW, resultados automáticos y archivo aportado permanecen intactos. No se han ejecutado inferencias nuevas ni se ha accedido al test final. Para el registro técnico y la propuesta de prompts véase [seguimiento de revisión y prompts](human_review_prompt_followup_20261109.md).", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backup", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=LAB / "analysis_v2/human_review_20261109")
    parser.add_argument("--report", type=Path, default=LAB / "documentation/human_review_results_20261109.md")
    args = parser.parse_args()
    result = analyze(args.backup)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "intake_and_scores.json").write_text(json.dumps(result, ensure_ascii=False, allow_nan=False, indent=2)+"\n", encoding="utf-8")
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(markdown(result), encoding="utf-8")
    print(json.dumps({"status": result["status"], "records": result["records"], "contract_conflicts": result["contract_conflicts"], "pending_common_cases": len(result["pending_common_case_ids"])}))


if __name__ == "__main__":
    main()
