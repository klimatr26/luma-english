# Prototipo local de Writing y revisión del investigador

## Alcance y decisión del tutor

El 16 de octubre de 2026, el investigador comunicó que el tutor indicó realizar personalmente la revisión de respuestas, sin solicitarla al área de idiomas, priorizando la demostración tecnológica. Se registra como decisión comunicada por el investigador, sin atribuir una aprobación adicional ni reescribir el plan aprobado. La revisión humana todavía no se ha realizado y no se fabricaron notas.

La página de revisión v2 continúa siendo utilizable por el investigador con su identificador y fundamento. Los juicios deben describirse como **revisión del investigador**, sin presentarlos como validación lingüística externa, revisión ciega por especialista o acuerdo entre evaluadores. El conocimiento previo de los resultados limita la independencia del revisor, aunque las fichas oculten los modelos. La asignación de 45 fichas para un segundo evaluador permanece como propuesta no ejecutada; no se reportará acuerdo interevaluador si solo revisa una persona. Una segunda lectura propia podría documentarse como revisión repetida, no como segundo evaluador independiente.

Se conserva el foco tecnológico y el alcance de Writing A1/A2. El prototipo implementa el objetivo de integración local del plan; no reemplaza las comparaciones de prompts o pruebas posteriores previstas. Los resultados del desarrollo siguen siendo provisionales en las dimensiones semánticas y pedagógicas pendientes de revisión.

## Implementación

Se creó `SLM_A1A2/demo/`, con Windows Forms/.NET 10 y un núcleo C# sin dependencias de terceros. Se reutilizan los modelos descargados y llama.cpp b11457. Los tres perfiles preseleccionados (Qwen3.5-4B, MiniCPM5-2B y Gemma E2B) y las dos familias LFM2.5 se exponen con 13 variantes de precisión/cuantización.

El programa carga un solo modelo, verifica los activos y muestra ejercicio, respuesta libre o ejemplo seleccionable, interpretación estructurada, correcciones, explicaciones y JSON original. Los cuatro ejercicios A1/A2 se escribieron para la demostración. No se usan los casos de 40/120 para generar ejercicios ni se accede al test final; solo se obtiene el system prompt canónico del documento histórico. El ejemplo alternativo, su supuesta corrección y cualquier referencia no se envían al modelo.

El resultado visual proviene del booleano generado. El parser comprueba estructura y coherencia interna, sin decidir verdad lingüística. Por ejemplo, `is_correct=true` con texto cambiado o errores declarados produce una advertencia, y no una marca verde. Un JSON recuperado se distingue de uno estricto. El comportamiento no se cambia según la calidad de cada salida.

Las descargas conservan fuentes fijadas, tamaño y SHA-256; Qwen conserva su receta de conversión local en vez de sustituirlo por un GGUF de otro proveedor. No se descargaron ni reconvirtieron los pesos existentes como parte de esta entrega. La adquisición y la preparación de faltantes tienen pruebas sintéticas; una restauración remota completa de varios gigabytes no se presenta como ejecutada si no se realizó.

El proceso servidor se inicia en loopback, sin consola visible, y se libera al cambiar o cerrar el modelo. El programa no termina procesos ajenos. La cancelación y los errores se presentan sin reintentar una generación ni cambiar de cuantización silenciosamente. Se preserva thinking desactivado según los controles del runtime y la plantilla nativa.

## Evidencia y reproducibilidad

Las sesiones se guardan en `SLM_A1A2/logs/writing_demo/`, separadas de RAW/resultados de 40/120 y de las fichas humanas. Incluyen modelo/hash, consigna, texto, tipo de entrada, parámetros, respuesta API, fin de generación, tiempo e interpretación. El token opcional de descarga no forma parte del registro. Los binarios de compilación, modelos y sesiones quedan fuera de Git; se conservan el código y los informes pequeños.

La guía de uso y los comandos están en [`demo/README.md`](../demo/README.md). El registro `demo/verification_20261016.json` recoge las comprobaciones de esta entrega, los resultados observados de demostración y sus límites. Estas interacciones son pruebas funcionales del prototipo, no una estimación de precisión ni una ampliación de los benchmarks.

## Resultados funcionales observados

Se ejecutaron diez interacciones secuenciales: un ejemplo A1 correcto y otro con `I wakes` en cada una de cinco configuraciones Q4. Se usaron los parámetros preservados y no se ajustaron por estas respuestas.

| Configuración | Ejemplo correcto | Ejemplo con error | Comportamiento visible |
|---|---|---|---|
| Qwen3.5-4B Q4_K_M | JSON estricto, `true` | JSON estricto, `false` | Marca verde o cruz, con el juicio del modelo |
| MiniCPM5-2B Q4_K_M | JSON estricto, `true` | JSON estricto, `false` | Interpretación directa |
| Gemma E2B UD-Q4_K_XL | JSON recuperado, `true` | JSON recuperado, `false` | Advertencia de envoltura; contenido interpretable |
| LFM2.5-1.2B Q4_K_M | Incoherente, `true` | Incoherente, `true` | Cambió el texto aunque afirmó que era correcto: advertencia, sin aprobación verde |
| LFM2.5-2.6B Q4_K_M | JSON recuperado, `false` | JSON recuperado, `false` | Inventó una preferencia por `have breakfast` frente a `eat breakfast`; el contrato no detecta por sí solo este error lingüístico |

El ejemplo correcto de Qwen dejó `feedback` vacío en una interacción de la ventana. La interfaz identifica la ausencia de comentarios sin inventar retroalimentación, y el RAW mantiene la cadena vacía. La prueba con error sí mostró la corrección `wakes → wake` y su explicación. Las comprobaciones adicionales de la ventana quedan identificadas por sus sesiones locales; no se suman a estas diez como si fueran una nueva muestra de calidad.

Estos resultados permiten demostrar el motor local, el parser y sus límites. La validación estructural no detecta una explicación falsa como la observada en LFM2.6; por eso el programa atribuye la marca al modelo y conserva la salida completa para revisión.

Pasaron las tres suites C# (parser/ejercicios, adquisición y runtime), incluidas siete comprobaciones del runtime con HTTP simulado, y ocho pruebas Python del preparador Qwen. Se verificaron compilación Release sin advertencias, tamaño/hash de los modelos efectivamente cargados, recuperación de JSON envuelto, detección de duplicados/contradicciones, protección frente a reemplazos de archivos, manejo de 429 sin retry y retirada de credenciales en redirects. Las descargas grandes y la reconversión no se ejecutaron: ya estaban los pesos requeridos.

La revisión de la ventana comprobó ejemplos seleccionables, evaluación real, cambio de respuesta que limpia resultados, pestaña del JSON, cierre que libera el servidor propio y cierre durante la verificación de un modelo. Se corrigieron etiquetas y recortes de estado, el reparto de columnas de ediciones y una carrera de cierre esperando a que termine la operación cancelada. Se conservaron los 24 artefactos protegidos de Fase 1, los 93 archivos originales comparados con su commit de referencia, 164 hashes de fuentes y 76 derivados v2. No se modificaron resultados ni se registraron notas humanas.
