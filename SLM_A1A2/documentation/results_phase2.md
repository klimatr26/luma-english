# Resultados y cierre experimental Writing A1/A2

## Alcance completado

Se recogieron 2560 respuestas nuevas: 120×16=1920 y 40×16=640. Todas las configuraciones actuales, incluidas Qwen3.5-4B y LFM2.5-2.6B, tienen ambos conjuntos. Las 80 observaciones LFM2.5-2.6B inicialmente previstas están incluidas en 640; no se duplicaron. Los resultados históricos de 40 casos permanecen intactos y se documentan en historical_phase1_results.md.

Hubo 0 fallos de transporte, 0 reintentos técnicos, 0 filas ausentes y 0 mezclas de hashes. Esto significa recepción HTTP exitosa, no corrección lingüística ni JSON válido en todas las respuestas. La auditoría verificó 2560 fingerprints del prompt canónico, 2560 RAW exactos y evidencia CUDA/offload en los 32 logs de configuración. Ninguna respuesta backend tuvo reasoning_content no vacío; las 16 configuraciones conservaron thinking desactivado. Los 16 puertos quedaron libres tras cleanup.

## Horas, duración y protocolo

| Matriz | Inicio UTC | Fin UTC | Duración de invocación | Filas |
|---|---|---|---:|---:|
| results_120 | 2026-10-11T17:16:40.974573+00:00 | 2026-10-11T18:24:11.615788+00:00 | 67.51 min | 1920 |
| results_40_current_16 | 2026-10-11T18:25:00.742074+00:00 | 2026-10-11T18:50:03.005875+00:00 | 25.04 min | 640 |

Hora local America/Guayaquil=UTC−5. La duración incluye carga/hash, health, generación, escritura y cierre; no es la suma de latencias de API. Se trabajó en un escritorio local con actividades de documentación y tests concurrentes durante partes de la corrida; no se reclama un entorno de rendimiento aislado. El runtime, prompts, seed 42, máximos 512/4096 y muestreo por familia permanecieron congelados. El intento previo con CWD incorrecto envió 0 peticiones.

Gold designa la referencia congelada de cada caso (texto corregido, errores y alternativas). RAW son las respuestas HTTP originales guardadas antes de parsear; las evaluaciones son archivos derivados y conservan la selección trazada de intentos.

## Cómo interpretar las métricas

Los veredictos y TP/FP/FN/P/R/F0.5 siguientes son **proxies automáticos provisionales de coincidencia estricta**, no juicios humanos de calidad lingüística. Hay 0 casos confirmados por humanos. El diagnóstico posterior annotation_granularity_diagnostic.md muestra que un modelo puede reconstruir exactamente el gold con fragmentos más cortos y recibir un veredicto negativo por granularidad. También puede haber discrepancias por esquema, flag is_correct o declaraciones incompletas. No se debe interpretar toda brecha como un único problema ni inferir una caída de calidad gramatical únicamente del F0.5.

El diagnóstico mecánico posterior conserva los puntajes primarios y se etiqueta como exploratorio; no fue una métrica seleccionada antes de inferir. Igualar el gold no confirma explicaciones ni significado de alternativas no listadas. No se eligieron respuestas por calidad ni se reescribió el gold. No se añadió ninguna invalidación de casos; eso no constituye validación humana del conjunto.

CTMR mide modificación del texto de controles; CFAR marca is_correct=false o errores declarados. ND significa casos no observables por problemas de forma/esquema y debe leerse junto al conteo observado: no equivale a cero falsas alarmas. JSON directo, recuperable, esquema válido y JSON estricto son dimensiones distintas.

## results_120: resultados primarios

Denominadores por configuración: 90 textos incorrectos y 30 controles. Todas tienen cobertura completa. Correcto/Parcial/Incorrecto son etiquetas provisionales de la rúbrica congelada; ND se informa separadamente.

| Configuración | C/P/I | P proxy | R proxy | F0.5 proxy | CTMR observado (ND) | CFAR observado (ND) | Directo/Recuperable/Inválido | Esquema válido | JSON estricto |
|---|---|---:|---:|---:|---|---|---|---:|---:|
| 01-qwen35-2b-f16 | 30/17/73 | 0.1894 | 0.1667 | 0.1844 | 3/30 (ND=0) | 5/30 (ND=0) | 117/1/2 | 110 | 110 |
| 02-qwen35-2b-q8-0 | 33/14/73 | 0.1894 | 0.1667 | 0.1844 | 3/30 (ND=0) | 4/30 (ND=0) | 117/2/1 | 108 | 108 |
| 03-qwen35-2b-q4-k-m | 33/15/72 | 0.1970 | 0.1733 | 0.1917 | 1/30 (ND=0) | 5/30 (ND=0) | 119/1/0 | 114 | 114 |
| 04-minicpm5-2b-f16 | 24/6/90 | 0.1667 | 0.1067 | 0.1498 | 2/30 (ND=4) | 10/30 (ND=4) | 79/11/30 | 86 | 76 |
| 05-minicpm5-2b-q8-0 | 26/11/83 | 0.2737 | 0.1733 | 0.2453 | 0/30 (ND=4) | 11/30 (ND=4) | 85/8/27 | 92 | 84 |
| 06-minicpm5-2b-q4-k-m | 36/10/74 | 0.2017 | 0.1600 | 0.1917 | 2/30 (ND=0) | 3/30 (ND=0) | 118/0/2 | 116 | 116 |
| 07-lfm25-12b-bf16 | 19/6/95 | 0.0745 | 0.0467 | 0.0665 | 7/30 (ND=0) | 7/30 (ND=0) | 120/0/0 | 118 | 118 |
| 08-lfm25-12b-q8-0 | 18/8/94 | 0.0952 | 0.0667 | 0.0877 | 7/30 (ND=0) | 8/30 (ND=0) | 120/0/0 | 118 | 118 |
| 09-lfm25-12b-q4-k-m | 21/2/97 | 0.0800 | 0.0133 | 0.0400 | 8/30 (ND=0) | 1/30 (ND=0) | 120/0/0 | 120 | 120 |
| 10-qwen35-4b-q8-0 | 43/20/57 | 0.3852 | 0.3467 | 0.3768 | 2/30 (ND=0) | 4/30 (ND=2) | 118/1/1 | 115 | 115 |
| 11-qwen35-4b-q4-k-m | 44/14/62 | 0.3538 | 0.3067 | 0.3433 | 2/30 (ND=0) | 5/30 (ND=0) | 116/1/3 | 114 | 114 |
| 12-gemma4-e2b-qat-q4-0 | 37/17/66 | 0.3147 | 0.3000 | 0.3116 | 0/30 (ND=0) | 14/30 (ND=0) | 93/27/0 | 120 | 93 |
| 13-gemma4-e2b-ud-q4-k-xl | 39/20/61 | 0.3082 | 0.3000 | 0.3065 | 0/30 (ND=0) | 7/30 (ND=4) | 20/100/0 | 116 | 19 |
| 14-gemma4-e2b-ud-q2-k-xl | 0/0/120 | 0.0000 | 0.0000 | 0.0000 | 6/30 (ND=24) | 5/30 (ND=28) | 0/45/75 | 8 | 0 |
| 15-lfm25-26b-q8-0 | 26/13/81 | 0.1571 | 0.1467 | 0.1549 | 0/30 (ND=1) | 11/30 (ND=2) | 0/115/5 | 112 | 0 |
| 16-lfm25-26b-q4-k-m | 7/21/92 | 0.1406 | 0.1800 | 0.1471 | 0/30 (ND=1) | 25/30 (ND=1) | 0/117/3 | 114 | 0 |

### Telemetría observada

RSS es pico del servidor durante peticiones; VRAM es el máximo de las muestras puntuales device-wide, incluye otros procesos y no es pico continuo atribuible al modelo. La latencia API incluye generación y prefilling/red local; depende de longitud de salida. Tokens/s de tokenizadores distintos no expresan idéntica cantidad de texto. TTFT fue no disponible por modo no streaming, no cero.

| Configuración | Latencia mediana (s) | Tokens salida mediana | RSS servidor máx (MiB) | VRAM muestra máx device-wide (MiB) | Stop/Length |
|---|---:|---:|---:|---:|---|
| 01-qwen35-2b-f16 | 2.215 | 191.0 | 5965.8 | 4685 | 120/0 |
| 02-qwen35-2b-q8-0 | 1.444 | 189.0 | 4252.7 | 2969 | 119/1 |
| 03-qwen35-2b-q4-k-m | 1.183 | 198.0 | 3537.8 | 2285 | 119/1 |
| 04-minicpm5-2b-f16 | 2.112 | 163.5 | 5329.6 | 5525 | 120/0 |
| 05-minicpm5-2b-q8-0 | 1.270 | 166.0 | 3170.1 | 3432 | 120/0 |
| 06-minicpm5-2b-q4-k-m | 0.842 | 155.0 | 2231.4 | 2525 | 120/0 |
| 07-lfm25-12b-bf16 | 0.667 | 97.0 | 2946.2 | 3310 | 120/0 |
| 08-lfm25-12b-q8-0 | 0.421 | 100.0 | 1765.5 | 2230 | 120/0 |
| 09-lfm25-12b-q4-k-m | 0.291 | 94.0 | 1174.9 | 1738 | 120/0 |
| 10-qwen35-4b-q8-0 | 2.560 | 179.5 | 8836.5 | 5567 | 119/1 |
| 11-qwen35-4b-q4-k-m | 2.001 | 194.5 | 8132.5 | 3839 | 117/3 |
| 12-gemma4-e2b-qat-q4-0 | 1.142 | 180.0 | 2497.2 | 2501 | 120/0 |
| 13-gemma4-e2b-ud-q4-k-xl | 1.047 | 173.0 | 2215.0 | 2367 | 120/0 |
| 14-gemma4-e2b-ud-q2-k-xl | 6.144 | 259.5 | 2337.6 | 1555 | 114/6 |
| 15-lfm25-26b-q8-0 | 1.972 | 230.0 | 3660.1 | 3875 | 116/4 |
| 16-lfm25-26b-q4-k-m | 1.760 | 302.5 | 2659.7 | 2731 | 116/4 |

### Diagnóstico posterior del texto corregido

| Configuración | Texto primario idéntico en incorrectos | Alternativa licenciada | Primario idéntico pero no C estricto | Efecto de ediciones declarado=gold |
|---|---:|---:|---:|---:|
| 01-qwen35-2b-f16 | 37/90 | 1/90 | 32 | 28/90 |
| 02-qwen35-2b-q8-0 | 38/90 | 1/90 | 31 | 27/90 |
| 03-qwen35-2b-q4-k-m | 41/90 | 0/90 | 33 | 26/90 |
| 04-minicpm5-2b-f16 | 35/90 | 0/90 | 27 | 28/90 |
| 05-minicpm5-2b-q8-0 | 40/90 | 0/90 | 29 | 32/90 |
| 06-minicpm5-2b-q4-k-m | 44/90 | 1/90 | 35 | 35/90 |
| 07-lfm25-12b-bf16 | 54/90 | 0/90 | 54 | 10/90 |
| 08-lfm25-12b-q8-0 | 55/90 | 0/90 | 55 | 8/90 |
| 09-lfm25-12b-q4-k-m | 55/90 | 1/90 | 55 | 1/90 |
| 10-qwen35-4b-q8-0 | 62/90 | 1/90 | 43 | 57/90 |
| 11-qwen35-4b-q4-k-m | 61/90 | 2/90 | 42 | 55/90 |
| 12-gemma4-e2b-qat-q4-0 | 72/90 | 1/90 | 51 | 64/90 |
| 13-gemma4-e2b-ud-q4-k-xl | 70/90 | 1/90 | 54 | 62/90 |
| 14-gemma4-e2b-ud-q2-k-xl | 7/90 | 0/90 | 7 | 1/90 |
| 15-lfm25-26b-q8-0 | 53/90 | 2/90 | 45 | 40/90 |
| 16-lfm25-26b-q4-k-m | 57/90 | 1/90 | 54 | 39/90 |

Los desgloses A1/A2, taxonomía, número de errores y longitud están en ../results_120/reports/subgroup_summary.csv; las matrices de casos y selección exacta de tentativas en case_matrix.csv; las evaluaciones individuales en ../results_120/evaluations/. Los archivos fuente y salidas están indexados por SHA en source_index.json.

## results_40_current_16: resultados primarios

Denominadores por configuración:30 textos incorrectos y10 controles. Todas tienen cobertura completa. Correcto/Parcial/Incorrecto son etiquetas provisionales de la rúbrica congelada; ND se informa separadamente.

| Configuración | C/P/I | P proxy | R proxy | F0.5 proxy | CTMR observado (ND) | CFAR observado (ND) | Directo/Recuperable/Inválido | Esquema válido | JSON estricto |
|---|---|---:|---:|---:|---|---|---|---:|---:|
| 01-qwen35-2b-f16 | 8/4/28 | 0.1633 | 0.1356 | 0.1569 | 3/10 (ND=0) | 1/10 (ND=0) | 39/1/0 | 35 | 35 |
| 02-qwen35-2b-q8-0 | 8/3/29 | 0.2195 | 0.1525 | 0.2018 | 3/10 (ND=0) | 1/10 (ND=0) | 35/2/3 | 31 | 31 |
| 03-qwen35-2b-q4-k-m | 9/7/24 | 0.1538 | 0.1356 | 0.1498 | 1/10 (ND=0) | 1/10 (ND=1) | 38/2/0 | 37 | 37 |
| 04-minicpm5-2b-f16 | 11/3/26 | 0.1707 | 0.1186 | 0.1570 | 0/10 (ND=1) | 0/10 (ND=1) | 29/3/8 | 31 | 28 |
| 05-minicpm5-2b-q8-0 | 12/3/25 | 0.1915 | 0.1525 | 0.1822 | 0/10 (ND=0) | 1/10 (ND=0) | 33/2/5 | 34 | 32 |
| 06-minicpm5-2b-q4-k-m | 12/3/25 | 0.1556 | 0.1186 | 0.1464 | 0/10 (ND=0) | 0/10 (ND=0) | 40/0/0 | 39 | 39 |
| 07-lfm25-12b-bf16 | 8/2/30 | 0.0588 | 0.0339 | 0.0513 | 2/10 (ND=0) | 1/10 (ND=0) | 40/0/0 | 40 | 40 |
| 08-lfm25-12b-q8-0 | 8/2/30 | 0.0465 | 0.0339 | 0.0433 | 2/10 (ND=0) | 1/10 (ND=0) | 40/0/0 | 40 | 40 |
| 09-lfm25-12b-q4-k-m | 9/2/29 | 0.1667 | 0.0339 | 0.0935 | 1/10 (ND=0) | 0/10 (ND=0) | 40/0/0 | 40 | 40 |
| 10-qwen35-4b-q8-0 | 16/8/16 | 0.4310 | 0.4237 | 0.4296 | 0/10 (ND=0) | 0/10 (ND=2) | 40/0/0 | 38 | 38 |
| 11-qwen35-4b-q4-k-m | 18/6/16 | 0.4615 | 0.4068 | 0.4494 | 0/10 (ND=0) | 0/10 (ND=0) | 38/1/1 | 36 | 36 |
| 12-gemma4-e2b-qat-q4-0 | 8/4/28 | 0.2407 | 0.2203 | 0.2364 | 0/10 (ND=0) | 5/10 (ND=1) | 27/12/1 | 37 | 26 |
| 13-gemma4-e2b-ud-q4-k-xl | 12/6/22 | 0.3158 | 0.3051 | 0.3136 | 0/10 (ND=0) | 4/10 (ND=3) | 7/33/0 | 37 | 6 |
| 14-gemma4-e2b-ud-q2-k-xl | 0/0/40 | 0.0000 | 0.0000 | 0.0000 | 1/10 (ND=8) | 2/10 (ND=9) | 0/21/19 | 4 | 0 |
| 15-lfm25-26b-q8-0 | 6/6/28 | 0.1607 | 0.1525 | 0.1590 | 0/10 (ND=0) | 5/10 (ND=0) | 0/38/2 | 38 | 0 |
| 16-lfm25-26b-q4-k-m | 1/4/35 | 0.0746 | 0.0847 | 0.0765 | 0/10 (ND=0) | 9/10 (ND=0) | 0/38/2 | 38 | 0 |

### Telemetría observada

RSS es pico del servidor durante peticiones; VRAM es el máximo de las muestras puntuales device-wide, incluye otros procesos y no es pico continuo atribuible al modelo. La latencia API incluye generación y prefilling/red local; depende de longitud de salida. Tokens/s de tokenizadores distintos no expresan idéntica cantidad de texto. TTFT fue no disponible por modo no streaming, no cero.

| Configuración | Latencia mediana (s) | Tokens salida mediana | RSS servidor máx (MiB) | VRAM muestra máx device-wide (MiB) | Stop/Length |
|---|---:|---:|---:|---:|---|
| 01-qwen35-2b-f16 | 2.314 | 207.0 | 5044.6 | 4723 | 39/1 |
| 02-qwen35-2b-q8-0 | 1.684 | 232.5 | 3380.8 | 3025 | 37/3 |
| 03-qwen35-2b-q4-k-m | 1.345 | 235.5 | 2686.1 | 2323 | 39/1 |
| 04-minicpm5-2b-f16 | 1.979 | 161.0 | 5027.4 | 5517 | 40/0 |
| 05-minicpm5-2b-q8-0 | 1.141 | 149.0 | 2864.4 | 3491 | 40/0 |
| 06-minicpm5-2b-q4-k-m | 0.928 | 172.0 | 1958.7 | 2553 | 40/0 |
| 07-lfm25-12b-bf16 | 0.556 | 81.5 | 2803.8 | 3347 | 40/0 |
| 08-lfm25-12b-q8-0 | 0.362 | 85.0 | 1641.2 | 2293 | 40/0 |
| 09-lfm25-12b-q4-k-m | 0.246 | 79.0 | 1133.9 | 1801 | 40/0 |
| 10-qwen35-4b-q8-0 | 3.089 | 218.5 | 7062.4 | 5519 | 40/0 |
| 11-qwen35-4b-q4-k-m | 2.472 | 239.0 | 5942.3 | 3829 | 38/2 |
| 12-gemma4-e2b-qat-q4-0 | 1.273 | 201.0 | 2217.1 | 2501 | 40/0 |
| 13-gemma4-e2b-ud-q4-k-xl | 1.258 | 210.0 | 1976.1 | 2367 | 40/0 |
| 14-gemma4-e2b-ud-q2-k-xl | 5.802 | 239.0 | 1866.2 | 1555 | 38/2 |
| 15-lfm25-26b-q8-0 | 2.071 | 244.0 | 3399.2 | 3875 | 40/0 |
| 16-lfm25-26b-q4-k-m | 1.694 | 293.5 | 2275.1 | 2731 | 40/0 |

### Diagnóstico posterior del texto corregido

| Configuración | Texto primario idéntico en incorrectos | Alternativa licenciada | Primario idéntico pero no C estricto | Efecto de ediciones declarado=gold |
|---|---:|---:|---:|---:|
| 01-qwen35-2b-f16 | 13/30 | 0/30 | 12 | 8/30 |
| 02-qwen35-2b-q8-0 | 9/30 | 0/30 | 8 | 6/30 |
| 03-qwen35-2b-q4-k-m | 10/30 | 0/30 | 10 | 9/30 |
| 04-minicpm5-2b-f16 | 15/30 | 1/30 | 13 | 10/30 |
| 05-minicpm5-2b-q8-0 | 16/30 | 1/30 | 13 | 11/30 |
| 06-minicpm5-2b-q4-k-m | 19/30 | 0/30 | 17 | 12/30 |
| 07-lfm25-12b-bf16 | 16/30 | 0/30 | 16 | 3/30 |
| 08-lfm25-12b-q8-0 | 16/30 | 0/30 | 16 | 3/30 |
| 09-lfm25-12b-q4-k-m | 16/30 | 0/30 | 16 | 1/30 |
| 10-qwen35-4b-q8-0 | 22/30 | 0/30 | 14 | 17/30 |
| 11-qwen35-4b-q4-k-m | 21/30 | 0/30 | 13 | 19/30 |
| 12-gemma4-e2b-qat-q4-0 | 21/30 | 0/30 | 18 | 19/30 |
| 13-gemma4-e2b-ud-q4-k-xl | 26/30 | 1/30 | 20 | 24/30 |
| 14-gemma4-e2b-ud-q2-k-xl | 3/30 | 0/30 | 3 | 1/30 |
| 15-lfm25-26b-q8-0 | 17/30 | 0/30 | 16 | 14/30 |
| 16-lfm25-26b-q4-k-m | 17/30 | 0/30 | 17 | 14/30 |

Los desgloses A1/A2, taxonomía, número de errores y longitud están en ../results_40_current_16/reports/subgroup_summary.csv; las matrices de casos y selección exacta de tentativas en case_matrix.csv; las evaluaciones individuales en ../results_40_current_16/evaluations/. Los archivos fuente y salidas están indexados por SHA en source_index.json.

## Hallazgos verificables y límites

En desarrollo, Gemma oficial obtuvo texto primario idéntico en 72/90 incorrectos y Qwen3.5-4B Q8 en 62/90; sus veredictos estrictos difieren porque también exigen declaraciones, flag y esquema. Estas cifras son correspondencias con una referencia, no validaciones humanas ni una selección final de modelo. El ejemplo A1-E001 demuestra una penalización por fragmentos cortos válidos; el resto de las brechas necesita revisión individual.

LFM2.5-2.6B Q8 y Q4 emitieron cercas Markdown en todas sus 160 respuestas por configuración (120+40); el cumplimiento JSON directo se mantuvo en 0 y los conteos recuperables/esquema se reportan aparte. No se quitó esa dificultad con una gramática ni un reintento. Gemma UD-Q2_K_XL mostró problemas importantes de formato y muchas terminaciones length; las cifras exactas arriba documentan ese comportamiento sin cambiar presupuesto ni sampling.

La comparación histórica Transformers se mantiene con su evaluación original, ocho modelos y 320 respuestas consolidadas; no se mezcla con el incidente inicial 269 ni se atribuyen diferencias a cuantización aisladamente. Las corridas nuevas usan backend, generación, artefactos y evaluación distintos. Los40 casos ya usados son exploratorios; no son un test final independiente. Una única semilla/corrida no proporciona una estimación de variabilidad entre corridas.

Se verificaron 24 artefactos históricos byte-idénticos,23 blobs Git históricos idénticos y 11 activos runtime contra sus hashes. El evaluador primario no cambió desde la preparación. No se creó, abrió ni consultó el test final. La revisión humana trazada de semántica, explicaciones y discrepancias de fragmentos permanece pendiente; no se fabrica una aprobación.

## Reproducción y fuentes

Los comandos se ejecutan desde SLM_A1A2. No repetir inferencias al regenerar informes. Para análisis de resultados existentes:

```powershell
.\.venv\Scripts\python.exe scripts/report_execution_results.py --scope results_120 --require-complete
.\.venv\Scripts\python.exe scripts/report_execution_results.py --scope results_40_current_16 --require-complete
.\.venv\Scripts\python.exe scripts/analyze_annotation_granularity.py --scope results_120
.\.venv\Scripts\python.exe scripts/analyze_annotation_granularity.py --scope results_40_current_16
.\.venv\Scripts\python.exe scripts/audit_completed_execution.py
```

Las autorizaciones y límites están en manifests/main_execution_authorization_20261011.json y main_execution_expansion_20261011.json. El índice de cierre en manifests/execution_completion_audit_20261011.json enlaza hashes,32 logs CUDA/offload,2560 prompts y RAW. Los RAW nuevos se preservan localmente fuera de Git; CSV/JSON de evaluación, informes y código quedan versionados en Git local sin remoto.
