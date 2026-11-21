# Comparación de finalistas en 200 casos nuevos — protocolo prospectivo

17 de noviembre de 2026, UTC−5. Este protocolo se fija antes de generar respuestas del conjunto nuevo. El usuario autorizó explícitamente 200 preguntas para Gemma E2B y Qwen3.5 4B, con medición CPU/GPU y memoria, y permitió repetir las 200 por backend. Se ejecutarán 800 respuestas: dos modelos × dos backends × 200 casos. Una respuesta por caso, sin reintentos por formato ni por calidad. Cada carga tiene una generación sintética de calentamiento fuera del conjunto puntuado.

## Pregunta y alcance

Se comparan las dos configuraciones de producto preseleccionadas para decidir el modelo por defecto de la aplicación final. Los datos nuevos permanecen fuera de la elaboración de prompts y de la selección inicial de candidatos. La elección posterior del ganador entre estos dos usa los mismos resultados; no se presentará como una confirmación independiente posterior a esa elección. Cualquier mejora futura de prompting requerirá datos de desarrollo y otra evaluación independiente.

El conjunto de 200 se autoriza ahora; las prohibiciones de construirlo o consultarlo de la preparación de Fase 2 correspondían a una etapa anterior. Se conservan íntegros los datos y resultados de 40/120. No se sumarán sus filas como observaciones independientes del conjunto nuevo.

## Tratamientos congelados

- Gemma 4 E2B `gemma-4-E2B-it-qat-UD-Q4_K_XL.gguf`, catálogo `13-gemma4-e2b-ud-q4-k-xl`.
- Qwen3.5 4B `Qwen3.5-4B-Q4_K_M.gguf` descargable de Unsloth, catálogo `portable-unsloth-qwen35-4b-q4-k-m`. Este GGUF tiene un hash y tamaño diferentes del Qwen convertido localmente usado en 120; los resultados no se atribuyen al archivo antiguo.
- Puente nativo de la aplicación, ABI 2, llama.cpp b12359, commit `b1b770d90d94cad9e9ea5b993bdbc383a522fb28`; mismos DLL en CPU y Vulkan. No se modifica upstream. GPU es Vulkan en la RTX 3070 de escritorio; no es CUDA ni Mesa Turnip de Android.
- Prompts revisados por familia ya incluidos en `cross_demo/WritingApp.Shared/Assets/prompts.json`. Sus SHA y el muestreo del catálogo se congelan. La comparación corresponde a dos configuraciones completas, no a un aislamiento causal de los pesos con un prompt común.
- Plantilla nativa, thinking desactivado, contexto 2048, límite 512, semilla 42. El motor borra el estado entre peticiones. Sin visión, MTP ni draft model.
- Gramática `writing_json_grammar_v1`, igual a la aplicación. La validez de JSON resultante describe el sistema restringido; no demuestra obediencia espontánea al esquema ni se compara como mejora directa frente a la generación libre histórica.

Se repiten las mismas 200 preguntas en cada backend porque diferencias numéricas de implementación pueden alterar los tokens incluso con la misma semilla. [Discusión técnica upstream](https://github.com/ggml-org/llama.cpp/discussions/4020). El orden de casos es una permutación con semilla 20261117, común a los cuatro bloques. Orden de bloques: Gemma/Vulkan, Qwen/CPU, Gemma/CPU, Qwen/Vulkan. Se carga una configuración por vez. La ejecución por bloques puede confundirse con deriva térmica/carga externa; sus resultados describen estas sesiones, sin demostrar superioridad universal de una arquitectura.

## Construcción y congelación de los datos

200 textos originales: 100 A1 y 100 A2. En cada nivel hay 75 incorrectos y 25 controles. Por nivel, 42/20/10/3 textos contienen 1/2/3/4 errores: 248 errores intencionales en total. Longitudes A1 de 15–60 palabras y A2 de 25–100. Los autores IA trabajan por nivel y una revisión IA independiente examina cada caso antes del freeze. No hay validación humana del gold ni se simula la aprobación de un docente.

Los controles son gramaticales. Se admiten variantes británicas/estadounidenses estándar y sugerencias opcionales en feedback sin convertirlas en errores. Los errores deben ser inequívocos y las referencias preservar significado. Se comprueban cuotas, fragmentos únicos/no solapados, reconstrucción, alternativas completas y similitud interna y contra los 160 textos previos. Los umbrales de candidatos son SequenceMatcher ≥0,78 o Jaccard de trigramas de palabras ≥0,45; la comparación no prueba ausencia de paráfrasis. Cada candidato requiere resolución trazada antes del freeze.

Se vinculan los SHA de ambas fuentes, revisión y resoluciones al JSON congelado y al manifiesto. El evaluador no recibe las soluciones durante inferencia. Después de las respuestas no se modifica el gold: un defecto se registra e invalida para todas las configuraciones, conservando sus datos y el denominador original.

## Memoria, tiempos y trazabilidad

Se mide tiempo nativo total, prefill, decode, tokens de entrada/salida, fin y tiempo de llamada. El calentamiento y la carga se informan por separado. Se conserva toda salida, incluso JSON defectuoso, contradicciones y truncamientos. El plazo técnico es 120 segundos por generación.

La RAM es el pico observado de RSS/working set y bytes privados del worker y sus descendientes, para incluir el lanzador de Python de Windows. Muestreo objetivo 50 ms. Son magnitudes distintas: RSS incluye páginas mapeadas/compartidas y la memoria privada comprometida puede no estar residente. Se registra RAM libre mínima del sistema. Los picos muestreados no son máximos exactos del asignador ni consumo de todo el despliegue.

VRAM se consulta con `nvidia-smi`, durante la carga y aproximadamente cada segundo, además de los límites de cada caso. Se registra el UUID del único adaptador, memoria usada total, temperatura y utilización. Es memoria del dispositivo completo bajo WDDM; el valor previo y su incremento se publican sin atribuirlos exclusivamente al modelo. Otros procesos pueden contribuir. La ruta CPU fija cero capas en GPU, pero la inicialización de plugins de Windows puede crear contexto Vulkan: no se afirmará que toda VRAM observada en CPU pertenece al modelo.

Antes de enviar cada caso se escribe un inicio de intento con fsync. Al recibirlo se conserva RAW con fsync inmediatamente, antes de completar telemetría. Un inicio sin respuesta duradera bloquea reanudación automática, evitando repeticiones invisibles. El proceso propio se puede terminar ante un bloqueo. Se validan cobertura exacta, hashes de modelos, código y runtime. Las salidas de ejecución permanecen separadas en `results_finalists_200_v1/`.

## Métricas y criterio de decisión

1. **Corrección textual:** TP/FP/FN, precisión, recall y F0.5 mediante la evaluación v2 ya existente y ERRANT real. Se publican referencia primaria y mejor referencia completa licenciada, cobertura y omisiones sobre todo el gold. No se crean alternativas a partir de las respuestas. [ERRANT](https://github.com/chrisjbryant/errant).
2. **Acierto por caso:** flag de original correcto y coincidencia con una referencia completa, distinguiendo texto exacto de respuesta utilizable. El éxito completo automático es un proxy de corrección textual/contrato; no certifica la explicación.
3. **Controles:** modificación innecesaria CTMR, falsas alarmas CFAR y preservación literal, con sus denominadores y no observables.
4. **Contrato:** JSON directo/recuperable/esquema, estado del mismo parser C# usado en la app, coherencia de declaraciones, alcance del límite de salida y fallos técnicos. `length` se informa por separado: si el JSON está completo y su contenido es correcto, alcanzar el límite no lo convierte automáticamente en una respuesta incorrecta.
5. **Recursos:** carga, mediana/media/p95 de latencia, tokens/s, RAM y VRAM muestreadas. Se comparan los mismos casos y se informa que las longitudes generadas pueden diferir.

Se calcularán diferencias pareadas entre modelos por backend y entre backends por modelo, con intervalos bootstrap de 95 %, 2000 remuestreos estratificados por nivel/condición y semilla 20261117. Para esos intervalos de F0.5 se usará la referencia primaria con toda edición gold no observable contada como FN; se publicará también su estimación puntual, diferenciada del F0.5 condicional v2. Sus intervalos describen la variación de este conjunto sintético, no representatividad poblacional ni ausencia de sesgo de anotación. También se informará cuánto cambian las respuestas CPU/Vulkan de cada modelo.

Se distinguirá ganador de latencia del mejor resultado textual. F0.5, falsas correcciones, cobertura y utilidad del contrato se consideran juntos. Diferencias inciertas o contrapuestas se describirán como tales. No se declarará precisión humana de las explicaciones. Si los costes de procesamiento resultan cercanos, una muestra común podrá medirse en móviles; una diferencia clara de escritorio no se extrapolará automáticamente a otro SoC. La selección final de producto debe conservar CPU como fallback y permitir al usuario cambiar de modelo.
