# Correspondencia con el plan de titulación y próximos pasos

**Fecha de corte:** 11 de octubre de 2026, America/Guayaquil.

**Naturaleza:** revisión documental y técnica asistida por IA; propuestas para el investigador y su tutor, sin aprobación humana simulada.

**Conclusión:** el trabajo realizado constituye una base sólida de selección local y comparación de cuantizaciones. Todavía no completa la comparación de prompts, la validación humana, el estudio de robustez ni el prototipo que exige el plan. La siguiente prioridad es mejorar la medición y cerrar esos componentes, aprovechando las respuestas existentes.

## 1. Fuentes y comprobaciones

Se leyó el contenido del DOCX aprobado, incluidos objetivos, alcance, metodología, cronograma, presupuesto y bibliografía. Se extrajeron sus párrafos y tablas en orden mediante `zipfile` y XML con el Python del runtime de documentos de Codex. El PDF se conserva como otra presentación del plan; no se verificó por separado su equivalencia con el DOCX. También se leyó la contextualización Markdown completa.

El plan del tutor es la referencia académica principal. El Markdown es una contextualización secundaria: conserva propuestas y estados anteriores que deben contrastarse con los archivos de ejecución. La realidad de una corrida se determina por sus manifiestos, RAW y código, aunque se desvíe de lo previsto; no se reescribe para hacerla coincidir con el plan.

Se contrastaron las fuentes con:

- `documentation/methodology_phase2.md`, `results_phase2.md`, `historical_phase1_results.md`, `experiment_chronology.md` y `annotation_granularity_diagnostic.md`.
- Los benchmarks de 40 y 120, el manifiesto de 16 configuraciones, los resúmenes de ambas corridas, sus índices de fuentes y la auditoría de cierre.
- El evaluador, su rúbrica, el generador de informes y el inventario de archivos del proyecto, excluyendo modelos, herramientas, cachés y contenido del test final.

Comprobaciones nuevas de esta revisión:

| Comprobación | Resultado |
|---|---|
| RAW y parsed de desarrollo | 16 configuraciones × 120 filas en cada representación; IDs completos y únicos |
| RAW y parsed sobre los 40 históricos | 16 × 40 filas en cada representación; IDs completos y únicos |
| SHA de fuentes y derivados de los dos `source_index.json` | 158 registros cotejados; ninguna diferencia |
| Integridad de Fase 1 | `verify_phase1_integrity.py`: 24 artefactos byte-idénticos |
| Fallos/reintentos según los resúmenes de ejecución | 0 fallos de transporte y 0 reintentos en ambas matrices |
| Confirmaciones humanas actuales registradas | 0; las revisiones editoriales disponibles son de IA |

Las filas RAW y parsed representan las mismas respuestas, por lo que **no se suman como observaciones diferentes**. El total de respuestas nuevas es 1.920 + 640 = **2.560**. La auditoría de cierre anterior registra además 23 blobs Git históricos idénticos, 11 activos de runtime verificados, 32 logs de offload CUDA y 2.560 prompts cotejados; no se repitió aquí el hashing de los modelos grandes ni toda esa auditoría de hardware. Las 138 pruebas automáticas documentadas son fixtures/mocks de la entrega anterior; no se reejecutaron para esta revisión documental.

No se realizaron nuevas inferencias, cambios de parámetros, modificaciones del gold ni accesos al test final. Se hicieron dos revisiones independientes de solo lectura, invocadas explícitamente con `gpt-6-luna`, esfuerzo `max` y contexto nuevo. No hubo errores de rate limit observados.

## 2. Correspondencia con objetivos y entregables

| Exigencia del plan aprobado | Evidencia actual | Estado y trabajo pendiente |
|---|---|---|
| OE1: evaluar capacidad inicial, instrucciones, robustez y recursos | Screening histórico de ocho modelos; matrices actuales 120×16 y 40×16; formato, controles, latencia y memoria | Ejecución cubierta; calidad lingüística todavía provisional y robustez no demostrada mediante perturbaciones |
| OE2: comparar prompt simple y system prompt estructurado; few-shot si pertinente | Se utilizó un único system prompt estructurado, común y congelado | Pendiente. Las 2.560 respuestas no constituyen una comparación de estrategias de prompting |
| OE3: construir y validar casos A1/A2, controles, varios errores y ambigüedad | 120 nuevos, 60 por nivel; 90 incorrectos/30 controles; 150 errores/31 categorías; validación estructural y editorial de IA | Construcción técnica cubierta. Falta validación humana y mapa explícito de alternativas/ambigüedad |
| OE4: prototipo local mínimo de Writing | Servidores, launchers y transporte local disponibles | No se encontró evidencia del flujo completo de interfaz: consigna → texto → corrección → ediciones → explicación |
| §8.3: embudo 40 → 120 → aproximadamente 200; uno o dos finalistas | Hay ambos conjuntos de desarrollo/exploración y sus resultados | Selección final pendiente; el test final permanece reservado |
| §8.5: P/R/F0.5 sobre ediciones; ERRANT cuando compatible | Métrica propia de coincidencia literal; diagnóstico posterior de granularidad | Evaluar una medición alineada al texto corregido; no denominar ERRANT a la métrica actual |
| §8.5: rúbrica humana 0–2 en siete criterios | Campos de juicio humano y cola de revisión; sin fichas humanas actuales | Preparar instrumento, muestreo y esquema de datos compatibles con el plan |
| §§6 y 8.4: GPT-4o como referencia externa | No se encontraron resultados de esa comparación en el expediente actual | Mantenerlo en la evaluación prevista, verificar permisos de los textos y documentar la ejecución externa por separado |
| §8.6: baja aleatoriedad o determinismo y subconjunto de robustez | Seed 42; temperaturas por familia; una corrida | Hay una desviación de perfil experimental que documentar y resolver prospectivamente |
| §§8.7 y 9: decisión condicional de LoRA/QLoRA después del segundo avance | No se realizó entrenamiento | Compatible con el plan. No es una deuda obligatoria: decidir después de evaluar prompting |
| §8.9: trazabilidad y separación de datos | SHA, versiones, RAW, registros, Git local, test final sin acceso | Bien cubierto técnicamente; prever copia de respaldo de RAW ignorados por Git |

No asigno un porcentaje global de avance: contar llamadas no permite medir cuánto se ha completado de los objetivos lingüísticos, pedagógicos y de adaptación.

## 3. Qué conviene corregir

### 3.1 Separar calidad lingüística y coincidencia de declaraciones

El evaluador congelado exige que `original` coincida literalmente con el fragmento gold, que `correction` sea una opción licenciada y que aparezca en el texto final. Es una medida reproducible del contrato de anotación, pero puede producir falsos negativos de medición.

Ejemplo documentado: Qwen3.5-4B Q8/A1-E001 declara `meet → meets` y `bring → brings`, mientras el gold usa `art teacher meet → art teacher meets` y `Lina bring → Lina brings`. Las ediciones reconstruyen exactamente el mismo texto, pero el proxy da TP=0, FP=2, FN=2. No corresponde interpretar esos dos FP como dos correcciones lingüísticamente falsas.

**Recomendación:** conservar el evaluador y los informes primarios intactos; crear una versión de evaluación separada que distinga:

1. Corrección del texto: ediciones extraídas entre texto original y texto corregido, comparadas con referencias válidas.
2. Coherencia de declaraciones: los cambios enumerados deben poder localizarse y explicar los cambios realizados, sin exigir idénticos límites de fragmento cuando el efecto es equivalente.
3. Calidad formativa: significado, explicación, nivel y claridad, mediante revisión humana.
4. Formato y funcionamiento: JSON directo/recuperable, esquema, truncamiento y fallos técnicos.

ERRANT es una opción alineada con el plan: extrae y clasifica ediciones entre textos originales y corregidos. Su integración requiere validar segmentación, tokenización, alineación y referencias con ejemplos sintéticos y una muestra revisada. Véanse el [artículo original](https://aclanthology.org/P17-1074/) y el [repositorio del proyecto](https://github.com/chrisjbryant/errant).

No bastaría con quitar la comparación de `original`: también deben verificarse ubicación, realización, correspondencia uno a uno y cambios adicionales. Una coincidencia de texto final tampoco demuestra explicaciones correctas. Las alternativas no listadas requieren adjudicación; no deben aceptarse automáticamente por similitud.

La nueva evaluación de los datos actuales será **post hoc**, porque el problema se identificó al observar outputs. Debe aplicarse uniformemente a todas las configuraciones y publicar su diferencia con la versión congelada. Después podrá fijarse prospectivamente para prompting y test final. Esto permite aprovechar RAW existentes **sin repetir inferencias**.

Las alternativas completas ya autorizadas pueden constituir referencias adicionales. No generar todas las combinaciones de alternativas por error: algunas decisiones pueden interactuar o modificar el significado. Los datos y las referencias congeladas siguen intactos. Un defecto real del caso requiere un registro compartido de invalidación para todos los modelos; una alternativa legítima no convierte automáticamente el caso en inválido.

### 3.2 Completar y asegurar la evaluación humana

El §8.5 especifica siete criterios con notas de 0 a 2: detección, corrección, preservación de significado, adecuación A1/A2, explicación gramatical, claridad pedagógica y tratamiento de textos correctos. La clasificación C/P/I y los dos campos booleanos actuales no sustituyen ese instrumento.

Hay además una discrepancia concreta entre documentación y código: `valid_human()` y `apply_human_override()` en `scripts/evaluate_benchmark_120.py` aceptan veredicto, revisor y justificación sin exigir `meaning_preserved` ni `explanations_ok`, aunque la rúbrica los requiere. Un registro incompleto podría aparecer como confirmado. **Corregir ese contrato antes de importar fichas humanas**, en una versión nueva que preserve los informes ya publicados.

Propuesta de instrumento y procedimiento:

- Vincular cada ficha a dataset SHA, configuración, caso y hash de la respuesta exacta; conservar identidad o código de revisor, fecha, fundamento y siete notas. Usar `no aplica` con reglas explícitas cuando un criterio no corresponda.
- Definir anclas observables para 0/1/2 y juicios explícitos sobre significado y explicaciones. Registrar adjudicaciones de alternativas sin reescribir retrospectivamente el gold.
- Para calibrar desarrollo, empezar con los mismos 60 casos en hasta tres configuraciones: los 30 controles y 30 incorrectos estratificados por nivel, número de errores y alternativas. Serían hasta 180 respuestas revisadas. Es una propuesta de carga de trabajo, no una muestra ya seleccionada o validada.
- Ocultar identidad del modelo y orden de resultados; mezclar la presentación. Separar esa muestra sistemática de una cola adicional de anomalías: la cola prioriza problemas, pero no estima por sí sola la calidad media.
- Si hay un segundo evaluador, revisar una fracción predefinida, por ejemplo 20–25 %, y publicar acuerdo por criterio y desacuerdos antes de adjudicarlos.
- Resolver con trazabilidad los cinco juicios históricos enumerados en el registro estructurado, conservando sus archivos originales; reconciliar además la mención narrativa de seis sin inventar una sexta entrada. No atribuir a esas etiquetas una nueva validación humana que no existe.

La revisión humana del conjunto también debe comprobar que las tareas y la taxonomía corresponden a A1/A2. No exigir una persona por cada una de las 2.560 respuestas para avanzar: el plan pide una muestra, con evaluación detallada de los finalistas.

### 3.3 Cumplir la comparación de prompting y controlar el muestreo

La corrida actual compara configuraciones **bajo el tratamiento B, prompt estructurado**. Es útil, pero no responde cuánto mejora B frente a A ni si C aporta valor. La cuantización tampoco completa por sí sola el objetivo de adaptación mediante instrucciones.

Los perfiles congelados usaron temperatura 0,7 para Qwen, 1,0 para MiniCPM/Gemma y 0,1 para LFM. La semilla permite registrar el muestreo, pero no convierte esa corrida en greedy ni estima variabilidad. Los perfiles de proveedor pueden justificarse como configuraciones prácticas; no satisfacen automáticamente la intención de baja aleatoriedad del §8.6.

Para el siguiente estudio de pocos finalistas, recomiendo fijar un perfil de baja aleatoriedad o greedy técnicamente validado y usarlo igual en A/B/C dentro de cada configuración. Registrar ese cambio como otra condición experimental. Si se conserva muestreo, acotar repeticiones con semillas predefinidas y reportar variación; no escoger la mejor respuesta. No hace falta repetir las 16 configuraciones por este motivo.

Si cambian parámetros, las respuestas B antiguas no pueden actuar como control causal del nuevo A. Ejecutar A/B/C bajo el mismo protocolo nuevo. Si todos los parámetros se conservan, podría reutilizarse B con sus hashes, pero la comparación mantiene la limitación de una única corrida muestreada.

### 3.4 Precisar cobertura y robustez

Las longitudes reales son **23–45 palabras en A1 y 35–59 en A2**. Todas caben en el alcance aproximado 20–100 del tutor. Los límites de construcción 15–60/25–100 no causaron aquí una violación; tampoco hay evidencia sobre textos de más de 60 palabras. No interpretar el grupo vacío `long_>60` como rendimiento perfecto ni como cobertura del extremo de 100 palabras.

Hay 15 casos con alternativas completas de texto (8 A1 y 7 A2) y 26 errores con una corrección licenciada distinta de la primaria (9 A1 y 17 A2). Eso demuestra alternativas, pero no una cuota previamente definida de ambigüedad. Mapear qué casos representan variantes estándar, varias reparaciones válidas o incertidumbre de intención, y revisarlos con una persona. Casos como puntuación final deben interpretarse por su categoría, sin convertirlos en evidencia general de gramática A2.

El §8.6 requiere perturbaciones de robustez. Readiness comprueba funcionamiento, no estabilidad lingüística ante variaciones. Propongo un subestudio acotado de finalistas con 20 casos base balanceados y dos variantes validadas por caso. El tamaño es una propuesta, no una necesidad estadística demostrada. No aplicar transformaciones a ciegas: cambiar mayúsculas, espacios o puntuación puede reparar o introducir justo el error evaluado. Conservar la intención y los errores previstos o anotar las nuevas referencias antes de inferir. Analizar cada grupo de original y variantes como dependiente, sin inflar el N de casos independientes.

### 3.5 Documentar las ampliaciones y los límites de comparación

- El contexto Markdown prevé 14 configuraciones/1.680 inferencias; la ejecución real tuvo **16/1.920**, al añadir LFM2.5-2.6B Q8/Q4 por instrucción del investigador. Es una ampliación del screening de desarrollo compatible con el objetivo, no una especificación original del tutor.
- La nueva matriz común sobre 40 se ejecutó **después** de la matriz de 120. Documentar esa cronología: completa la comparación actual sobre los 40, pero no afirmar que esos resultados nuevos justificaron prospectivamente el paso de todas las configuraciones a 120.
- Los 40 ya se habían usado y no son holdout ni una réplica independiente. Mantener tres expedientes: histórico Transformers, 40 actuales llama.cpp y 120 de desarrollo. No mezclar sus rúbricas ni atribuir diferencias entre fases solo a cuantización.
- Entre familias cambian entrenamiento, plantilla, tamaño y sampling. En Gemma cambian procedencias QAT/dinámicas; no es una prueba aislada QAT frente a PTQ. Las comparaciones dentro de fuente y familia tienen mejor control, con sus propias limitaciones.
- El rendimiento medido es descriptivo de la RTX 3070 en ese escritorio. VRAM fue muestreo del dispositivo completo, TTFT no estuvo disponible por modo no streaming y hubo actividad concurrente. Para finalistas puede hacerse una medición técnica separada más controlada, sin sustituir las salidas de calidad ni llamarla réplica lingüística.
- No demostrar viabilidad móvil a partir del tamaño GGUF o de una GPU de escritorio. El plan hace móvil complementario; basta demostrar el prototipo local en computadora y delimitar las conclusiones al hardware observado.
- RAW nuevos están ignorados por Git. Versionar sus hashes ayuda a verificar, pero no recupera archivos perdidos: acordar un respaldo local separado, verificable y sin publicación externa.

Los documentos antiguos deben citarse con fecha y propósito. `benchmark_120_validation.md` conserva una fotografía de preparación con notas anteriores al cierre; el encabezado actualizado no convierte todas sus frases en estado actual. Esta revisión y los informes de resultados son el punto de entrada para decisiones actuales; no se alteró la contextualización del usuario ni el plan aprobado.

## 4. Diseño recomendado para la etapa siguiente

### Paso A: evaluación y preselección sobre desarrollo

Primero especificar la evaluación nueva, validarla con casos sintéticos y una muestra humana, y reprocesar uniformemente las respuestas existentes en otra carpeta de análisis. Publicar diferencias respecto al proxy original. Comparar por caso, nivel, categoría, múltiples errores, controles, significado, explicación, formato y recursos.

Hay señales para revisar Qwen3.5-4B Q8/Q4 y Gemma Q4: el diagnóstico de texto primario coincide en 62/90 y 61/90 para Qwen, y 72/90 y 70/90 para Gemma oficial/dinámica. Son señales posteriores, no exactitud humana. Gemma oficial también declara falsas alarmas observadas en 14/30 controles pese a CTMR=0; corregir bien el texto no basta para un feedback fiable.

Conservar una opción compacta si la evaluación nueva muestra una relación calidad/recursos competitiva —por ejemplo, Qwen2B o MiniCPM2B Q4—, en lugar de seleccionar solo las filas con proxy más alto. LFM no debe descartarse únicamente por esa métrica sesgada. Gemma UD-Q2 tiene evidencia independiente de problemas de formato (8/120 esquemas válidos), por lo que es candidata a descarte del flujo actual; ello no demuestra incapacidad universal del modelo bajo todo prompting.

Seleccionar **dos o tres configuraciones**, idealmente cubriendo perfiles distintos de calidad y costo, para prompting; finalmente **uno o dos SLM**, como indica el plan. La selección debe justificarse con evidencia de desarrollo y revisión, no con un ranking único.

### Paso B: comparación A/B/C y robustez

- A: instrucción simple y neutral con el contrato de salida necesario para medir la misma tarea.
- B: system prompt estructurado con minimal edit, preservación y restricciones ya definidas.
- C: B más pocos ejemplos fijos y validados, únicamente si el costo de contexto y las señales de desarrollo lo justifican.

Mantener iguales datos de evaluación, artefactos, runtime, límites y generación entre tratamientos de cada configuración. Reservar IDs del desarrollo para ejemplos C y excluirlos de la evaluación de **todos** los tratamientos; no presentar el propio caso evaluado como demostración. Documentar el N común restante. Una alternativa es crear demostraciones de desarrollo separadas, sin usar el test final.

Fijar antes de generar los criterios de elección: validez de correcciones y falsas correcciones, significado y explicación, A1/A2, cumplimiento/recuperabilidad, truncamiento y recursos. No cambiar gold, presupuesto o prompt durante una corrida por una respuesta mala.

Para comparaciones pareadas, reportar diferencias por texto e intervalos de incertidumbre. Si se utiliza bootstrap, remuestrear IDs comunes a todas las condiciones y recalcular los agregados; agrupar variantes de robustez por caso base. Una muestra sintética controlada no se vuelve representativa de estudiantes reales por calcular un intervalo. Evitar pruebas masivas para buscar significación y afirmaciones causales entre familias.

### Paso C: cierre, referencia externa y prototipo

Después del segundo avance, registrar la decisión LoRA/QLoRA con las condiciones del §8.7. No iniciar entrenamiento para justificar el título: el plan reconoce prompting como adaptación y permite no entrenar. Solo si se activa esa fase, finalizarla antes del congelamiento definitivo y usar datos de entrenamiento separados.

Antes del test final, fijar modelo, cuantización, prompt/demos, parámetros, versión de parser/evaluador, referencias, reglas de invalidación, muestra humana y comparaciones previstas. El test final y su construcción siguen reservados a la etapa y autorización correspondientes; esta revisión no los crea ni consulta.

GPT-4o figura en el plan como referencia externa de mayor capacidad, no como gold ni revisor humano. Comprobar disponibilidad del modelo/versionado, permisos de los casos y presupuesto antes de ejecutar; registrar llamadas y costos. Si hiciera falta sustituir esa referencia por otra, documentar y consultar el cambio con el tutor, sin sustitución silenciosa.

El prototipo mínimo puede avanzar en paralelo una vez elegido el formato de integración: consigna, texto, inferencia local, texto corregido, cambios y explicación. Añadir manejo comprensible de salida inválida y trazabilidad. Si se usan grammar/schema o reintentos para el producto, evaluarlos como una condición de despliegue separada del benchmark sin restricciones. No presentar el prototipo como prueba de aprendizaje del estudiante: el estudio mide calidad de feedback, no una mejora educativa longitudinal.

## 5. Cronograma propuesto dentro del aprobado

Este calendario es una propuesta de organización, no una modificación de los hitos institucionales ni una garantía de duración. La disponibilidad de una persona que revise inglés es la dependencia principal.

| Ventana | Trabajo prioritario | Evidencia de salida |
|---|---|---|
| 11–16 octubre | Cerrar el mapa plan→evidencia; especificar evaluación v2 y ficha humana; preparar coordinación de revisión | Primer avance del **16-oct**: protocolo, piloto, runtimes, corridas realizadas, ampliaciones y límites explícitos |
| 17–25 octubre | Validar evaluación y muestra humana inicial; reprocesar RAW existentes; preseleccionar 2–3 configuraciones | Análisis pareado de desarrollo, adjudicaciones y lista justificada de candidatos |
| 26 octubre–5 noviembre | Comparar A/B y C si procede; robustez acotada; elegir uno o dos finalistas | Segundo avance del **6-nov**: comparación de prompts, finalistas y protocolo de cierre |
| 7–20 noviembre | Decidir LoRA/QLoRA después del segundo avance; congelamiento definitivo; etapa final/GPT-4o/revisión humana cuando autorizada; prototipo en paralelo | Registro de decisión, configuración congelada, evaluación final independiente y demostración local |
| 21 noviembre–4 diciembre | Análisis, límites, figuras, anexos, redacción e integración del prototipo | Documento completo y reproducible para **5-dic**, tercer avance/100 % |
| 6–14 diciembre y posterior | Correcciones de lectores y preparación de sustentación | Atención a rúbricas hasta **14-dic**; sustentación **4–8 ene-2027** |

Si se activa LoRA después del 6 de noviembre, el congelamiento definitivo debe ocurrir después de ese experimento y antes del test. No fijar un freeze ficticio el 6 de noviembre y luego ajustar sobre resultados finales. Si entrenamiento amenaza el margen de redacción, continuar con prompting y documentar esa decisión.

## 6. Cambios compatibles y cambios que requieren acordar el alcance

Son refinamientos compatibles: evaluación v2 trazada, ERRANT cuando adecuado, rúbrica 0–2, revisión humana de muestra, pocos finalistas, comparación de prompts, robustez, controles CTMR/CFAR, diferenciación de formato y calidad, registro de la ampliación a LFM2.6, prototipo local y decisión de no hacer fine-tuning.

Conviene acordar expresamente con el tutor cambios que eliminen un componente aprobado: omitir la comparación de prompt simple y estructurado, omitir evaluación humana, suprimir la referencia GPT-4o o reemplazarla, retirar el test independiente o cambiar el objetivo a un tutor integral. Aplicación móvil completa, usuarios, gamificación y estudio longitudinal no son necesarios para cumplir este plan.

**Siguiente acción recomendada:** especificar y validar el instrumento de evaluación y el contrato humano, conservar la evaluación original, y analizar nuevamente los RAW de desarrollo con una versión explícita. Después seleccionar candidatos para prompting. La prioridad inmediata es producir una medición defendible, no incrementar el número de modelos o de llamadas.

## 7. Huellas de documentos de entrada

| Archivo en la raíz del repositorio | SHA256 leído |
|---|---|
| `PlanTrabajoTitulación_KevinLima-rev1.docx` | `f69838aae2086b5ccd5f4f136ed3f6f04b874edf84af0905f73a6407a5f1b337` |
| `PlanTrabajoTitulación_KevinLima-rev1.pdf` | `b9f6294d1fdf26038f042226e8b9cf107fb2221c36da12525505aecafe7364ab` |
| `PROJECT_CONTEXT_TITULACION_SLM_A1A2.md` | `2b8b7dc7d53ed80170029e40848389bea3b676beff650b1d353a553b29bcc01b` |

Benchmark120: `07308427c02adcc056a8964d3e4da41615db4b7fc0101870e277097de46d59f9`. Benchmark40: `a271c2ee84839aff21cd923a9ec7d22450c34b4003cace8233b0a128f8edbfe9`. Manifiesto ejecutado: `8e62d01164a86a63a3b9b16da0aacbbc365176bdd44fb76e0acfb04da249e255`. Estado Git de entrada: `feb818d`; únicamente los tres documentos aportados por el usuario estaban sin seguimiento. Los documentos de entrada y los resultados congelados se preservan sin cambios.
