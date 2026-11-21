# Auditoría independiente por IA de la comparación de finalistas

**Dictamen.** En las sesiones medidas, Gemma E2B UD-Q4_K_XL obtuvo menor latencia nativa y menor pico RSS en ambos backends. Qwen3.5 4B Unsloth Q4_K_M obtuvo mayor F0.5 de corrección textual y más casos que cumplen el criterio automático en CPU y Vulkan. En controles, Qwen produjo menos alarmas y preservó más casos íntegramente. Gemma modificó menos textos de control. La revisión puntual no detectó un defecto inequívoco en las referencias congeladas que obligue a invalidar un caso.

## Integridad y alcance

Verifiqué los SHA-256 del benchmark, manifiesto y cuatro archivos RAW contra `completion.json`. Cada configuración contiene los 200 identificadores esperados, una sola vez, con estado técnico 0 e intento 1. Las 800 filas de evaluación coinciden con su texto RAW y su hash. El protocolo y las fuentes se congelaron antes de inferir en `1b58599`. El manifiesto conserva el SHA-256 `9ec595218c105e6a2b48d515dcffd01bbfd762b94646b2958f5f972b987e9878`. [Protocolo](../../documentation/finalists_200_protocol_20261117.md) · [Registro de finalización](../completion.json)

Verifiqué los siete hashes del archivo inicial y sus 32 filas RAW. Hubo 31 respuestas completas y un fallo técnico de codificación en `T200-A1-E006` sin respuesta observable. El reinicio UTF-8 repitió la matriz completa y excluyó el bloque inicial entero. En la matriz principal, las tres respuestas Gemma que alcanzaron 512 tokens se conservaron y se evaluaron. Tuvieron `INVALID_JSON` y texto corregido no observable, dos en CPU y una en Vulkan. [Incidencia técnica](../../documentation/finalists_200_execution_20261117.md)

## Comparaciones pareadas

Los resúmenes JSON y CSV coinciden en los resultados principales. La tabla usa Qwen menos Gemma para las diferencias y expresa los intervalos bootstrap del 95 % en puntos porcentuales. Se remuestrearon los mismos 200 casos en cada comparación, con 2.000 réplicas estratificadas por nivel y condición. Cada modelo se ejecutó en dos backends sobre los mismos textos.

| Backend | Proxy Qwen / Gemma | Diferencia en proxy | F0.5 primario condicional Qwen / Gemma | Diferencia de F0.5 con no observables como FN |
|---|---:|---:|---:|---:|
| CPU | 170/200 · 146/200 | +12,0 pp [5,5 a 18,5] | 0,9241 · 0,8679 | +6,17 pp [1,01 a 11,92] |
| Vulkan | 171/200 · 143/200 | +14,0 pp [7,5 a 20,5] | 0,9282 · 0,8607 | +7,00 pp [1,99 a 12,30] |

Los intervalos de F0.5 usan todo el gold primario de los 150 textos incorrectos, con 255 ediciones alineadas por ERRANT frente a 248 errores intencionales del conjunto. Las comparaciones Vulkan–CPU dentro de cada modelo incluyen cero tanto en F0.5 como en el proxy. En las salidas observables de ambos backends, el texto corregido coincidió en 190 casos para Gemma y 195 para Qwen, sobre 200 pares en cada modelo. Estos intervalos describen la variación entre los casos sintéticos elegidos. El corpus y sus referencias fueron escritos y revisados por IA. [Resultados JSON](comparison.json) · [Resultados CSV](comparison.csv)

## Controles, contrato y ejemplos

- **Controles.** El CFAR de Qwen fue 6/50 en cada backend. Gemma tuvo 20/50 en CPU y 21/50 en Vulkan, en su mayoría en A1. Gemma dejó el texto intacto en 19 de sus 20 falsas alarmas CPU y 18 de 21 en Vulkan. En `T200-A1-C006` Vulkan, Gemma marcó el original incorrecto e incluyó un supuesto error cuya corrección repetía el fragmento y cuya explicación admitía que era gramatical. El CTMR fue 1/50 CPU y 3/50 Vulkan para Gemma, frente a 4/50 en ambos para Qwen. En `T200-A1-C002`, Qwen cambió el gramatical «until I arrive» por «until I get there» y justificó el cambio con una regla incorrecta.
- **Contrato.** El parser C# marcó `STRICT` 193/200 respuestas de Qwen en cada backend, 176/200 de Gemma CPU y 177/200 de Gemma Vulkan. El proxy combina estado utilizable, flag correcto y coincidencia exacta con alguna referencia completa licenciada. Gemma obtuvo 31 éxitos proxy en CPU y 28 en Vulkan con al menos una declaración identificable que repetía el fragmento original. En `T200-A2-E014` Vulkan, Qwen pasó el proxy con la alternativa licenciada «more warm», aunque su feedback pide «warmer» y su explicación vacila entre ambas. Son ejemplos de por qué el proxy y `STRICT` dejan abierta la calidad de la explicación. No hubo evaluación humana del feedback.
- **Referencia.** En `T200-A1-E070` Vulkan, «three pieces of paper» de Qwen coincide con una alternativa completa congelada. Gemma devolvió «three papers», que admite lecturas distintas según qué objeto se cuente. En `T200-A2-E075`, «showed» de Qwen es una lectura temporal posible y el gold conserva «shows» para la lectura habitual. Las coincidencias y penalizaciones publicadas responden a la política de referencias predefinida. Estos casos ilustran el alcance de la referencia, sin cambios de puntuación.

## Recursos

Gemma y Qwen tardaron, respectivamente, 13,229 s y 26,525 s en CPU, y 1,583 s y 2,134 s en Vulkan, según la mediana nativa. El cociente de medianas Qwen/Gemma tuvo IC 95 % de [1,945 a 2,106] en CPU y [1,289 a 1,422] en Vulkan. La latencia refleja también el número de tokens generados. Se ejecutó un bloque por configuración y el orden común de casos no contrabalanceó el orden de los bloques.

El pico RSS observado del árbol de procesos fue 2,690 GiB para Gemma y 4,173 GiB para Qwen en CPU, y 2,035 y 2,974 GiB en Vulkan. El pico de VRAM de la RTX 3070 en Vulkan fue 2.773 MiB para Gemma y 5.398 MiB para Qwen, con bases de 746 y 1.848 MiB antes de cargar. Sus incrementos observados, 2.027 y 3.550 MiB, corresponden al dispositivo completo bajo WDDM y pueden incluir otros procesos. Los picos muestreados incluyen carga y calentamiento. Las cifras de escritorio corresponden al hardware y las sesiones medidas. [Telemetría agregada](comparison.json)
