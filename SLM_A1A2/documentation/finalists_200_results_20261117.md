# Gemma E2B y Qwen3.5 4B en 200 preguntas nuevas

Comparación local de las configuraciones de producto, 17 de noviembre de 2026. Los mismos 200 textos fueron respondidos por ambos modelos en CPU y Vulkan: **800 respuestas puntuadas**. A1/A2: 100/100; incorrectos/controles: 150/50; 248 errores intencionales.

Qwen3.5 4B Unsloth Q4_K_M obtiene mejor corrección textual, clasificación y contrato utilizable en ambos backends. Gemma E2B UD-Q4_K_XL ofrece menor latencia y menor pico RSS. La recomendación de producto prioriza Qwen cuando cabe en memoria y Vulkan aporta beneficio; Gemma queda como alternativa rápida seleccionable.

## Qué mide la precisión

El conjunto fue redactado y revisado de forma cruzada por IA, con fuentes congeladas antes de inferir. Las puntuaciones automáticas contrastan con esas referencias; **no son una evaluación humana de las explicaciones**. El proxy de caso resuelto exige un JSON utilizable, flag correcto y texto idéntico a una referencia completa licenciada. Las explicaciones y las sugerencias opcionales requieren revisión del investigador.

| Configuración | Backend | Proxy caso resuelto /200 | Flag correcto /200 | JSON utilizable /200 | Texto observable en incorrectos /150 |
|---|---|---:|---:|---:|---:|
| Gemma E2B UD-Q4_K_XL | CPU | 146 | 181 | 176 | 148 |
| Gemma E2B UD-Q4_K_XL | Vulkan | 143 | 180 | 177 | 149 |
| Qwen3.5 4B Unsloth Q4_K_M | CPU | 170 | 192 | 193 | 150 |
| Qwen3.5 4B Unsloth Q4_K_M | Vulkan | 171 | 192 | 193 | 150 |

F0.5 da mayor peso a falsas correcciones que a omisiones. Se puntúan ediciones ERRANT en los textos incorrectos; las falsas alarmas en controles se publican aparte. La referencia primaria mide una reparación mínima; la mejor referencia completa licenciada admite las alternativas redactadas antes de observar respuestas.

| Configuración | Backend | Precisión ediciones primaria | Recall primario | F0.5 primario condicional | F0.5 multirreferencia condicional | F0.5 todo gold, no observable=FN |
|---|---|---:|---:|---:|---:|---:|
| Gemma E2B UD-Q4_K_XL | CPU | 0.8605 | 0.8988 | 0.8679 | 0.8679 | 0.8625 |
| Gemma E2B UD-Q4_K_XL | Vulkan | 0.8523 | 0.8964 | 0.8607 | 0.8607 | 0.8581 |
| Qwen3.5 4B Unsloth Q4_K_M | CPU | 0.9309 | 0.8980 | 0.9241 | 0.9403 | 0.9241 |
| Qwen3.5 4B Unsloth Q4_K_M | Vulkan | 0.9350 | 0.9020 | 0.9282 | 0.9443 | 0.9282 |

## Controles y contrato

| Configuración | Backend | CTMR /50 (ND) | CFAR /50 (ND) | STRICT | RECOVERED | INCONSISTENT | INVALID_JSON / INVALID_SCHEMA | Ediciones reconstruyen salida /200 | length |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemma E2B UD-Q4_K_XL | CPU | 1 (0) | 20 (0) | 176 | 0 | 22 | 2 / 0 | 122 | 2 |
| Gemma E2B UD-Q4_K_XL | Vulkan | 3 (0) | 21 (0) | 177 | 0 | 22 | 1 / 0 | 126 | 1 |
| Qwen3.5 4B Unsloth Q4_K_M | CPU | 4 (0) | 6 (0) | 193 | 0 | 7 | 0 / 0 | 176 | 0 |
| Qwen3.5 4B Unsloth Q4_K_M | Vulkan | 4 (0) | 6 (0) | 193 | 0 | 7 | 0 / 0 | 178 | 0 |

CTMR cuenta controles cuyo texto se modificó; CFAR cuenta alarmas de error en controles. ND no equivale a cero. JSON utilizable describe estructura/coherencia básica, no corrección lingüística. La generación fue restringida por gramática, igual que en la app; no se atribuye el formato al modelo sin esa ayuda. `length` indica que se alcanzó el límite y no implica por sí solo JSON incompleto.

## Tiempo y memoria

| Configuración | Backend | Mediana (s) | Media (s) | p95 (s) | Tokens salida, media | Tokens/s decode, mediana |
|---|---|---:|---:|---:|---:|---:|
| Gemma E2B UD-Q4_K_XL | CPU | 13.229 | 12.965 | 19.109 | 259.7 | 26.1 |
| Gemma E2B UD-Q4_K_XL | Vulkan | 1.583 | 1.591 | 2.461 | 255.1 | 176.1 |
| Qwen3.5 4B Unsloth Q4_K_M | CPU | 26.525 | 27.243 | 39.033 | 198.2 | 12.0 |
| Qwen3.5 4B Unsloth Q4_K_M | Vulkan | 2.134 | 2.236 | 3.761 | 200.2 | 107.4 |

| Configuración | Backend | Prefill, mediana (s) | Decode, mediana (s) | Tokens entrada, mediana |
|---|---|---:|---:|---:|
| Gemma E2B UD-Q4_K_XL | CPU | 2.500 | 10.473 | 758.000 |
| Gemma E2B UD-Q4_K_XL | Vulkan | 0.055 | 1.444 | 758.000 |
| Qwen3.5 4B Unsloth Q4_K_M | CPU | 10.321 | 16.039 | 742.000 |
| Qwen3.5 4B Unsloth Q4_K_M | Vulkan | 0.190 | 1.791 | 742.000 |

Latencia de generación nativa; carga y calentamiento se informan por separado en el JSON técnico. Cada petición borra el contexto, sin reutilizar el prefijo. Las respuestas pueden tener distinta longitud; la latencia combina el coste del backend y la respuesta que realmente produce.

| Configuración | Backend | Pico RSS árbol (GiB) | Pico privado comprometido (GiB) | Pico VRAM dispositivo (GiB) | VRAM previa a carga (MiB) | Casos con RAM / VRAM | RAM libre mínima sistema (GiB) |
|---|---|---:|---:|---:|---:|---:|---:|
| Gemma E2B UD-Q4_K_XL | CPU | 2.690 | 2.024 | 1.812 | 685 | 200 / 200 | 2.532 |
| Gemma E2B UD-Q4_K_XL | Vulkan | 2.035 | 2.463 | 2.708 | 746 | 200 / 200 | 5.878 |
| Qwen3.5 4B Unsloth Q4_K_M | CPU | 4.173 | 2.332 | 0.798 | 743 | 200 / 200 | 3.950 |
| Qwen3.5 4B Unsloth Q4_K_M | Vulkan | 2.974 | 4.253 | 5.271 | 1848 | 200 / 200 | 2.406 |

RSS incluye el worker y sus descendientes, para incluir el intérprete real detrás del lanzador de Windows; no incluye toda la interfaz Avalonia. La memoria privada comprometida puede no estar residente. Los picos son observados por muestreo, incluidos carga/calentamiento. VRAM es la memoria total del dispositivo, también usada por otras aplicaciones; no es una atribución exclusiva al modelo. La inicialización de plugins puede crear un contexto Vulkan incluso con cero capas de modelo en GPU.

## Comparaciones pareadas

Intervalos bootstrap del 95 %, 2000 remuestreos estratificados por nivel/condición; describen variación entre estos casos sintéticos. No corrigen sesgo del gold IA ni convierten los bloques en un experimento térmico contrabalanceado. Los intervalos F0.5 usan todo el gold con no observables como FN.

- **Gemma minus Qwen / cpu**: f0_5_difference_ci95 = [-0.1192, -0.0101]; task_success_rate_difference_ci95 = [-0.1850, -0.0550]; qwen_over_gemma_latency_ratio_ci95 = [1.9453, 2.1061].
- **Gemma minus Qwen / vulkan**: f0_5_difference_ci95 = [-0.1230, -0.0199]; task_success_rate_difference_ci95 = [-0.2050, -0.0750]; qwen_over_gemma_latency_ratio_ci95 = [1.2887, 1.4217].
- **Vulkan minus CPU / 13-gemma4-e2b-ud-q4-k-xl**: f0_5_difference_ci95 = [-0.0243, 0.0129]; task_success_rate_difference_ci95 = [-0.0350, 0.0000]; cpu_over_vulkan_latency_ratio_ci95 = [7.9963, 8.7057].
- **Vulkan minus CPU / portable-unsloth-qwen35-4b-q4-k-m**: f0_5_difference_ci95 = [0.0000, 0.0112]; task_success_rate_difference_ci95 = [0.0000, 0.0150]; cpu_over_vulkan_latency_ratio_ci95 = [12.0662, 12.7009].

| Modelo | RAW idéntico CPU/Vulkan /200 | Texto corregido idéntico observable /200 | Éxito sólo CPU | Éxito sólo Vulkan |
|---|---:|---:|---:|---:|
| 13-gemma4-e2b-ud-q4-k-xl | 11 | 190 | 3 | 0 |
| portable-unsloth-qwen35-4b-q4-k-m | 31 | 195 | 0 | 1 |

## Interpretación para la aplicación

En estas sesiones, Gemma tardó aproximadamente la mitad en CPU (13,23 frente a 26,53 s de mediana) y fue 1,35 veces más rápido en Vulkan (1,58 frente a 2,13 s). Los intervalos de la razón Qwen/Gemma fueron 1,95–2,11 en CPU y 1,29–1,42 en Vulkan. Los tamaños de salida difieren: Gemma generó unos 255–260 tokens por respuesta y Qwen unos 198–200; los valores de throughput y longitud permiten interpretar el coste. No se atribuye el resultado exclusivamente a la arquitectura.

Qwen resolvió el proxy texto/flag/JSON en 170/200 CPU y 171/200 Vulkan, frente a 146 y 143 de Gemma. El F0.5 primario sobre todo el gold fue 0,9241/0,9282 en Qwen y 0,8625/0,8581 en Gemma. La ventaja Qwen–Gemma fue de 6,17 puntos de F0.5 en CPU (IC95 % 1,01–11,92) y 7,00 en Vulkan (1,99–12,30), condicionada a este conjunto sintético. En controles, Qwen tuvo menos falsas alarmas: 6/50 frente a 20/50 CPU y 21/50 Vulkan. Gemma modificó menos controles: 1/50 y 3/50 frente a 4/50 de Qwen; no hay un ganador único en todas las métricas de controles. CPU/Vulkan produjeron textos corregidos idénticos observables en 190/200 Gemma y 195/200 Qwen. Los intervalos de las diferencias de calidad entre backends incluyen cero; no se afirma que Vulkan mejore por sí mismo la precisión.

Para el modo que prioriza corrección textual usaría Qwen3.5 4B Q4_K_M como predeterminado, conservando elección manual. Con Vulkan, el coste adicional observado frente a Gemma fue aproximadamente 0,55 s de mediana, a cambio de 28 casos más que cumplen el proxy. Para equipos limitados o uso exclusivo de CPU, Gemma ofrece menor espera y RSS, con su mayor tasa de falsas alarmas visible. Esta es una selección entre dos configuraciones preseleccionadas, no una certificación pedagógica ni una validación independiente posterior de ese ganador. La muestra confirma explicaciones erróneas incluso cuando el texto corregido coincide con el gold: ver [ejemplos diagnósticos](../results_finalists_200_v1/reports/diagnostic_examples.md). La interfaz debe conservar las advertencias de coherencia y permitir revisión de las sugerencias.

Las diferencias de procesamiento en el PC superaron claramente el margen de 1,15 de la política prevista, por lo que esta comparación no necesitó otra ronda móvil para separar rendimiento de precisión. La elección de backend en cada teléfono continúa dependiendo de su calibración y memoria; el ranking de latencia de escritorio no garantiza el mismo en cualquier SoC. Las mediciones previas del F8 Pro (un ejemplo sintético, Gemma 12,64 s y Qwen 22,53 s con Turnip) son evidencia separada, sin sumar sus casos a estos 200.

## Reproducción y límites

Pesos descargables Q4 de Unsloth y prompts revisados por familia; contexto 2048, 512 tokens, semilla 42, thinking desactivado, llama.cpp b12359. Qwen tiene un GGUF distinto del convertido local usado en 120. La comparación es entre configuraciones completas de producto. Hardware y muestreo exacto están en el manifiesto. Una configuración y una secuencia activas por vez.

El intento inicial interrumpido por codificación queda archivado completo y excluido de la puntuación. La matriz se reinició con UTF-8 explícito, conservando sin cambios dataset y configuración. [Incidencia y corrección técnica](finalists_200_execution_20261117.md).

[Protocolo previo](finalists_200_protocol_20261117.md), [validación del conjunto](../benchmark_200/validation.md), [resultados JSON](../results_finalists_200_v1/reports/comparison.json), [tabla CSV](../results_finalists_200_v1/reports/comparison.csv), [muestra sin puntuar para revisión del investigador](../results_finalists_200_v1/reports/researcher_review_sample.json).

Benchmark SHA-256 `ecfe10cf6942788bfa059379e0461ab9e6291a00b5ef330bc806d94cb21dc125`. Manifiesto `9ec595218c105e6a2b48d515dcffd01bbfd762b94646b2958f5f972b987e9878`. JSON de resultados `9d798b673d46a2dd736dbb41e2fc635f0e4dec68e72cc0c9ba62d7de9e994ff0`.

## Seguimiento de recursos en portátil

El 18 de noviembre se integraron las mediciones del HP ZBook con Quadro P1000: CPU, Vulkan completo/parcial, Intel UHD 630, batería y presupuesto simulado de 2 GiB. Usan 15 textos de desarrollo y no añaden observaciones a los 200 casos ni cambian sus puntuaciones. Qwen a 32/33 capas logró 23,22 s de mediana frente a 84,13 s en CPU; Gemma con Vulkan, 8,88 s. La evidencia y la política propuesta para elegir modelo/backend por calibración están en [integración y decisiones de despliegue](laptop_results_integration_20261118.md).
