# Auditoría del smoke test Writing A1/A2 v2

## Benchmark y congelación

- Benchmark: `writing_a1_a2_smoke_v2`
- Fuente única: `../benchmark_smoke_test_v2.json`
- SHA-256 confirmado antes y después de las inferencias: `a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9`
- 40 casos: 30 incorrectos y 10 controles correctos (15 incorrectos + 5 controles por nivel).
- No se cambió el benchmark tras su aprobación.

## Corridas

### Corrida inicial (incidencia de modo y límite)

- Archivos: `../benchmark_results_v2/`
- Se detuvo al detectar que el ejecutor no pasaba `enable_thinking=False` a MiniCPM y limitaba salidas a 512 tokens.
- Se conservan íntegramente sus respuestas; no se usan en la comparación principal.
- Antes de detenerla: LFM 350M, Instruct, Thinking, Qwen 0.8B y 2B, MiniCPM 1B completos; MiniCPM 2B, 29/40. Esta corrida sirve como auditoría del incidente.

### Corrida principal aislada

- Archivos: `raw_outputs.jsonl`, `run_metadata.json` en este directorio.
- 320 filas únicas (8 modelos × 40 casos), sin errores de runtime.
- Límite de salida: 2048 tokens; sin gramática JSON; `do_sample=False`; contexto común de 4096; BF16 salvo checkpoint Gemma QAT con dtype auto, cuantificación del checkpoint.
- Chat templates locales nativos. `enable_thinking=False` aplicado a MiniCPM, Qwen y Gemma; el checkpoint LFM Thinking se mantiene dedicado a razonamiento.
- Revisión/hash de cada checkpoint, runtime, parámetros, latencia, tokens y memoria están en `run_metadata.json` y por fila en los raws.

## Limitaciones e interpretación

- `completed` en el raw originalmente se calculó comparando con EOS genérico. Ese criterio no es compatible con los tokens de fin de varias familias. Para los resultados consolidados, `completed` se interpreta operacionalmente como no truncado y sin error de runtime; se conservan ambos campos (`completed` del ejecutor y `completed` operacional en la tabla CSV).
- El modelo LFM2.5-1.2B-Thinking produjo salidas de razonamiento largas: 18/40 alcanzaron el límite de 2048 tokens. No se reintentaron.
- Gemma 4 QAT Mobile produjo fences Markdown en las 40 respuestas, aunque el contenido JSON pudo revisarse semánticamente; `json_valid` permanece falso porque el contrato exige únicamente el objeto JSON. El checkpoint consumió hasta 7.75 GiB de VRAM en esta GPU de 8 GiB y promedió alrededor de 79.7 s por caso.
- La corrida inicial de MiniCPM no se mezcló con la corrida principal. En la segunda, MiniCPM usó explícitamente no-thinking; los raws iniciales y parciales se conservan en el otro directorio.
- Los juicios semánticos son evaluación humana asistida por lectura de casos; 6 juicios quedaron marcados `needs_human_review`. Se listan sin alterar el gold en `needs_human_review_v2.json`.
- Smoke test exploratorio de 40 casos; no sustenta generalización estadística ni reemplaza la siguiente fase de 120 casos.

## Exportaciones

- `raw_outputs.jsonl`: respuesta original más parseo y telemetría, por modelo/caso.
- `case_results_v2.csv`: juicios normalizados para 320 modelo-casos.
- `model_summaries_v2.json`: resúmenes por modelo y telemetría agregada.
- `comparison_v2.csv`, `comparison_v2.json`, `comparison_v2.md`: tabla comparativa ordenada según el criterio especificado.
- `needs_human_review_v2.json`: casos ambiguos/incompletos para revisión.
- `judgments_*.json`: juicios originales por cada uno de los ocho modelos.
