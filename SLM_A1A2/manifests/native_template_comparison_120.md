# Native Gemma template comparison

synthetic text-only; enable_thinking=false; no tools; no benchmark content

Python Jinja2 sandbox; native llama.cpp /apply-template remains a separate readiness gate

All five tested renders equal across three configurations: True.

Finite synthetic renders support equivalence in the tested path, not general logical equivalence. Tool-call differences remain; no template substitution.

| Config | Native template SHA256 |
|---|---|
| gemma4_e2b_qat_q4_0 | 0a2c8073c878ab1da004bee933a998606537bbb62016310352c7285c3f01c5b5 |
| gemma4_e2b_ud_q4_k_xl | 241c50d86bdfe5e43307da87f559cd2416aacd67a8de46c15acc0105ef2200b7 |
| gemma4_e2b_ud_q2_k_xl | 241c50d86bdfe5e43307da87f559cd2416aacd67a8de46c15acc0105ef2200b7 |
