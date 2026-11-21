# Incidencia técnica de codificación en la comparación de finalistas

El conjunto y el protocolo se congelaron en el commit local `1b58599`, antes de iniciar inferencias. Benchmark SHA-256 `ecfe10cf6942788bfa059379e0461ab9e6291a00b5ef330bc806d94cb21dc125`; manifiesto SHA-256 `9ec595218c105e6a2b48d515dcffd01bbfd762b94646b2958f5f972b987e9878`.

El primer intento se interrumpió en el bloque Gemma/Vulkan: se conservaron 31 respuestas completas y un fallo técnico en la pregunta 32 (`T200-A1-E006`). El worker de Python imprimía JSON con caracteres no ASCII usando la codificación predeterminada de Windows, mientras el lector del coordinador exigía UTF-8. El byte `e9` de una cadena acentuada provocó `UnicodeDecodeError`. La respuesta de ese caso no quedó observable en RAW; se conserva el error técnico y no se reconstruye una respuesta inventada.

Se archiva íntegramente ese intento en `results_finalists_200_v1_interrupted_encoding_20261117/`, incluidos RAW, inicios de intento, telemetría y log nativo. Se conserva un inventario de hashes anterior al traslado. No se eligen respuestas del intento incompleto para puntuar. Se reinicia la matriz completa de 800 con el mismo conjunto, pesos, prompts, muestreo, semilla, contexto, gramática y binarios. Los scripts Python congelados permanecen idénticos.

La corrección es de entorno: el lanzador `scripts/run_finalists_200_utf8.ps1` fija `PYTHONIOENCODING=utf-8` para el coordinador y sus hijos. Una sonda sin inferencia comprobó que `café` viaja con bytes UTF-8 `63 61 66 c3 a9`. Se registra el lanzador y el entorno en `manifests/finalists_200_execution_amendment_20261117.json`. El reinicio se debe exclusivamente al fallo técnico de transporte y completitud de la matriz; no hubo cambios guiados por la calidad de las respuestas.

La comparación principal conserva una respuesta por cada combinación caso/modelo/backend. El intento interrumpido se informa aparte y se mantiene disponible para auditoría. Su calentamiento y sus 32 intentos adicionales no forman parte de las 800 respuestas puntuadas.
