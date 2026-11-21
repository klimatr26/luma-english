# Resultados históricos de la Fase 1: prueba exploratoria de 40 casos

## Alcance y procedencia

Este informe conserva los resultados de `writing_a1_a2_smoke_v2` para documentar el trabajo de titulación. La prueba contiene 40 casos: 30 textos con errores y 10 controles correctos, repartidos entre A1 y A2. No se volvieron a ejecutar modelos ni se recalcularon las métricas: la tabla reproduce los artefactos de comparación guardados en `benchmark_results_v2_rerun/comparison_v2.csv` y `.md`.

La comparación histórica principal es la segunda corrida consolidada, con 320 pares únicos modelo-caso (8 modelos × 40 casos). La corrida inicial interrumpida es un registro operativo separado. Sus filas no se mezclaron con las 320 filas consolidadas ni se presentaron como un modelo adicional.

## Corrida inicial interrumpida

El archivo `benchmark_results_v2/raw_outputs.jsonl` conserva 269 pares modelo-caso: seis modelos completaron 40 casos y MiniCPM5-2B llegó a 29/40. No incluye Gemma. En las 29 salidas registradas para MiniCPM5-2B, el RAW marca `completed=false`; 23 alcanzaron el límite de 512 tokens. No hay una tabla histórica de puntuaciones para esta corrida.

La auditoría atribuye la interrupción al modo de pensamiento de MiniCPM5: el ejecutor no le pasó explícitamente `enable_thinking=False`, y el límite de salida estaba en 512 tokens. En esta configuración, la generación de pensamiento agotó el presupuesto de salida antes de obtener una respuesta utilizable en los casos afectados. Esta incidencia explica por qué la corrida terminó en 29 casos; no se interpreta como una estimación de calidad del modelo. En la repetición se desactivó el modo de pensamiento de MiniCPM y se elevó el límite de salida.

| Modelo | Pares guardados |
|---|---:|
| LFM2.5-350M | 40/40 |
| LFM2.5-1.2B-Instruct | 40/40 |
| LFM2.5-1.2B-Thinking | 40/40 |
| Qwen3.5-0.8B | 40/40 |
| Qwen3.5-2B | 40/40 |
| MiniCPM5-1B | 40/40 |
| MiniCPM5-2B | 29/40 |

Parámetros registrados para la primera corrida: Transformers 5.18.0, PyTorch 2.14.1+cu130, CUDA 13.0, contexto máximo de 4096 tokens, generación greedy (`do_sample=false`), máximo de 512 tokens nuevos, sin gramática JSON y sin semilla fijada. El dispositivo registrado fue una NVIDIA GeForce RTX 3070.

## Resultados consolidados de los ocho modelos

Los denominadores son los del reporte original: 40 casos, 20 por nivel, 30 textos con errores, 10 controles y 59 errores de referencia en los textos con errores. `A1` y `A2` cuentan casos completamente correctos en cada nivel; los demás conteos mantienen el nombre y el sentido de las columnas originales.

| Modelo | Correctos /40 | % | Parciales | Incorrectos | A1 /20 | A2 /20 | Textos resueltos /30 | Controles preservados /10 | Controles modificados | Controles con FP | FCR | Errores detectados /59 | Falsos positivos | Casos con pérdida de significado | Explicaciones incorrectas | JSON válido /40 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemma 4 E2B QAT Mobile | 32 | 80.0% | 5 | 3 | 16 | 16 | 23 | 9 | 0 | 1 | 0% | 54 | 3 | 1 | 8 | 0 |
| Qwen3.5-2B | 28 | 70.0% | 7 | 5 | 16 | 12 | 18 | 10 | 0 | 0 | 0% | 49 | 2 | 1 | 6 | 39 |
| MiniCPM5-2B | 22 | 55.0% | 14 | 4 | 11 | 11 | 12 | 10 | 0 | 0 | 0% | 48 | 6 | 3 | 13 | 39 |
| LFM2.5-1.2B-Instruct | 20 | 50.0% | 19 | 1 | 13 | 7 | 10 | 9 | 1 | 0 | 10% | 45 | 15 | 2 | 15 | 40 |
| Qwen3.5-0.8B | 17 | 42.5% | 13 | 10 | 9 | 8 | 7 | 10 | 0 | 0 | 0% | 34 | 2 | 2 | 17 | 40 |
| LFM2.5-1.2B-Thinking | 6 | 15.0% | 10 | 24 | 4 | 2 | 1 | 5 | 3 | 0 | 30% | 20 | 4 | 22 | 24 | 0 |
| MiniCPM5-1B | 1 | 2.5% | 23 | 16 | 1 | 0 | 1 | 0 | 0 | 9 | 0% | 31 | 21 | 5 | 29 | 27 |
| LFM2.5-350M | 0 | 0.0% | 24 | 16 | 0 | 0 | 0 | 0 | 7 | 10 | 70% | 21 | 38 | 14 | 35 | 40 |

`FP` denota falsos positivos. `FCR` reproduce la tasa de falsa corrección del CSV de comparación. Las métricas de la tabla son las anotaciones y agregados originales, no una nueva evaluación. Un resultado de JSON válido solo mide el contrato de salida; por sí solo no significa que la corrección lingüística sea correcta.

En la repetición, el checkpoint Gemma produjo fences Markdown en las 40 respuestas, por eso el artefacto marca 0/40 JSON válidos aunque el contenido pudo parsearse y evaluarse semánticamente. LFM2.5-1.2B-Thinking alcanzó el máximo de 2048 tokens en 18/40 casos; esos casos aparecen como truncados y no se reintentaron. El campo `completed` original comparaba con EOS genérico, que no coincide con el fin de generación de todas las familias; la auditoría recomienda usar el indicador operativo de no truncamiento y ausencia de error de runtime al interpretar la finalización.

## Método y checkpoints de la corrida consolidada

La repetición utilizó la misma huella del benchmark, plantillas de chat nativas locales, contexto de 4096 tokens y generación greedy (`do_sample=false`) con un máximo de 2048 tokens nuevos. No se impuso una gramática JSON y no se fijó semilla. Se usaron Transformers 5.18.0, PyTorch 2.14.1+cu130, CUDA 13.0 y la misma NVIDIA GeForce RTX 3070. Se desactivó `enable_thinking` para MiniCPM, Qwen y Gemma; LFM2.5-1.2B-Thinking permaneció como checkpoint dedicado de razonamiento.

| Modelo | Identificador del checkpoint | Revisión registrada |
|---|---|---|
| LFM2.5-350M | `LiquidAI/LFM2.5-350M` | `9e6c6ccf47cd318696e137d381a7ded8fe4df09f` |
| LFM2.5-1.2B-Instruct | `LiquidAI/LFM2.5-1.2B-Instruct` | `0f604ada3f766f9f257460c4c9f0b5d6f69d431b` |
| LFM2.5-1.2B-Thinking | `LiquidAI/LFM2.5-1.2B-Thinking` | `f313478934a7612d22991f752959d7a1a8756fec` |
| Qwen3.5-0.8B | `Qwen/Qwen3.5-0.8B` | `2fc06364715b967f1860aea9cf38778875588b17` |
| Qwen3.5-2B | `Qwen/Qwen3.5-2B` | `15852e8c16360a2fea060d615a32b45270f8a8fc` |
| MiniCPM5-1B | `openbmb/MiniCPM5-1B` | `87179e5c1f455ef22e6223592d2d61351b525bfc` |
| MiniCPM5-2B | `openbmb/MiniCPM5-2B` | `f97400052a43d642bbc6e9975e2397e3ae6a6b52` |
| Gemma 4 E2B QAT Mobile | `google/gemma-4-E2B-it-qat-mobile-transformers` | `dd693ff40353f057ca5f07e945ad867f4afbf2ec` |

Los siete checkpoints que también aparecen en la corrida inicial conservan las revisiones registradas allí. Gemma se incorporó en la repetición y su checkpoint ya incluía cuantización QAT; no equivale a un Gemma E2B no cuantizado ni a una conversión GGUF.

## Juicios y revisión humana pendiente

`judgments_*.json`, `case_results_v2.csv` y `model_summaries_v2.json` conservan las etiquetas históricas (`CORRECT`, `PARTIAL`, `INCORRECT`) y las explicaciones por caso. Se reportan como juicios anotados del conjunto histórico. La nota de auditoría describe la evaluación como lectura humana asistida, pero los artefactos no registran una identidad verificable de revisor, una aprobación independiente ni una firma de validación actual. Por ello, las etiquetas existentes no se presentan como evidencia de una nueva aprobación humana.

Hay una discrepancia documental que debe quedar visible: `audit_notes_v2.md` afirma que seis juicios tienen `needs_human_review`; en cambio, `needs_human_review_v2.json` enumera cinco entradas y los JSON de juicios/sumarios también suman cinco (Qwen3.5-2B: 2; MiniCPM5-1B: 2; MiniCPM5-2B: 1). Los cinco identificadores enumerados son Qwen3.5-2B/A1-E04, Qwen3.5-2B/A1-E08, MiniCPM5-1B/A1-E11, MiniCPM5-1B/A1-C05 y MiniCPM5-2B/A2-E14. No se ha añadido ni supuesto una sexta entrada. Estas marcas significan revisión pendiente, no aprobación.

## Relación con las matrices posteriores y límites

Fase 1 sirve como antecedente exploratorio para algunos modelos o familias, no como línea base emparejada de las configuraciones posteriores. En las matrices nuevas cambian el runtime a llama.cpp b11457, el formato a GGUF, la cuantización, la precisión y el muestreo congelado por familia; se usan seed 42, máximo de 512 tokens y pensamiento desactivado. También cambia el conjunto de casos. Por ello, una diferencia de puntuación entre fases no permite atribuir causalmente el cambio al tamaño, a la cuantización, al backend o a un único parámetro.

Hay continuidad nominal de checkpoint para Qwen3.5-2B, MiniCPM5-2B y LFM2.5-1.2B-Instruct, pero las nuevas corridas usan conversiones GGUF y variantes de precisión/cuantización distintas de la referencia Transformers BF16. El Gemma QAT Mobile histórico es un checkpoint diferente de las variantes oficiales y Unsloth usadas después. Qwen3.5-4B y LFM2.5-2.6B no tienen resultados previos en estos 40 casos. Por tanto, ninguna de las configuraciones actuales tiene una medición histórica exacta bajo la misma combinación de checkpoint, artefacto, runtime y parámetros.

La muestra es una prueba exploratoria de 40 casos. Los porcentajes describen estos casos y no justifican generalización estadística a todos los textos A1/A2 ni afirmaciones causales. Los resultados semánticos, las métricas de formato y la telemetría de ejecución responden preguntas distintas y deben seguir identificándose por separado en la tesis.

## Archivos fuente, hashes e integridad

El benchmark congelado fue `SLM_A1A2/benchmark_smoke_test_v2.json`, SHA-256 `a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9`. Su huella coincide con ambas corridas.

| Artefacto | SHA-256 |
|---|---|
| `benchmark_results_v2/raw_outputs.jsonl` (corrida inicial) | `3d73ad9cb9e4e2d76f2bd991f0dbc5c9c2be38dcd0c281e73e01f107023c56e0` |
| `benchmark_results_v2/run_metadata.json` (corrida inicial) | `95b17176bee03d78a3afe3ff7c2b125ff01db565172521c24399fd93efc7574d` |
| `benchmark_results_v2_rerun/raw_outputs.jsonl` | `589c62551271a3ffd3cf9e96c1daafec6db18589754708ba6505b3ee92ee0a23` |
| `benchmark_results_v2_rerun/run_metadata.json` | `321360b8b9feb07f73897fe649cc761c2618f400045bc160aa27ffc2dea99a5c` |
| `benchmark_results_v2_rerun/comparison_v2.csv` | `7248c7b8a2d850003bc89d1a574baf3089c161a918cacd14810e23b69bea9548` |
| `benchmark_results_v2_rerun/comparison_v2.json` | `d14789c167b44f7a4c498041a3fbeceaf2fad8a7d456445ffc0a9306160218cc` |
| `benchmark_results_v2_rerun/needs_human_review_v2.json` | `2ac45b597633d59072bd03c4f64cf4ec762bde9f97440ef0bf5ab0deb393bd52` |

El manifiesto `benchmark_40_archive/phase1_baseline_hashes.json` registra los hashes y tamaños de los 24 artefactos protegidos de Fase 1. La auditoría de acceso de `manifests/phase1_results_access_audit_20261011.json` confirma 269 y 320 filas respectivamente y que los 24 artefactos permanecieron byte-idénticos durante la inspección histórica.

Fuentes de métricas: `benchmark_results_v2_rerun/comparison_v2.csv`, `comparison_v2.json`, `comparison_v2.md`, `case_results_v2.csv`, `model_summaries_v2.json`, ocho archivos `judgments_*.json`, `needs_human_review_v2.json`, `audit_notes_v2.md` y `run_metadata.json`. Fuente de la corrida interrumpida: `benchmark_results_v2/raw_outputs.jsonl` y `run_metadata.json`. Estos archivos se conservaron sin cambios.
