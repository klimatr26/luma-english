# Ampliación autorizada de la preparación — 2026-10-11

La petición incorpora LFM2.5-2.6B en Q8 y Q4 a los benchmarks de 40 y 120 casos.
Se concretan como los GGUF oficiales PTQ Q8_0 y Q4_K_M, siguiendo los formatos
de la matriz existente. No se añade F16, Q4_0, QAD ni DSpark para este modelo.

La matriz de desarrollo pasa de 14 a 16 configuraciones: 16 × 120 = 1920
inferencias futuras. Las configuraciones 15/16 usan los puertos 8115/8116.
La extensión de Fase 1 tendrá 2 × 40 = 80 inferencias futuras en artefactos
separados bajo results_40_lfm26. Los 40 enunciados y resultados anteriores
permanecen intactos; se conserva su SHA y el inventario de 24 artefactos.

Esta ampliación modifica la preparación del plan original, no autoriza las
inferencias de 120 ni las de 40. Antes de aprobación expresa solo se permite
una generación sintética de readiness por configuración, ajena a los benchmarks.
La readiness de las dos configuraciones nuevas puede servir a ambos conjuntos;
no se repite por cada benchmark. «Continúa» no autoriza la ejecución principal.
No se crea, abre ni consulta el test final de aproximadamente 200 casos.

Procedencia fijada: LiquidAI/LFM2.5-2.6B-GGUF, revisión
e7caca5d835a3901a8e0d63e94009429bafafdfc, licencia lfm1.0. La etiqueta genérica
`other` de HF se resuelve con `license_name: lfm1.0` de la ficha fijada.
Los tamaños/hashes están en lfm26_upstream_snapshot_120.json y el registro de
adquisición; no se atribuye ausencia de imatrix si no consta.

Parámetros previos a cualquier respuesta: temperature 0.1, top_k 50,
repeat_penalty 1.1, según la ficha oficial del 2.6B; top_p 0.95 y min_p 0.05
son defaults explícitos del backend. Presence/frequency penalty 0, seed 42,
max_tokens 512, contexto 4096, intento ngl 999, plantilla GGUF nativa.
Ambas cuantizaciones usan los mismos parámetros. La comparación con el 1.2B
(repeat_penalty 1.05 en la preparación existente) no aísla solo tamaño.

Subagentes invocados mediante collaboration.spawn_agent con
model=gpt-6-luna, reasoning_effort=max, fork_turns=none. No se modifica
opencode.jsonc. Ante rate limit de esos agentes se guarda traspaso y se detiene,
sin reintentar ni sustituir el modelo.

Fuentes: https://huggingface.co/LiquidAI/LFM2.5-2.6B-GGUF/tree/e7caca5d835a3901a8e0d63e94009429bafafdfc
y https://learn.chatgpt.com/docs/agent-configuration/subagents.
