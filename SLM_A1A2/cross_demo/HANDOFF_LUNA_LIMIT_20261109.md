# Traspaso: detenido por límite de uso de Luna

Captura del estado: **2026-11-09 22:25 UTC** (America/Guayaquil UTC−5).

Nota posterior: el usuario indicó «Continúa. Mis límites de uso están completos ahora». Se retomó el trabajo con los mismos subagentes Luna, sin sustitución. Este archivo conserva el estado histórico de la detención; el cierre vigente se describe en [implementación y validación](docs/implementation_and_validation_20261109.md).

## Motivo de la detención

Los tres subagentes `cross_ui`, `cross_native` y `cross_android`, invocados como **gpt-6-luna / max**, terminaron con:

> You've hit your usage limit.

Se aplica la instrucción del usuario: guardar un traspaso preciso, detener el trabajo y esperar su indicación; **no reintentar ni sustituir el modelo**. No se debe interpretar este archivo como autorización para reanudar. El último «Continúa» llegó antes de recibirse estos errores de límite.

## Encargo vigente

Crear una aplicación Avalonia para Windows y Android, .NET 11 RC3, con selección inicial recomendada por RAM/almacenamiento, elección manual de modelo/cuantización, descarga verificada/cambio posterior, ejercicios nuevos Writing A1/A2, ejemplos correcto/incorrecto, inferencia local Vulkan con alternativa CPU, interpretación JSON/retroalimentación y exportación. Preparar el diseño para NativeAOT, sin exigir que todo sea AOT todavía. Compilar APK y probar emulador si existe. El usuario probará teléfonos físicos después.

No acceder al test final de aproximadamente 200 casos. No modificar benchmarks, gold ni resultados anteriores. Las pruebas actuales son demostraciones sintéticas nuevas. No hay autorización nueva para ejecutar benchmarks. Los reintentos de formato de producto son opcionales y separados del protocolo experimental.

## Git y archivos

- Repositorio local, `main`, sin remoto; baseline de este trabajo: **6cc3c01**, integración Vulkan de Windows Forms ya finalizada en la tarea anterior.
- Estado al detener: únicamente `?? SLM_A1A2/cross_demo/`; **todo el nuevo trabajo está sin commit**. Conservarlo íntegro.
- No se editaron los fuentes antiguos de WinForms ni los artefactos experimentales durante esta tarea. Los tres archivos C# de contratos/parser/ejercicios existentes se enlazan como fuentes de solo lectura desde Shared.
- `cross_demo/.gitignore` excluye SDK local, builds, paquetes, DLL/SO, caché de compilación y logs; no agregar esos binarios a Git. Un agente sobrescribió inicialmente este archivo y root restauró las reglas globales necesarias.
- El README nuevo es una guía de implementación, **todavía necesita actualizar los resultados y comandos finales de Android**; no es un informe de cierre.

## Implementación escrita y comprobada

### Compartido (root)

- `global.json`: SDK **11.0.100-rc.3.26522.148**; no cambia el `global.json` .NET 10 de la demo anterior.
- `Directory.Build.props`: nullable/determinismo y `JsonSerializerIsReflectionEnabledByDefault=false` para todos los hosts.
- `WritingApp.Shared`: contratos, catálogo embebido, prompts embebidos, recomendaciones, `ModelStore`, `EvaluationService`, `SessionStore`, JSON source generation.
- Catálogo: 13 identidades/hashes anteriores y **2 Qwen Unsloth descargables separados**, sin atribuirles los resultados de los GGUF locales. Pin de estas dos variantes: `unsloth/Qwen3.5-4B-GGUF`, revisión `e87f176479d0855a907a41277aca2f8ee7a09523`. Metadatos comprobados contra API primaria y guardados en `manifests/portable_qwen_sources_20261109.json`. **No se descargaron sus pesos**.
- `scripts/generate_portable_assets.py` copia solo metadatos y prompts; no copia casos/gold. Los prompts propuestos de revisión se aplican a Qwen/MiniCPM/Gemma; LFM mantiene el base. No se afirma mejora de calidad validada.
- ModelStore: SHA/tamaño/magic, transferencia por streaming, no reemplazo automático de archivos diferentes, cancelación elimina solo su parcial. `FindVerifiedAsync` busca copia válida incluso si la caché está corrupta. Importación explícita totalmente verificada archiva la copia errónea de la caché propia como `.unverified-GUID`; no mueve externos.
- Recomendación conservadora, permite override. Contexto Android 2048 / Windows 4096. No es un ranking de calidad.
- Reintentos: 1 por defecto, máximo 3, semillas 42/43/44, mismos inputs/prompt. Solo formato/consistencia inutilizable; no reintentos técnicos ni por calidad lingüística. Se guardan checkpoints de cada respuesta antes de continuar.
- **15/15 pruebas** de `WritingApp.Tests` pasaron en Release, sin inferencias: descarga/cancelación/429/hash/caché/importación, recomendaciones, reintentos/source-gen.
- Comprobación de URLs reales leyendo solo los 4 bytes GGUF: LFM1.2 Q4 y Qwen Unsloth Q4 respondieron HTTP206 y tamaño total esperado. No fue una descarga completa.

### Interfaz y Windows (`cross_ui`)

- Avalonia **12.1.5**, UI común `MainView`, Desktop bootstrap con memoria Windows real y búsqueda del directorio de modelos del checkout.
- Modelo/backend/ejercicio, ejemplos, descarga e importación para **cualquier** variante, cancelación, salida RAW por intento y exportación con selector de archivos.
- Invalida resultados viejos al cambiar entradas; snapshots y bloqueo de edición durante carga/evaluación. CTS de carga y evaluación; evita colas por clics repetidos; espera/cancela al cerrar.
- Datos extensos en Expander; diseño estrecho apila columnas. Conteo de capas negativo se muestra «no medidas».
- Builds Debug y publicación Desktop terminaron sin errores/advertencias.
- Publicación Windows existente y funcional:
  `artifacts/windows/WritingApp.Desktop.exe`
  Compilación usada por root: `-c DesktopRelease -p:Optimize=true -r win-x64 --self-contained false`.
- Requiere runtime .NET 11 instalado en este equipo. Las DLL se copian de `native/artifacts/win-x64/` junto al EXE.

### Motor nativo (`cross_native`)

- `WritingApp.Native` implementa IInferenceEngine con LibraryImport estático, ABI C versionado, UTF-8 explícito, handles y cancelación.
- `native/include`, `native/src/writing_llama_bridge.cpp`, `native/CMakeLists.txt` contra llama.cpp **b11457**, commit `5ad1c5da0ad7f6176256b823925aad19134f0263`, fuentes existentes bajo `SLM_A1A2/tools/llama.cpp/llama.cpp-<commit>`.
- Windows compilado con CMake/MSVC de VS 18, compartido, Jinja/common, CPU, sin OpenMP; plugin Vulkan oficial del mismo commit copiado sin modificar el paquete preservado anterior.
- **7 DLL** finales en `native/artifacts/win-x64/` (incluye Vulkan). Se demostró carga/generación Vulkan con este core y plugin.
- Correcciones de revisión: no duplicar `llama_sampler_accept` después de `llama_sampler_sample`; no alimentar indebidamente el prompt a penalties; CPU usa lista de dispositivos vacía y ambos offload desactivados.
- Incidencia real: callback de progreso confundía `load_context*` con `int32_t*` y abortaba la carga. Corregido pasando el flag real; recompilado. SHA del bridge Windows corregido comunicado por agente: `6d22069209648130c77f449a799c0d5208e54e06a9e84c8d73cbe0c5f9c730a4`.
- API no ofrece getter público de capas reales: exporta **−1 desconocido para Vulkan**, 0 para CPU. Los logs permiten comprobar offload/buffers; no inventar conteos desde el número de capas del modelo.
- ARM64 **y x86_64 CPU ya compilados y staged** al detener: siete SO por ABI, incluido su `libc++_shared.so`:
  `native/artifacts/android-arm64-v8a/` y `native/artifacts/android-x86_64/`.
- **Vulkan Android todavía NO está compilado/empaquetado.** El código permite plugin, pero no afirmar que el APK actual acelera GPU. Falta intentar construirlo con NDK y verificar fallback antes de entrega.
- NDK instalado por root con sdkmanager, sin prompt de licencia: `C:/Users/Kevin/AppData/Local/Android/Sdk/ndk/29.0.14206865`.
- glslc host disponible: `<NDK>/shader-tools/windows-x86_64/glslc.exe`.

## Pruebas reales Windows realizadas

Harness `WritingApp.Smoke`, exige `--execute`, solo usa pesos existentes, no descarga ni recorre benchmarks. Se usó configuración **NativeSmoke** para evitar que builds Android Release concurrentes bloquearan PDB de Shared. No compilar proyectos al mismo tiempo en la misma configuración de Shared.

Evidencias bajo **SLM_A1A2/logs/cross_demo/**, fuera de Git:

| Evidencia | Resultado |
|---|---|
| `native_cpu_load_incident_20261109.json` | Primera carga abortada por bug de callback; cero generaciones. Conserva hash del DLL fallido y causa. |
| `native_cpu_lfm12_20261109.json` + `.log` | LFM1.2 Q4, CPU, contexto2048, una respuesta, INCONSISTENT. |
| `native_vulkan_lfm12_20261109.json` + `.log` | LFM1.2 Q4, Vulkan, contexto2048, una respuesta, INCONSISTENT. |
| `native_vulkan_06-minicpm5-2b-q4-k-m_20261109.json` + `.log` | Vulkan, una respuesta, STRICT. |
| `native_vulkan_11-qwen35-4b-q4-k-m_20261109.json` + `.log` | Vulkan, una respuesta, STRICT. |
| `native_vulkan_13-gemma4-e2b-ud-q4-k-xl_20261109.json` + `.log` | Vulkan, una respuesta, STRICT. |
| `native_vulkan_16-lfm25-26b-q4-k-m_20261109.json` + `.log` | Vulkan, una respuesta, INVALID_JSON. |

No se cambió sampling/prompt por estos resultados. No se seleccionó una respuesta mejor. **Seis peticiones sintéticas CLI** completadas, ninguna de benchmark.

Además se comprobó desde la **GUI Windows publicada**: seleccionar MiniCPM Q4, cargar Auto→Vulkan, usar ejemplo correcto y evaluar una vez (contexto4096, semilla42). Devuelve STRICT, `is_correct=true`, texto preservado y una recomendación opcional en feedback. Sesión guardada automáticamente:

`C:/Users/Kevin/AppData/Local/WritingApp/Sessions/session-20261109T183249065Z-c5b07eb42b8547be9ba5c2459748ff5f.json`

**Total hasta la pausa: 7 nuevas generaciones técnicas Windows.** No hubo generación Android. La exportación por diálogo todavía no se probó; sí se comprobó escritura local source-gen.

La ventana de Windows publicada quedó abierta, modelo MiniCPM Q4 cargado, sin generación activa. Se observó y capturó en la herramienta la marca de correcto y el feedback; **no se guardó aún esa captura como archivo**. Identificador de la ventana durante la prueba: 5181090, ruta `.../artifacts/windows/WritingApp.Desktop.exe`. Reobservar antes de actuar; no reutilizar índices/coordenadas viejos.

## Android: estado real pendiente

- Android Studio **2025.2.3**, JDK embebido21.0.8. No se actualizó Studio.
- SDK usuario: `C:/Users/Kevin/AppData/Local/Android/Sdk`; SDK manager adicional existente en `C:/Program Files (x86)/Android/android-sdk/cmdline-tools/latest/bin/sdkmanager.bat`.
- SDK global .NET11 RC3 no reconocía android (NETSDK1147): carga VS era preview6. Se creó SDK aislado en `.tools/dotnet11`; no se modificó SDK global. Herramienta Android usa manifiesto/bindings VS preview6 API37 junto a runtime Mono RC3; **documentar esta combinación experimental**, no llamarla una carga oficial RC3 íntegramente validada.
- Se añadieron plataforma **android-37.0** y build-tools37.0.0 al SDK usuario, con licencias ya presentes y sin nuevas aceptaciones.
- Host `net11.0-android37.0`, minAPI26, paquete `org.kevinlima.writinglab`, ABIs arm64+x64.
- Scripts `android_setup_dotnet.ps1`, `android_build.ps1`, `android_try_emulator.ps1`; revisar sus flags y estado antes de reusar. Android manifest incluye `extractNativeLibs=true`, necesario para plugins GGML dinámicos.
- **APK PRELIMINAR SOLO DE HOST/UI**:
  `artifacts/android/org.kevinlima.writinglab-Signed.apk`, **108.289.156 bytes**.
  No se debe entregar como APK funcional de inferencia: fue publicado antes de incorporar SO.
- Emulador existente `Medium_Phone_API_36.1` (config original 2GB, x86_64, userdata6GB), iniciado temporalmente oculto/read-only con 4GB, sin cambiar su configuración original. `adb devices` informó **emulator-5554 online**. Quedó en ejecución al pausar; no hay inferencia activa ni modelo transferido.
- Primer arranque falló por tema AppCompat; agente añadió `WritingLabTheme.NoActionBar`.
- **Bloqueo UI Android todavía pendiente**: Avalonia12 usa `IActivityApplicationLifetime.MainViewFactory`; `App.axaml.cs` solo contemplaba ClassicDesktop/ISingleView. El agente UI estaba verificando esta API cuando alcanzó el límite. Al inspeccionar tras el límite, `rg IActivityApplicationLifetime|MainViewFactory|BringIntoView` no encontró coincidencias. Verificar fuente real y arreglar branch antes de reconstruir.
- Ajuste de UX solicitado aún pendiente: al terminar evaluación, llevar la vista a `ResultPanel` (BringIntoView) para no dejar el resultado fuera del scroll.
- Agente Android confirmó que no mantenía un proceso de build activo; tras el límite, inventario no mostró procesos cmake/ninja/clang activos. Las dos carpetas SO ya existen. No reanudar herramientas automáticamente por este dato.

## Responsabilidades previas (al retomar solo con indicación)

- root: Shared, Tests, Smoke, raíz cross_demo, README, documentación, integración/QA/procedencia y commit final.
- `cross_ui`: UI y Desktop; revisar lifetime Android y BringIntoView, luego avisar para recompilar.
- `cross_native`: native + WritingApp.Native; SO CPU ambas ABIs listos, Vulkan Android/receta/manifiesto todavía pendientes.
- `cross_android`: host Android, scripts android*, android_environment.json, SDK/emulador/APK. No editar .gitignore ni raíz compartida.
- Reutilizar **Luna 6 max** si el usuario autoriza continuar y el límite lo permite; no reemplazar por otro modelo silenciosamente.

## Orden para completar cuando el usuario indique continuar

1. Leer este traspaso y comprobar Git/procesos/ventanas sin descartar archivos. Confirmar disponibilidad Luna sin reintentos repetitivos si vuelve a limitar.
2. Resolver lifetime Avalonia12 y tema; SO CPU ya listos. Decidir/compilar Vulkan Android con glslc y sysroot correctos, sin enlazar loader Windows al target.
3. Recompilar APK con SO por ABI y verificar ZIP, extracción, libc++ y bibliotecas reales; el preliminar de108MB no basta. Evitar builds C# concurrentes que compartan `obj/Release`.
4. Instalar APK nuevo en emulator-5554, verificar arranque/logcat. Si se prueba inferencia, transferir/importar solo un GGUF existente verificado (LFM1.2 Q4 es menor); no redescargar pesos innecesariamente. Contexto2048 y una prueba técnica, no benchmark. No equiparar GPU virtual/emulada con validación de GPU física.
5. Probar exportación, override/cambio, resultado inválido visible, invalidación de resultados viejos y layout estrecho; conservar todos los intentos y fallos.
6. Rehacer publicación Windows tras cambios UI finales (la ruta artifacts/windows puede estar en uso por ventana propia). Volver a comprobar source-gen y fixtures si cambian fuentes.
7. Documentar resultados y fallos reales, hashes de paquetes/bibliotecas/evidencias, toolchain aislado, limitaciones Android/Vulkan/NativeAOT. Registrar primer intento y recuperación por separado. No tocar test200.
8. Revalidar integridad24 Fase1, auditoría v2 fuentes164/derivados76 y93 originales Git; revisar assets≤10MiB y Git. Guardar código/documentación en commit local, sin binarios ni remoto.
9. Entregar EXE/APK funcional con límites y pasos de instalación. Si no se logra inferencia Android, decirlo explícitamente y no presentar el APK de UI como funcional.

La comprobación de preservación y el informe final de entrega **no se han ejecutado todavía en esta tarea**. No marcarla completa ni borrar este traspaso antes de cerrar los pendientes.
