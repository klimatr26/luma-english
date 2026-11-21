"""Rebuild only the final app's extra pins; never rewrite the frozen shared catalog."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REVISION = "f6d5376be1edb4d416d56da11e5397a961aca8ae"
PINS = [
    ("Q4_K_M", 1280835840, "aaf42c8b7c3cab2bf3d69c355048d4a0ee9973d48f16c731c0520ee914699223"),
    ("Q8_0", 2012012800, "1b04acba824817554f4ce23639bc8495ff70453b8fcb047900c731521021f2c1"),
    ("UD-Q4_K_XL", 1339752704, "0af96165ea615bea39a04118d63f0b6d35908aea850ee4a51aa6151d851b8b35"),
]


def main():
    source = ROOT.parent / "cross_demo/WritingApp.Shared/Assets/catalog.json"
    base = json.loads(source.read_text(encoding="utf-8"))
    template = next(m for m in base if m["Family"] == "qwen" and m["Quantization"] == "Q4_K_M")
    models = []
    for quant, size, sha in PINS:
        model = dict(template)
        filename = f"Qwen3.5-2B-{quant}.gguf"
        model.update(Id="portable-unsloth-qwen35-2b-" + quant.lower().replace("_", "-"),
                     Name="Qwen 3.5 · 2B (Unsloth descarga)", Quantization=quant,
                     RelativePath="portable_unsloth_qwen35_2b/" + filename, SizeBytes=size, Sha256=sha,
                     DownloadUrl=f"https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/resolve/{REVISION}/{filename}?download=true",
                     SourceUrl=f"https://huggingface.co/unsloth/Qwen3.5-2B-GGUF/tree/{REVISION}")
        models.append(model)
    target = ROOT / "Course.Core/Assets/extra-models.json"
    target.write_text(json.dumps(models, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Prepared three additional final-app entries; frozen shared catalog untouched.")


if __name__ == "__main__":
    main()
