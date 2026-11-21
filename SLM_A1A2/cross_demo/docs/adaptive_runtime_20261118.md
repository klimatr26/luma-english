# Reparto CPU/GPU y calibración compartida — 0.1.6

18 de noviembre de 2026, hora de Ecuador continental. Implementación del siguiente paso propuesto en la [integración del portátil](../../documentation/laptop_results_integration_20261118.md). El núcleo queda disponible para reutilizarlo en la aplicación final del curso. Esta entrega mantiene los ejercicios de demostración actuales.

## Cambio de comportamiento

Windows y Android ARM64/API 28+ usan la misma política de estimación, comparación y perfiles. Antes el puente de la aplicación solo admitía CPU o descarga completa; ahora puede seleccionar una GPU concreta y una cantidad explícita de capas. Los intentos viven en procesos distintos, lo que permite retirar un dispositivo lógico fallido antes del siguiente candidato.

**Auto** consulta las GPU y estima pesos, contexto y buffers para el modelo real, a contexto fijo. Utiliza las API públicas `common_fit_params` y `common_fit_measure` de llama.cpp b12359. Se vuelve a medir sin asignación la distribución exacta por capas, sin adoptar las posibles anulaciones de tensores del ajuste inicial. No se reduce contexto ni cambia el sampling para hacer caber el modelo. La reserva de GPU es el mayor entre 256 MiB y un doceavo de la capacidad anunciada por el backend. Es un margen de ingeniería, no una garantía de carga.

El valor automático negativo que conserva el estimador cuando ya cabe todo se interpreta como todas las capas antes de medir. La comprobación técnica detectó y corrigió esta distinción. No existe un umbral excluyente de 4 GiB ni una lista de teléfonos. Una integrada sigue siendo candidata: el tipo discreto solo da prioridad inicial al ordenar la búsqueda, sin decidir el ganador.

La comparación ejecuta un calentamiento y tres muestras sintéticas por backend completado. Usa el prompt de producción, contexto solicitado, gramática, sampling y semilla 42. El calentamiento se conserva y se excluye de la mediana. Vulkan necesita tres respuestas completas utilizables según el parser y una mejora de al menos 1,15 en la razón CPU/Vulkan. Si CPU no completa técnicamente, puede elegirse una ruta GPU con las tres muestras válidas. No se puntúa la corrección lingüística para elegir backend ni se modifica el prompt según esas salidas.

Se prueban como máximo tres candidatos GPU. Tras un fallo se permite un candidato con una capa menos para ese adaptador, en un proceso nuevo; otro adaptador sigue pudiendo participar. La calibración tiene diez minutos de presupuesto total. Al agotarlo se conserva la mejor distribución ya comprobada; no se repite una respuesta real del estudiante. Carga y generación tienen límites técnicos propios y cancelación mediante cierre del worker.

**CPU** omite sonda Vulkan y calibración. **Vulkan manual** conserva la elección de GPU, usa la estimación y permite recuperación de carga parcial acotada; no compara velocidad con CPU ni cae silenciosamente a CPU. Auto sí puede seleccionar CPU y explica el motivo. Si una evaluación real falla en Vulkan, se libera el worker, se archiva el perfil fallido y se pide recargar o elegir CPU. Esa respuesta no se reintenta automáticamente.

## Perfiles, interfaz y modelos

Los perfiles vinculan SHA del modelo, prompt, sampling, contexto, archivos del runtime/worker, controlador, dispositivo anfitrión, hilos y estado de alimentación/ahorro. Windows consulta `GetSystemPowerStatus`; Android lee el Intent de batería existente sin registrar un receptor persistente. [Referencia Android](https://developer.android.com/training/monitoring-device-state/battery-monitoring).

Antes de reutilizar una distribución se consulta de nuevo el presupuesto. Si ya no cabe, se recalibra. Una mejora importante de las capas estimadas también permite recalibrar; un cambio de unos pocos bytes no lo exige. Un perfil CPU que procede de fallos técnicos caduca a los cinco minutos, evitando convertir un fallo transitorio en exclusión permanente de GPU. Si cambia la alimentación durante la comparación, se usa CPU temporalmente y no se guarda esa comparación como perfil reutilizable. Los perfiles anteriores y fallidos se archivan; los RAW de calibración se conservan en archivos separados.

Windows guarda perfiles y logs bajo `%LOCALAPPDATA%/WritingApp/`; Android usa sus archivos privados. Los modelos y sesiones previos no se borran. La interfaz explica la demora inicial, permite cancelar y muestra GPU física y capas confirmadas, por ejemplo `32/33`. El conteo procede del resumen de carga del runtime; no significa que todos los tensores y operaciones residan en GPU.

La sugerencia inicial por capacidad es **Gemma E2B → MiniCPM → LFM2.5 1.2B**. Conserva la estimación conservadora de RAM y la elección manual de Qwen y las demás configuraciones. Esta primera sugerencia no ha medido un modelo aún no descargado. Qwen se calibra al cargarlo; si Auto selecciona CPU, informa que Gemma puede reducir la espera sin borrar Qwen. El selector de modelo por preferencias de calidad/espera del curso podrá reutilizar estos perfiles; no se cambia de modelo ni se inicia otra descarga en segundo plano.

## Aislamiento y compatibilidad

La nueva variante está en `native/artifacts/b12359-adaptive-v1/`. Conserva el ABI 2 y añade una API de opciones versión 1: sonda, carga con adaptador/capas y consulta de colocación. La implementación está en `writing_llama_bridge_adaptive.cpp`, derivada de la fuente congelada con SHA `1ca23cd6dde3552b82731cc63ba3bfa2f38040982faa2fe07e044db3b56e3110`. La función de generación y el resto de su sección final permanecen idénticos al puente congelado. No se modificó upstream llama.cpp, el catálogo ni los prompts.

`IsolatedInferenceEngine` ofrece el mismo transporte en Windows y Android. Cada respuesta IPC se escribe y sincroniza antes de interpretarla, también ante error nativo. Los logs y las trazas quedan locales. En Android se conserva Mesa Turnip empaquetado y la selección de variantes CPU existentes. El selector adaptativo está activo en ARM64/API 28+; Android x86_64 y API 26–27 conservan el adaptador CPU dentro del proceso. No se presenta NativeAOT como una publicación validada, aunque se mantienen serialización generada y analizadores de compatibilidad.

## Validación realizada

- **39 pruebas del núcleo**, incluidas recuperación 33→32 con worker nuevo, otro adaptador después de fallos, memoria que baja o mejora, perfil corrupto, caducidad del fallback técnico, cambio de alimentación, cancelación y ausencia de reintentos técnicos de una evaluación. Una salida CPU inmediata con cero tokens no se cuenta como rendimiento válido.
- **4 pruebas de estado de interfaz**: invalidación de resultados al editar, advertencias de JSON/coherencia, conservación de RAW y exportación sin cola antigua.
- Compilaciones nativas Windows x64, Android ARM64 y x86_64; publicación Windows y APK Android 0.1.6, versionCode 7, minSdk 26 y targetSdk 37. Se inspeccionaron contenido, firma y exports nativos del paquete.
- Sondas de metadatos sin generación y **20 generaciones técnicas sintéticas** en este escritorio, sin casos ni gold de los benchmarks: 16 de calentamiento/calibración y cuatro evaluaciones de demostración. Los 24 artefactos protegidos de Fase 1 y los 27 vínculos congelados del experimento de 200 conservaron sus hashes. La auditoría de los 165 resultados importados del portátil siguió pasando.

| Modelo local, contexto 2048 | CPU, mediana de tres muestras (s) | Vulkan, mediana de tres muestras (s) | Selección Auto | Evaluación parcial adicional |
|---|---:|---:|---|---|
| Gemma E2B UD-Q4_K_XL | 12,346 | 1,333 | RTX 3070, 36/36 | 18/36, JSON STRICT |
| Qwen3.5 4B Q4_K_M descargable | 24,377 | 1,740 | RTX 3070, 33/33 | 14/33, JSON STRICT |

Las dos evaluaciones posteriores a Auto también devolvieron `STRICT`, con un intento cada una. La recarga de Gemma reutilizó el perfil sin nuevas muestras: se mantuvieron ocho trazas, cuatro por backend con calentamiento incluido. El primer calentamiento GPU de Gemma tardó 22,369 s, frente a 1,333 s de mediana posterior; ilustra por qué no se usa la primera generación como medida estable.

Estos tiempos describen un ejercicio sintético repetido y este PC. No son nuevas métricas de precisión, no sustituyen las mediciones de 40/120/200 ni permiten prometer la misma latencia en otro dispositivo. El nuevo APK y su reparto parcial **todavía requieren validación en teléfono físico**. La recuperación del fallo de la P1000 se verificó con fixtures y con la evidencia previa del portátil; esta entrega no volvió a ejecutar la aplicación nueva en ese portátil.

El ajuste upstream supone memoria del host suficiente. La recomendación inicial estima RAM y las sondas consultan presupuesto GPU, pero no constituyen una predicción completa de residencia, paginación o presión de memoria de Android. La generación posterior a la carga y los workers aislados siguen siendo necesarios. No se mide energía por componente durante la calibración ni se fuerza CPU por estar en batería.

## Repetir únicamente comprobaciones técnicas

Desde `cross_demo`, con dependencias b12359 y herramientas locales ya preparadas:

```powershell
.\scripts\build_adaptive_runtime.ps1 -Platform All
dotnet run --project WritingApp.Tests/WritingApp.Tests.csproj -c Release
dotnet run --project WritingApp.UiTests/WritingApp.UiTests.csproj -c Release
.\scripts\windows_build.ps1
.\scripts\android_build.ps1
```

El harness `WritingApp.Smoke` conserva `--execute` explícito. Añade `--adaptive` para comprobar selección/perfil, o `--gpu-layers N` para una distribución técnica concreta; `--native-dir` permite apuntar a la variante. No descarga pesos. En modo adaptativo, `--load-only` puede incluir la calibración inicial, pero omite la evaluación posterior. Con perfil válido tampoco vuelve a calibrar.

Fuentes, dependencias, pesos declarados, resultados técnicos y paquetes se vinculan por SHA en [el manifiesto de entrega](../../manifests/adaptive_runtime_20261118.json). La evidencia RAW permanece bajo `SLM_A1A2/logs/adaptive_runtime_20261118/`, fuera de Git. Las decisiones de precisión siguen apoyándose en la evaluación documentada de los modelos, no en elegir la mejor respuesta de esta calibración.
