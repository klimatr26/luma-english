# Evaluación v2: resultados, preselección y revisión humana

Fecha de corte: 11 de octubre de 2026. Versión `evaluation-v2.0`. **Análisis posterior de desarrollo**, no resultado de test final ni validación humana de feedback.

## Qué se hizo y por qué

Se reprocesaron las 2.560 respuestas ya recogidas: 120×16 y 40×16. Se conservaron intactos los benchmarks, RAW, parsed, evaluador original y sus puntuaciones. Las nuevas salidas están en `analysis_v2/`, con fuentes, código, dependencias y protocolo ligados por SHA. No hubo nuevas generaciones de SLM ni acceso al test final.

La evaluación original comparaba literalmente `original` y `correction` con los fragmentos del gold. Esa regla penalizaba reparaciones válidas que expresaban el mismo cambio con límites diferentes. V2 separa ediciones del texto, coherencia de declaraciones, flags/controles, formato y calidad humana. La revisión de la métrica se hizo después de ver outputs y así se registra; no se presenta como prerregistro.

ERRANT 3.0.2, spaCy 3.8.7 y `en_core_web_sm` 3.8.0 se instalaron en `.venv_eval_v2`, con Python 3.12.14 y un lock completo de dependencias con hashes. No se modificó la `.venv` de inferencia. Se verificó reinstalación del lock y compatibilidad. El protocolo, instalación y correspondencias están en [evaluation_v2_protocol.md](evaluation_v2_protocol.md) y [errant_integration_v2.md](errant_integration_v2.md).

## Evidencia del problema y su reparación

En Qwen3.5-4B Q8/A1-E001, la salida declara `meet → meets` y `bring → brings`. El gold usa fragmentos más largos. La evaluación original daba TP=0, FP=2, FN=2 e `INCORRECT`. V2 reconoce TP=2, FP=0, FN=0 con ERRANT, y la reconstrucción de las dos declaraciones coincide exactamente con el texto esperado. La explicación y el significado siguen sin confirmación humana; el ejemplo demuestra la reparación de la medición, no una certificación pedagógica.

La referencia primaria de los 120 contiene **163 ediciones ERRANT**, frente a 150 errores intencionales anotados. Son unidades diferentes: el alineador puede separar o agrupar cambios de una reparación. No se sustituyó el denominador por 150 artificialmente. Las 31 categorías intencionales también se mantienen diferenciadas de la taxonomía ERRANT.

## Resultados completos y lectura correcta

- [Informe de desarrollo 120](../analysis_v2/results_120/reports/scope_report.md), [tabla CSV](../analysis_v2/results_120/configuration_summary.csv) y [subgrupos](../analysis_v2/results_120/reports/subgroup_summary.csv).
- [Informe común de 40](../analysis_v2/results_40_current_16/reports/scope_report.md) y [tabla CSV](../analysis_v2/results_40_current_16/configuration_summary.csv).
- Cada configuración conserva sus filas individuales, ediciones de hipótesis/referencias y puntuaciones por referencia completa bajo `analysis_v2/<scope>/configurations/`.

F0.5 textual se agrega sobre los casos incorrectos con texto corregido observable; se publica siempre su cobertura. Una salida sin texto recuperable no recibe un texto de reemplazo. El recall adicional sobre todas las ediciones gold cuenta esas respuestas como omisiones por convención explícita. Formato, clasificación `is_correct`, declaraciones y controles siguen siendo medidas separadas. El mejor resultado entre referencias completas licenciadas se muestra como resultado complementario; no se inventan referencias combinando alternativas por error.

No comparar automáticamente el F0.5 original con el nuevo como si fuera una mejora del modelo: **se modificó el instrumento de medición, no la respuesta del modelo**. Las discrepancias restantes pueden ser variantes válidas no listadas, cambios de estilo, diferencias de alineación o errores reales; requieren adjudicación. Las explicaciones nunca se validan por exact match.

## Preselección propuesta para revisión humana

La preselección cubre tres perfiles, con los mismos 60 casos de revisión en cada uno. No es un ganador definitivo ni una elección basada en el test final.

| Configuración | F0.5 textual primario condicional | Texto observable incorrectos | CFAR observado /30 | CTMR observado /30 | Esquema válido /120 | JSON estricto /120 | Mediana API observada | GGUF registrado |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Qwen3.5-4B Q4_K_M (11) | 0.8344 | 86/90 | 5 | 2 | 114 | 114 | 2.001 s | 2.709 GB |
| Gemma E2B UD-Q4_K_XL (13) | 0.8730 | 90/90 | 7 | 0 | 116 | 19 | 1.047 s | 2.620 GB |
| MiniCPM5-2B Q4_K_M (06) | 0.7682 | 88/90 | 3 | 2 | 116 | 116 | 0.842 s | 1.561 GB |

Los tres tienen cero controles no observables para CTMR y CFAR bajo la definición v2; se muestran conteos, no solo tasas. `GB` es decimal y describe tamaño de archivo, no consumo total de despliegue. Latencias son las observadas en la corrida original compartida, no una medición aislada nueva.

- **Qwen4B Q4:** buen equilibrio entre corrección textual, flags y estructura. Qwen4B Q8 permanece como contraste de mayor precisión: F0.5=0.8532, 88/90 observables, CFAR=4/30, mediana 2.560 s y GGUF 4.482 GB. Se propone Q4 para esta muestra limitada por su menor tamaño y perfil de recursos; no se declara equivalencia estadística ni inferioridad universal de Q8.
- **Gemma UD-Q4:** corrección textual alta y cobertura completa. Frente al oficial QAT Q4_0, que obtiene F0.5=0.8773, presenta menos falsas alarmas observadas en controles (7 frente a 14). Su contrato estricto es una debilidad marcada: 19/120, con muchas respuestas recuperables tras cercas. El oficial tiene 93/120 estrictas y 120/120 esquemas válidos. La revisión debe valorar esas diferencias; no atribuirlas únicamente a un formato de bits.
- **MiniCPM Q4:** opción compacta con menos falsas alarmas observadas, formato generalmente usable y latencia menor en esta corrida. Hay menor corrección textual y el flag es correcto en 72/90 incorrectos, frente a 85/90 de Qwen4 Q4 y 88/90 de Gemma UD-Q4. Es precisamente un candidato para estudiar el compromiso recursos/feedback, no una recomendación de uso autónomo.

Estos datos sostienen una lista provisional para revisión, no una frontera Pareto de calidad humana ya demostrada. La muestra de 60 incluye todos los controles y la mitad de los incorrectos: no calcular una calidad poblacional global mediante promedio bruto sin atender a los estratos y denominadores.

## Configuraciones que siguen en el análisis, sin pasar a estas fichas

LFM1.2 obtiene F0.5 textual aproximado 0.762–0.781 y cobertura 90/90: el antiguo proxy ocultaba buena parte de su corrección. Sin embargo, `is_correct` solo es correcto en 1–3 de los 90 textos incorrectos, y muchas declaraciones no reconstruyen el texto que devuelve. Son fallos de instrucciones relevantes para la tarea completa de feedback. No se descarta la familia por el antiguo F0.5 ni se afirma que nunca pueda mejorar con prompting.

LFM2.6 Q8 tiene F0.5=0.8394 en 84/90 observables; Q4, 0.8159 en 85/90. El recall sobre todo el gold primario es 0.7117/0.7669. Sus controles registran 11/25 falsas alarmas de 30, con un control no observable por configuración. Las respuestas permanecen recuperables en gran parte, pero ambas tienen JSON estricto 0. Se conservan sus resultados completos de 40 y 120; estos problemas justifican no incluirlas en la primera muestra limitada de tres configuraciones.

MiniCPM F16/Q8 ilustran la importancia de cobertura: Q8 obtiene F0.5 condicional 0.8205, pero solo 67/90 textos incorrectos observables y recall sobre todo el gold 0.5215. No debe ascender por esa cifra condicional ignorando las salidas restantes. Gemma UD-Q2 tiene 23/90 textos observables, 8/120 esquemas válidos y recall total 0.1902; la dificultad de servicio sigue siendo clara aunque su F0.5 condicional no sea cero.

Las diferencias entre familias incluyen arquitectura, entrenamiento, plantilla y sampling. Una semilla no estima variación entre corridas. Las diferencias pequeñas entre cuantizaciones no demuestran superioridad general sin revisión y análisis pareado. Los 40 reutilizados siguen siendo exploratorios y se analizan separados de los 120.

## Precisión de los nombres Gemma

Una inspección independiente de los tres headers GGUF, sin recalcular el hash de pesos ni ejecutar inferencia, confirmó los histogramas del manifiesto y tamaños estables. Las etiquetas comerciales no describen formatos uniformes:

| Artefacto | Tipos de tensor observados, conteo |
|---|---|
| Google QAT Q4_0 | F32 263; F16 1; Q6_K 2; Q4_0 275 |
| Unsloth UD-Q4_K_XL | F32 263; Q4_0 278 |
| Unsloth UD-Q2_K_XL | F32 263; F16 1; Q4_0 146; TQ2_0 61; Q8_0 70 |

Cada archivo contiene 541 tensores. No llamar a UD-Q4 una cuantización uniforme Q4_K ni a UD-Q2 una uniforme Q2_K por el nombre del archivo. Los conteos de tensores no ponderan su número de parámetros. La receta del proveedor y el origen QAT son asuntos distintos; la comparación no aísla causalmente QAT frente a PTQ. Registro: `manifests/gemma_tensor_type_verification_v2.json`, que distingue el hash previamente registrado de la lectura nueva de headers.

## Fichas y coordinación humana

Se prepararon **180 fichas sin notas**: 60 mismos casos × tres configuraciones. Los 60 son 30 controles y 30 incorrectos, con 15 de cada condición por nivel. Los incorrectos se seleccionaron por nivel y número de errores con cuotas 8/4/2/1, considerando alternativas completas y semilla 20261011, sin mirar calidad de salidas.

Material para entregar al revisor: únicamente `analysis_v2/human_review_development60/reviewer_materials/`:

- `human_review_rubric_v2.md`: siete criterios 0–2/NA y reglas de juicio.
- `review_cards.md` y `blind_packet.json`: nivel visible, consigna, texto y respuesta íntegra; sin modelo, configuración, case ID, gold ni scores visibles.
- `blank_reviews.jsonl`: plantilla vacía para completar y guardar en una copia aparte.
- `second_reviewer_plan.json`: propuesta de 45 revisiones dobles, 25 % de las fichas, sobre 15 mismos casos base en las tres configuraciones, semilla 20261012. No hay segundo revisor asignado ni juicios simulados.

`coordinator_only/` contiene el plan de casos y crosswalk. No se entrega esa carpeta al evaluador durante el ciego. Se conservan hashes del texto de respuesta y del contexto visible para evitar vincular una nota a otro caso. El material íntegro puede revelar espontáneamente una identidad si el propio modelo la menciona; no se cambia el RAW para ocultarlo y se registra una posible ruptura del ciego.

El revisor decide explícitamente `response_assessable`. JSON inválido no implica automáticamente contenido lingüístico imposible de evaluar. Las fichas no evaluables usan NA y no pueden convertirse en `CORRECT`. Los registros completos exigen siete notas, dos juicios explícitos, revisor, fecha, fundamento y SHA exactos; notas contradictorias con el veredicto se rechazan. Las fichas vacías también se rechazan al importar. No se verifican lingüísticamente los juicios de una persona mediante un algoritmo: el contrato verifica estructura y trazabilidad.

La vía de importación es `prepare_human_review_v2.py import`, que guarda una capa separada por revisión. **No usar la vía humana del evaluador primario congelado**: conserva su contrato histórico más débil para reproducibilidad. V2 incorpora el contrato corregido en su interfaz nueva. No se modifica automáticamente un caso o todos los modelos por una opinión `INVALID_CASE`; esa opinión requiere adjudicación e invalidación compartida.

## Verificación y límites pendientes

La suite final pasó **179 pruebas** desde la `.venv` original; una de ellas es el wrapper que ejecuta y exige las **10 fixtures ERRANT reales** en el entorno aislado. Las demás nuevas verifican equivalencia de fragmentos, ubicación, solapamientos, ausencia de texto, cobertura, referencias completas, identidad de tentativas y registros humanos. Las pruebas son sintéticas/mocks, no inferencias de benchmark.

La auditoría reprodujo los agregados a partir de todas las filas, verificó 76 hashes de derivados y cotejó **93 entradas originales contra los bytes del commit local `feb818d`**. Los RAW/parsed ignorados por Git se verificaron contra los índices originales preservados en ese commit. Los 24 artefactos protegidos de Fase 1 siguen intactos. Hubo cero confirmaciones humanas y cero inferencias nuevas. Registro: `manifests/evaluation_v2_audit_20261011.json`.

Se conservó un render inicial de los informes bajo `reports_initial/`, junto al código que lo produjo, y se corrigió una cadena de comando PowerShell que emitía un aviso de escape de Python. Los informes canónicos en `reports/` son los posteriores a esa reparación cosmética; las métricas y filas v2 no se recalcularon ni cambiaron por ella.

La revisión de significado, explicaciones y alternativas aún depende de evaluadores reales. La preselección puede cambiar tras esa revisión. El siguiente experimento de prompts requerirá condiciones prospectivas iguales entre tratamientos; no se ejecutó aquí. La configuración final y el test independiente permanecen para una etapa posterior.

## Comandos y repetición de análisis

Desde `SLM_A1A2`, los comandos que produjeron esta entrega fueron:

```powershell
.\.venv_eval_v2\Scripts\python.exe scripts/evaluate_responses_v2.py --scope results_120
.\.venv_eval_v2\Scripts\python.exe scripts/evaluate_responses_v2.py --scope results_40_current_16
.\.venv\Scripts\python.exe scripts/report_evaluation_v2.py --scope results_120
.\.venv\Scripts\python.exe scripts/report_evaluation_v2.py --scope results_40_current_16
.\.venv\Scripts\python.exe scripts/prepare_human_review_v2.py packet --configs 06-minicpm5-2b-q4-k-m 11-qwen35-4b-q4-k-m 13-gemma4-e2b-ud-q4-k-xl
.\.venv\Scripts\python.exe scripts/audit_evaluation_v2.py
.\.venv\Scripts\python.exe -m unittest discover -s scripts -p "test_*.py" -v
```

Los generadores rechazan sobrescribir análisis/fichas existentes. Para otra entrega se prepara una versión o copia de trabajo explícita, conservando esta. Auditar sí es read-only de resultados y puede volver a ejecutarse. No es necesario regenerar RAW.

Ejemplo de importación **cuando existan revisiones humanas completas**, no ejecutado en esta entrega:

```powershell
.\.venv\Scripts\python.exe scripts/prepare_human_review_v2.py import --scope results_120 --reviews RUTA_REVISIONES_COMPLETADAS.jsonl --output-name revision_docente_01 --crosswalk analysis_v2/human_review_development60/coordinator_only/identity_crosswalk.json
```

No rellenar identidades, notas o aprobaciones con IA. Una capa humana aceptada sigue identificando sus revisores y discrepancias; no reemplaza silenciosamente la evaluación automática ni la adjudicación compartida.
