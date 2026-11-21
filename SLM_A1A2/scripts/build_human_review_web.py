"""Build a portable, offline page from public blinded review materials only."""
import argparse
import hashlib
import json
from pathlib import Path
from human_review_v2 import HUMAN_REVIEW_SCHEMA_VERSION, REVIEW_FIELDS

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "analysis_v2/human_review_development60/reviewer_materials"
WEB = ROOT / "review_web"


def sha(data):
    return hashlib.sha256(data).hexdigest()


def script_json(value):
    return json.dumps(value, ensure_ascii=False).replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")


def build(packet_path=PUBLIC / "blind_packet.json", plan_path=PUBLIC / "second_reviewer_plan.json", output=WEB / "revision_humana.html"):
    packet_bytes = Path(packet_path).read_bytes()
    packet_source = packet_bytes.decode("utf-8")
    packet = json.loads(packet_source)
    allowed = {"blind_output_id", "level", "task", "student_text", "response_text", "review_template"}
    if packet.get("schema_version") != "human_review_v2.review_packet/1.0" or not packet.get("items"):
        raise ValueError("Invalid public packet")
    ids = [item["blind_output_id"] for item in packet["items"]]
    if len(set(ids)) != len(ids) or any(set(item) != allowed for item in packet["items"]):
        raise ValueError("Packet includes duplicate IDs or non-public fields")
    for item in packet["items"]:
        template = item["review_template"]
        if (set(template) != {"schema_version", *REVIEW_FIELDS}
                or template["schema_version"] != HUMAN_REVIEW_SCHEMA_VERSION
                or any(template[field] is not None for field in REVIEW_FIELDS)):
            raise ValueError("Review templates must contain blank judgments only")
    plan = json.loads(Path(plan_path).read_text(encoding="utf-8"))
    secondary = plan["blind_output_ids"]
    if len(set(secondary)) != len(secondary) or not set(secondary).issubset(ids):
        raise ValueError("Invalid public second-reviewer subset")
    sources = {name: (WEB / "src" / name).read_bytes() for name in ("page.html", "style.css", "review_core.js", "app.js")}
    html = sources["page.html"].decode("utf-8")
    html = html.replace("/* INLINE_STYLE */", sources["style.css"].decode("utf-8"))
    html = html.replace("/* INLINE_CORE */", sources["review_core.js"].decode("utf-8"))
    html = html.replace("/* INLINE_APP */", sources["app.js"].decode("utf-8"))
    html = html.replace("__PUBLIC_DATA__", script_json({"packet_source": packet_source, "packet_sha256": sha(packet_bytes), "second_ids": secondary}))
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    content = html.encode("utf-8")
    output.write_bytes(content)
    record = {"schema_version": "human_review_web.build/1.0", "packet_sha256": sha(packet_bytes), "item_count": len(ids), "second_review_count": len(secondary), "sources_sha256": {name: sha(data) for name, data in sources.items()}, "output_sha256": sha(content), "output_bytes": len(content)}
    output.with_suffix(".build.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return record


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--packet", type=Path, default=PUBLIC / "blind_packet.json")
    parser.add_argument("--second-plan", type=Path, default=PUBLIC / "second_reviewer_plan.json")
    parser.add_argument("--output", type=Path, default=WEB / "revision_humana.html")
    args = parser.parse_args()
    print(json.dumps(build(args.packet, args.second_plan, args.output), indent=2))
