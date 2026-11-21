"""Copy only model pins and prompt text into the app. Never embed benchmark cases."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "cross_demo/WritingApp.Shared/Assets"

def main():
    source = json.loads((ROOT / "demo/model_sources.json").read_text(encoding="utf-8"))
    manifest = json.loads((ROOT / "manifests/experiment_manifest_120.json").read_text(encoding="utf-8"))
    configurations = {c["config_id"]: c for c in manifest["configurations"]}
    names = {"minicpm": "MiniCPM 5 · 2B", "qwen": "Qwen 3.5 · 4B (GGUF local)",
             "gemma": "Gemma 4 · E2B", "lfm12": "LFM 2.5 · 1.2B", "lfm26": "LFM 2.5 · 2.6B"}
    models = []
    for s in source["models"]:
        c = configurations[s["config_id"]]
        assert s["sha256"] == c["model_sha256"] and s["size_bytes"] == c["gguf"]["bytes"]
        family = "qwen" if "qwen" in s["config_id"] else "minicpm" if "minicpm" in s["config_id"] else "gemma" if "gemma" in s["config_id"] else "lfm12" if "12b" in s["config_id"] else "lfm26"
        relative = "qwen_converted/" + c["model_path"].replace("\\", "/").split("/")[-1] if family == "qwen" else c["model_path"].removeprefix("models/")
        g = c["generation"]
        models.append(dict(Id=s["config_id"], Name=names[family], Family=family, Quantization=c["quant"],
            RelativePath=relative, SizeBytes=s["size_bytes"], Sha256=s["sha256"], DownloadUrl=s["download_url"],
            SourceUrl=s["source_page"], License=s["license"],
            Sampling=dict(Temperature=g["temperature"], TopP=g["top_p"], TopK=g["top_k"], MinP=g["min_p"],
                RepeatPenalty=g["repeat_penalty"], PresencePenalty=g["presence_penalty"], FrequencyPenalty=g["frequency_penalty"], MaxTokens=512),
            ThinkingToggle="enable_thinking" in (c.get("chat_template_kwargs") or {})))
    # Separate downloadable Qwen artifacts: never relabel these bytes as the local benchmark conversion.
    upstream_revision = "e87f176479d0855a907a41277aca2f8ee7a09523"
    for quant, size, sha in [("Q4_K_M",2740937888,"00fe7986ff5f6b463e62455821146049db6f9313603938a70800d1fb69ef11a4"),
                             ("Q8_0",4482403488,"10cc391b403021dd11c614679d2fd92f611c3681d29e29651b717316965d61e1")]:
        m = dict(next(m for m in models if m["Family"] == "qwen" and m["Quantization"] == quant))
        filename = f"Qwen3.5-4B-{quant}.gguf"
        m.update(Id="portable-unsloth-qwen35-4b-"+quant.lower().replace("_","-"), Name="Qwen 3.5 · 4B (Unsloth descarga)",
            RelativePath="portable_unsloth_qwen35_4b/"+filename, SizeBytes=size, Sha256=sha,
            DownloadUrl=f"https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/{upstream_revision}/{filename}?download=true",
            SourceUrl=f"https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/tree/{upstream_revision}")
        models.append(m)
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "catalog.json").write_text(json.dumps(models,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    # Read the canonical prompt field only; no cases/gold are copied into resources.
    baseline=json.loads((ROOT/"benchmark_smoke_test_v2.json").read_text(encoding="utf-8"))["system_prompt"]
    revision=json.loads((ROOT/"demo/prompts/human_review_20261109.json").read_text(encoding="utf-8"))
    assert hashlib.sha256(baseline.encode()).hexdigest()==revision["baseline_system_prompt_sha256"]
    prompts={"baseline":baseline,"revision_status":revision["status"]}
    for family in ("qwen","minicpm","gemma"):
        prompts[family]=baseline+"\n\n"+revision["common_appendix"]+"\n\n"+revision["family_appendices"][family]
    (OUT/"prompts.json").write_text(json.dumps(prompts,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(f"Prepared {len(models)} portable model records and prompt-only resources.")

if __name__ == "__main__": main()
