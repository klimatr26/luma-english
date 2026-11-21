"""Offline synthetic text-only template renders; no model inference or benchmark reads."""
import hashlib
import json
from pathlib import Path

from jinja2.sandbox import ImmutableSandboxedEnvironment
from prepare_experiment_120 import CONFIGS, gguf_meta_streaming


def main():
    lab = Path(__file__).resolve().parents[1]
    env = ImmutableSandboxedEnvironment(trim_blocks=True, lstrip_blocks=True)
    def raise_exception(message):
        raise ValueError(message)
    env.globals['raise_exception'] = raise_exception
    probes = [
        [{'role': 'user', 'content': 'Synthetic technical input.'}],
        [{'role': 'system', 'content': 'Return plain text.'}, {'role': 'user', 'content': 'Synthetic technical input.'}],
        [{'role': 'system', 'content': ' Keep content. '}, {'role': 'user', 'content': ' Line one.\nLine two: "x", 2 < 3. '}],
        [{'role': 'system', 'content': 'Return JSON.'}, {'role': 'user', 'content': '{"value": "á", "flag": true}'}],
        [{'role': 'user', 'content': 'First synthetic turn.'}, {'role': 'assistant', 'content': 'Synthetic reply.'}, {'role': 'user', 'content': 'Second synthetic turn.'}],
    ]
    rows = []
    for spec in (s for s in CONFIGS if s[2] == 'gemma'):
        meta = gguf_meta_streaming(lab / spec[4])
        source = meta['tokenizer.chat_template']
        tmpl = env.from_string(source)
        renders = [tmpl.render(messages=p, bos_token='<bos>', eos_token='<eos>',
                               tools=None, enable_thinking=False, add_generation_prompt=True)
                   for p in probes]
        rows.append({'id': spec[1], 'template_sha256': hashlib.sha256(source.encode()).hexdigest(),
                     'renders': renders, 'render_sha256': [hashlib.sha256(r.encode()).hexdigest() for r in renders]})
    equal = all(r['renders'] == rows[0]['renders'] for r in rows)
    report = {'scope': 'synthetic text-only; enable_thinking=false; no tools; no benchmark content',
              'engine': 'Python Jinja2 sandbox; native llama.cpp /apply-template remains a separate readiness gate',
              'synthetic_probes': probes, 'configs': rows, 'all_tested_renders_equal': equal,
              'limitation': 'Finite synthetic renders support equivalence in the tested path, not general logical equivalence. Tool-call differences remain; no template substitution.'}
    (lab / 'manifests/native_template_comparison_120.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    lines = ['# Native Gemma template comparison', '', report['scope'], '', report['engine'], '',
             f'All five tested renders equal across three configurations: {equal}.', '', report['limitation'], '',
             '| Config | Native template SHA256 |', '|---|---|']
    lines += [f"| {r['id']} | {r['template_sha256']} |" for r in rows]
    (lab / 'manifests/native_template_comparison_120.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('Gemma synthetic text/non-thinking render equality:', equal)
    return 0 if equal else 1


if __name__ == '__main__':
    raise SystemExit(main())
