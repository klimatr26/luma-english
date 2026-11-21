# Acceso a Fase 1 y comparabilidad con Fase 2

Esta inspección responde a la pregunta del usuario antes de iniciar las matrices autorizadas. Es un inventario de solo lectura: no modifica casos, RAW, juicios ni resultados históricos. Los 24 artefactos protegidos siguen byte-idénticos al baseline.

## Qué resultados existen

La primera corrida está en `benchmark_results_v2/`: contiene 269 filas únicas. Se interrumpió con MiniCPM5-2B en 29/40; seis modelos anteriores tienen 40/40. No incluye una corrida de Gemma. Los RAW y metadatos permanecen disponibles para auditar el incidente.

La repetición consolidada está en `benchmark_results_v2_rerun/`: contiene 320 filas únicas, ocho modelos por los mismos 40 casos. Se conservan RAW con respuesta original, JSON parseado y telemetría; metadatos de checkpoint/revisión/runtime/generación; juicios por modelo; CSV por caso; resúmenes y comparaciones; notas de auditoría; juicios históricos pendientes de revisión humana (la auditoría declara seis, pero el registro y los juicios enumeran cinco). Es la fuente de la comparación histórica principal, según sus notas de auditoría. No se mezclan sus filas con la corrida interrumpida.

Los ocho modelos históricos fueron LFM2.5-350M, LFM2.5-1.2B-Instruct, LFM2.5-1.2B-Thinking, Qwen3.5-0.8B, Qwen3.5-2B, MiniCPM5-1B, MiniCPM5-2B y Gemma 4 E2B QAT Mobile.

## Correspondencia con la matriz actual

| Configuraciones actuales | Antecedente en 40 casos | Alcance de la correspondencia |
|---|---|---|
| Qwen3.5-2B F16/Q8_0/Q4_K_M | Qwen3.5-2B BF16 Transformers | Misma revisión fuente oficial declarada; cambian conversión, precisión, backend y generación. |
| MiniCPM5-2B F16/Q8_0/Q4_K_M | MiniCPM5-2B BF16 Transformers | Mismo nombre de modelo; artefactos GGUF y revisión de distribución registrados separadamente. |
| LFM2.5-1.2B-Instruct BF16/Q8_0/Q4_K_M | LFM2.5-1.2B-Instruct BF16 Transformers | Mismo checkpoint nominal; comprobar procedencia de distribución GGUF sin presumir identidad de bytes. |
| Gemma E2B oficial Q4_0 y Unsloth UD | Gemma 4 E2B QAT Mobile Transformers | Familia relacionada; el checkpoint Mobile, los GGUF y las variantes Unsloth no son una misma configuración experimental. |
| Qwen3.5-4B Q8_0/Q4_K_M | Ninguno | Incorporación de desarrollo; no atribuirle resultados históricos de 40 casos. |
| LFM2.5-2.6B Q8_0/Q4_K_M | Ninguno | Incorporación nueva; sus 80 inferencias sobre los 40 casos se guardarán en `results_40_lfm26/`. |

No existen resultados previos para las dieciséis configuraciones exactas actuales. La Fase 1 proporciona antecedentes de cuatro modelos/familias incluidos ahora, no un baseline emparejado por cada GGUF y cuantización.

## Cómo y por qué se documenta la diferencia

Se leyó el inventario de hashes, los dos archivos de metadatos, los RAW y las notas de auditoría. Se contaron filas y pares únicos modelo/caso, sin regenerar resultados ni alterar puntuaciones. Los hashes y conteos verificables están en `manifests/phase1_results_access_audit_20261011.json`.

Fase 1 consolidada usó Transformers 5.18.0, torch 2.14.1+cu130, contexto 4096, generación greedy (`do_sample=false`), máximo 2048 tokens y seed no fijada. La primera corrida interrumpida tenía máximo 512 tokens; el usuario precisó que thinking agotaba ese presupuesto de salida en MiniCPM, coherente con la incidencia descrita por la auditoría. La Fase 2 usa llama.cpp b11457, GGUF, muestreo por familia congelado, seed42, máximo512 tokens y thinking desactivado. También cambia el conjunto de casos y se endurece/separa la evaluación de formato y contenido.

Por estas diferencias, un cambio de puntuación entre fases no identifica por sí solo un efecto causal de cuantización, backend o tamaño del modelo. La comparación de cuantizaciones se hará dentro de la matriz de desarrollo actual, conservando parámetros por familia, y documentando las fuentes distintas de Gemma. Los resultados históricos se presentarán como exploratorios con sus definiciones originales; cualquier armonización posterior tendrá artefactos nuevos y trazabilidad, sin reescribir Fase 1.

La matriz actual de 120 casos está destinada a desarrollo. El test final permanece sin crear ni consultar. Los juicios semánticos de IA y las métricas automáticas provisionales se distinguirán de la aprobación/revisión humana; las etiquetas históricas de autoría no se tomarán como evidencia nueva de una revisión humana realizada ahora.

## Autorización y documentación del trabajo de titulación

El usuario autorizó expresamente 1920 inferencias de desarrollo y 80 de la extensión LFM2.6, con obligación de documentar qué se hizo, cómo, por qué y los resultados. La autorización se conserva en `manifests/main_execution_authorization_20261011.json`, vinculada a ambos benchmarks y al manifiesto exacto. Este inventario se escribió antes de iniciar las matrices. Tras la orden posterior «Procede con las inferencias», se inició la matriz de 120; el registro y los resultados de ejecución se mantienen separados de esta inspección histórica.

La documentación de ejecución debe conservar diseño/cuotas, procedencia y licencias, hashes, recetas de conversión/cuantización, runtime y hardware, parámetros/templates, protocolo y retries técnicos, RAW íntegros, selección de tentativas, rúbrica, métricas/denominadores, incidencias e invalidaciones compartidas y límites de interpretación. El informe final registrará también ejecuciones fallidas y no presentará mediciones de readiness como calidad del benchmark.
