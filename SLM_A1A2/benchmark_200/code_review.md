# Revisión del ejecutor y evaluador de finalistas

17 de noviembre de 2026. Revisión estática por un agente Sol 6.1, razonamiento high, separado del autor del código. Se hizo antes de generar respuestas del conjunto de 200. La revisión lingüística corresponde a otros archivos. No constituye una revisión humana.

Se revisaron `run_finalists_200.py`, `scripts/prepare_finalists_200.py`, `scripts/analyze_finalists_200.py`, el parser de lote y su correspondencia con el ABI 2 del puente nativo. La firma ctypes y la convención cdecl se cotejaron con el encabezado C. El worker recibe prompts de sistema/usuario y no carga referencias gold.

Hallazgos y resolución antes de congelar:

- Un proceso interrumpido podía repetir un caso sin declarar un segundo intento. Se añadió un journal con fsync previo al envío y rechazo de intentos iniciados sin RAW duradero. El RAW se persiste antes de consultar telemetría final.
- Un orden incompleto o duplicado podía producir una finalización falsa. Se exige una permutación exacta de los 200 IDs, cuatro configuraciones distintas y cobertura completa por configuración.
- La VRAM podía corresponder a un adaptador diferente. El experimento exige un único adaptador, conserva su UUID/PCI y comprueba el PCI y offload completo en el log nativo de Vulkan. Los valores siguen siendo del dispositivo completo.
- Se perdían temperatura y utilización observadas. Ahora se conservan muestras por caso. El protocolo declara la limitación temporal de ejecutar por bloques.
- El análisis podía usar código o readiness de otra identidad. Verifica los hashes congelados de runtime/evaluadores/parser, versiones de ERRANT y los SHA del manifiesto de cada readiness. Comprueba las fuentes de nuevo antes de publicar.
- El parser de lote podía mezclar estados de otra respuesta. Sus filas incluyen SHA de RAW, texto original, manifiesto y ensamblado ejecutado; se cotejan al analizar.
- Una interrupción después del RAW podía perder memoria. La reanudación conserva la respuesta y registra explícitamente la medición no observable, sin volver a inferir. El informe incluye cobertura de memoria.
- Las métricas podían fallar si no había ningún texto observable o dejar un informe parcial. Se admiten métricas nulas y se publica el conjunto de análisis mediante staging y rename al terminar.

La última revisión estática no encontró bloqueos adicionales. También se detectó durante la sonda técnica que Windows mantiene un lanzador de Python separado del proceso nativo; la RAM pasó a medirse sobre el árbol del worker. La terminación por plazo abarca sus descendientes.

Se prepararon ocho comprobaciones sintéticas de seguridad, sin pesos ni preguntas del conjunto: cobertura, identidad de configuración/modelo, exclusión de gold, journal incompleto, RAW previo a telemetría, ausencia de reintentos por JSON, conservación ante fallo técnico y recuperación de telemetría perdida. Las ocho pasaron. Se comprobó el parser C# con un control válido y JSON truncado, y ERRANT con una edición conocida. Un fixture del bootstrap reprodujo diferencia F0.5=1 y razón de latencias=2. Los logs locales están en `logs/finalists_200_20261117/`.
