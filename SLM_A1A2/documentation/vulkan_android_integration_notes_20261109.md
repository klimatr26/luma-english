# Notas de integración: Vulkan en Windows y una ruta Android

**Revisión:** 2026-11-09. **Base fijada:** llama.cpp `b11457`, commit `5ad1c5da0ad7f6176256b823925aad19134f0263`. Lectura técnica de fuentes; no se compilaron binarios ni se ejecutó inferencia. Este apunte complementa [vulkan_android_feasibility_20261109.md](vulkan_android_feasibility_20261109.md).

Este documento conserva la revisión de fuentes previa a implementar Vulkan. Las referencias al «runtime actual», propuestas y checklist describen ese estado previo. La integración Windows, sus pruebas reales posteriores y asuntos resueltos se documentan en [vulkan_windows_integration_20261109.md](vulkan_windows_integration_20261109.md); las tareas Android siguen pendientes.

## Conclusión

- **Windows Forms:** viable con un runtime Vulkan adicional de llama.cpp. Mantener CUDA intacto y seleccionar el artefacto por backend. La build debe traer tanto el backend Vulkan como un backend CPU utilizable; que exista `llama-server.exe` por sí solo no garantiza ninguno de los dos.
- **CPU fallback:** b11457 admite seleccionar CPU explícitamente. La aplicación puede detectar si hay un dispositivo Vulkan utilizable antes de iniciar el servidor y elegir CPU, y puede intentar una sola carga CPU con el mismo GGUF si falla el arranque Vulkan. El fallback se limita al inicio/carga, antes de enviar una generación.
- **Android:** es un port experimental de NDK/JNI, no una extensión del runtime WinForms. El backend Vulkan fijado exige Vulkan 1.2. Android exige Vulkan 1.1 para dispositivos nuevos de 64 bits desde Android 10/API 29; eso no garantiza 1.2 en un teléfono que se haya actualizado. Como alcance inicial del port se propone API 33 o posterior **y** verificar que el driver informe 1.2 y las capacidades requeridas. API 33 es una decisión de alcance, no un sustituto de la comprobación del driver ni un mínimo deducido exclusivamente de Vulkan.
- **Familias y cuantizaciones:** el código fijado contiene las arquitecturas Qwen3.5, Gemma 4 y LFM2, y sus tipos de tensor principales aparecen en los kernels/checks de Vulkan. Esto sustenta compatibilidad a nivel de fuente; no certifica todas las formas del grafo, GGUF, drivers ni dispositivos sin ejecutar la matriz.

## Alcance real del catálogo

El catálogo activo en [ModelAssets.cs](../demo/WritingDemo.Core/ModelAssets.cs) enumera **13** configuraciones: 2 Qwen 3.5 4B, 3 Gemma 4 E2B, 5 LFM 2.5 y 3 MiniCPM 5 2B. Los 3 launchers Qwen 3.5 2B todavía presentes en `launchers/serve_01..03` no son parte de ese catálogo activo. Los identificadores originales se conservan, incluido el 14 de Gemma UD-Q2; no son una numeración consecutiva de este catálogo.

| Familia activa objetivo | Variantes del catálogo | Tipos/cuantizaciones relevantes observados |
|---|---|---|
| Qwen 3.5 4B | Q8_0, Q4_K_M | BF16/F16/F32 y familias Q8_0/Q4_K aparecen entre tipos admitidos por Vulkan; confirmar el histograma y la inferencia del GGUF convertido en el build candidato. |
| Gemma 4 E2B | QAT Q4_0, UD-Q4_K_XL, UD-Q2_K_XL | Los metadatos guardados en [gemma_tensor_type_verification_v2.json](../manifests/gemma_tensor_type_verification_v2.json) registran respectivamente `F32/F16/Q6_K/Q4_0`, `F32/Q4_0` y `F32/F16/Q4_0/TQ2_0/Q8_0`; esos tipos aparecen en los checks/kernels Vulkan de b11457. Los nombres UD son cuantizaciones dinámicas mixtas, no un tipo uniforme. |
| LFM 2.5 1.2B | BF16, Q8_0, Q4_K_M | BF16, Q8_0, Q4_K/Q5_K/Q6_K y F16/F32 tienen soporte de tipo en los caminos de matriz consultados. La disponibilidad del camino BF16 y del rendimiento depende de driver/capacidades. |
| LFM 2.5 2.6B | Q8_0, Q4_K_M | Mismos tipos relevantes que la variante 1.2B; falta carga y generación real en el dispositivo objetivo. |

En el código fijado, `llama-arch.cpp` etiqueta `qwen35`, `gemma4` y `lfm2`, `llama-model.cpp` instancia sus clases y `ggml-vulkan.cpp` acepta tipos como Q4_0, Q8_0, Q2_K, Q4_K, Q5_K, Q6_K y TQ2_0 para operaciones de matriz/lectura de filas. La pregunta final no es solamente si reconoce la arquitectura: cada grafo debe colocarse, ejecutarse y generar correctamente con el driver real. Operaciones no cubiertas pueden quedar en CPU; la asignación mixta debe medirse.

## Flags y comportamiento en b11457

Los flags disponibles se encuentran en `common/arg.cpp` y en la tabla de opciones del servidor fijado.

| Objetivo | Args recomendados | Interpretación |
|---|---|---|
| Vulkan | `--device VulkanN -ngl 999` | `VulkanN` debe salir de `--list-devices`; `-ngl 999` pide el máximo de capas que quepan, no promete offload total. |
| CPU determinista | `--device none -ngl 0 --no-op-offload --no-kv-offload` | `--device none` deshabilita la selección de dispositivos aceleradores. `-ngl 0` limita offload de capas; `--no-op-offload` desactiva el offload de operaciones de tensores host. `--no-kv-offload` deja explícita la decisión para KV. |

`-ngl 0` **por sí solo no garantiza CPU puro**: el build guide oficial advierte que aún puede haber aceleración de GPU y recomienda `--device none` para desactivarla. `--no-op-offload` solo gobierna operaciones del host y tampoco reemplaza `--device none`.

Al pasar un nombre concreto como `--device Vulkan0`, `parse_device_list()` vuelve a enumerar backends y termina con `invalid device: Vulkan0` si no existe; no conviene usar ese error como la detección inicial. Ejecutar `llama-server --list-devices` con el mismo directorio y entorno, parsear el resultado y seleccionar CPU cuando no aparece un `VulkanN` elegible.

### `GGML_BACKEND_DL` y fallo de plugin

- En b11457, `GGML_BACKEND_DL=ON` requiere `BUILD_SHARED_LIBS=ON`; `ggml_add_backend_library()` crea plugins. Eso incluye CPU: empaquetar un `ggml-vulkan.dll` pero omitir el plugin `ggml-cpu*.dll` puede quitar también el fallback CPU.
- El cargador busca plugins junto al ejecutable y en el directorio actual (además de una ruta de build si fue fijada). El proceso de esta demo ya usa como `WorkingDirectory` el directorio de `llama-server`, lo que ayuda si el set de DLL está junto al servidor.
- `ggml_backend_load_all()` intenta cargar Vulkan y luego CPU. En builds Release el escaneo se hace en modo silencioso (`NDEBUG`); una DLL de Vulkan ausente o una dependencia que no resuelva puede pasar inadvertida y dejar CPU como único backend. No tratar “el servidor arrancó” ni “no hubo error de DLL” como prueba de Vulkan.
- `GGML_BACKEND_PATH` añade un backend externo después del escaneo normal; no excluye el plugin Vulkan. Un argumento `--device Vulkan0` falla si Vulkan no quedó registrado; la aplicación debe detectar y escoger CPU antes de iniciar con ese nombre.

El manifiesto/validador actual fija una sola huella `ExpectedServerSha256` para el ejecutable CUDA y no valida todo el cierre de DLL. Al incorporar Vulkan, usar perfiles de runtime separados por backend y registrar tamaño/SHA-256 de cada artefacto: ejecutable, DLL centrales y plugins CPU/Vulkan. Mantener la distribución CUDA existente como perfil separado.

### Emular cero GPUs sin tocar el sistema

El fuente de **b11457 sí contiene** `GGML_VK_VISIBLE_DEVICES`: si la variable está definida, el parser construye la lista con sus índices. Para simular cero dispositivos Vulkan solo para el hijo, poner un valor vacío (`GGML_VK_VISIBLE_DEVICES=""`) en el entorno de `ProcessStartInfo` y lanzar con `--device none -ngl 0 --no-op-offload`. Confirmar la precondición con `--list-devices` en ese mismo entorno: debe imprimir `Available devices: (none)`. Esto no cambia visibilidad global de GPU ni archivos/driver del equipo.

No pasar `-1`: el parser fijado extrae índices a `size_t` y arroja `Invalid Vulkan device index` para un índice inválido. La variable vacía ejercita la rama de lista sin índices; **no** simula que falte `ggml-vulkan.dll` ni una dependencia del plugin. Para probar DLL ausente, crear una carpeta de staging aislada que contenga el servidor y CPU runtime pero carezca del plugin Vulkan, sin renombrar ni retirar los artefactos verificados del checkout. Alternativa unitaria: inyectar una respuesta mock de `--list-devices` con `(none)` y comprobar que la decisión de runtime escoge CPU.

## Propuesta de flujo Windows

1. Añadir selección de backend explícita al runtime y a los perfiles de empaquetado; conservar el perfil y comportamiento CUDA. Construir/recibir un artefacto Vulkan de la misma revisión b11457, con runtime CPU disponible.
2. Antes de iniciar el servidor del modelo, lanzar `--list-devices`, capturar salida/código y verificar el backend real disponible. Si la DLL no se cargó, el loader Vulkan falta, no hay dispositivo o el backend no puede inicializar, elegir CPU antes de cargar el modelo. Grabar el backend pedido, el seleccionado y una razón corta en `runtime.log`.
3. Con dispositivo elegible, iniciar el modelo con `--device VulkanN -ngl 999` y conservar el mismo GGUF, contexto `4096`, generación y API HTTP. La aplicación puede permitir una sola vuelta a CPU si el **inicio/carga** falla por causa Vulkan antes de `/health`: detener solo el proceso hijo propio, arrancar CPU con los flags anteriores y el **mismo** modelo. No rebajar contexto ni reemplazar cuantización.
4. Después de `/health`, errores de generación no se repiten automáticamente por CPU. Un HTTP 429 sigue siendo terminal: detener el servidor propio, guardar los datos de intercambio/estado y presentar el handoff preciso; no reintentar ni reiniciar para volver a emitir la misma generación.
5. Hacer visibles en UI/logs el backend realmente seleccionado y, tras carga exitosa, el conteo real de capas offload. No inferir GPU por nombre del build, extensión DLL ni el `-ngl 999` configurado.

### Evidencia en logs

**Vulkan seleccionado/activo** debe incluir el backend cargado (`loaded Vulkan backend from ...ggml-vulkan.dll`), uno o más dispositivos (`ggml_vulkan: Found N Vulkan devices`, con nombre/driver y capacidades) y, tras cargar el modelo, líneas `offloading ... layers to GPU` / `offloaded X/Y layers to GPU` junto al buffer `VulkanN model buffer size = ... MiB`. `--list-devices` solo acredita enumeración; las líneas tras carga acreditan asignación de pesos. Para una aceptación de uso GPU, complementar con medición de actividad/uso del dispositivo durante prefill y generación.

**CPU seleccionado** debe registrar la decisión de la aplicación, el backend CPU/plugin o CPU compilado de forma estática, políticas `--device none` y salida `/health`. `--list-devices` `(none)` es la evidencia de no GPU visible en esa ejecución. En una build Release, la ausencia de mensajes de fallo del plugin no es evidencia de que Vulkan se haya cargado.

Una capa cargada en GPU no demuestra que todas las operaciones de la red se ejecuten allí. Registrar el conteo y buffers por dispositivo; comprobar que el modelo devuelve JSON válido y medir por separado prefill/generación, memoria host/GPU y tiempo. Los logs de `llama-server` ya se capturan por stdout/stderr en el runtime actual.

## Port Android: estrategia independiente

`WritingDemo.WinForms.csproj` apunta a `net10.0-windows`; `LlamaRuntime.LoadAsync()` rechaza plataformas no Windows y la clase usa `iphlpapi.dll` para confirmar el PID que escucha. Su gestión de hijo Win32 no es una base Android portable.

La ruta con menos adaptación al entorno móvil es una app Android y una capa nativa arm64-v8a en el proceso:

1. Separar el contrato de inferencia (cargar `ModelSpec`, generar, cancelar/detener) de implementación de procesos HTTP/Win32.
2. Para Android, usar Kotlin/Java con JNI como en `examples/llama.android`, o una binding .NET Android sobre la API nativa C. Enlazar `libllama`/GGML y mantener UI, ciclo de vida, almacenamiento y memoria bajo el sandbox de Android.
3. Entregar primero una variante CPU funcional. Tratar Vulkan como plugin/ABI nativo experimental: compilar para `arm64-v8a` con NDK, `GGML_NATIVE=OFF`, `glslc` ejecutable en host para SPIR-V y headers/import library Vulkan target del NDK. El CMake del backend exige Vulkan, `glslc` y SPIRV-Headers; la toolchain cruzada debe impedir que CMake enlace accidentalmente el loader del host.
4. En runtime comprobar nivel API, `vkEnumerateInstanceVersion`, `VkPhysicalDeviceProperties.apiVersion`, GPU física y capacidades consultadas por el backend antes de escoger Vulkan. Para el alcance inicial propuesto se limita la ruta Vulkan a Android 13/API 33+ y dispositivo/driver >=1.2, además de las capacidades requeridas por b11457; no se afirma que todo teléfono con API 33 lo admita. Ante falla/ausencia, seleccionar CPU antes de cargar.
5. Probar en hardware real: un Adreno y, si se pretende cobertura multi-vendor, al menos un proveedor adicional. Medir presión de RAM compartida, KV/contexto, temperatura sostenida, offload y estabilidad del driver. Una lista de tipos soportados en fuente no sustituye a estas pruebas.

El NDK aporta `<vulkan/vulkan.h>` y `libvulkan` desde API 24, pero la biblioteca no instala el driver ni garantiza GPU Vulkan. Android usa su loader del sistema y el driver entregado por el dispositivo; no empaquetar un loader/driver de Windows o Linux en el APK. La guía upstream de Android compila la ruta nativa CPU y el sample JNI fija CPU/KleidiAI, no activa `GGML_VULKAN`. La publicación b11457 y la nightly oficial b12144 listan Android CPU y una variante específica Snapdragon, pero no una distribución Android Vulkan genérica.

La alternativa conceptual de servir HTTP desde un proceso Android separado exigiría resolver ejecución/ABI del binario, permisos y ciclo de vida en sandbox, loopback, foreground/background y ubicación del GGUF; no reutiliza el hijo Windows actual. Preferir JNI/in-process salvo que exista una necesidad de protocolo HTTP local.

## Checklist de implementación y aceptación (pendiente)

- [ ] Construir b11457 con `GGML_VULKAN=ON` y el modo de plugins elegido; comprobar compilación y revisar las dependencias transitivas que se empaquetarán.
- [ ] Confirmar que `llama-server --list-devices` expone el nombre Vulkan del equipo; luego iniciar con selección explícita y el mismo modelo/contexto usado por CUDA.
- [ ] Añadir perfil de backend y hashes por artefacto; confirmar que CPU plugin está incluido. Mantener CUDA y sus hashes/rutas existentes en su perfil.
- [ ] Probar CPU explícito (`--device none -ngl 0 --no-op-offload --no-kv-offload`) y la decisión al ver `(none)`; probar además cero Vulkan simulado con `GGML_VK_VISIBLE_DEVICES=""` en el proceso hijo.
- [ ] Probar staging sin Vulkan DLL o un mock de `--list-devices`; verificar mensajes de selección, health, parada únicamente del hijo propio y mismo hash/configuración de modelo en el fallback de arranque.
- [ ] Inyectar errores posteriores a `/health` y HTTP 429 para comprobar que no se reenvía una generación; preservar capturas/handoff preciso.
- [ ] Ejecutar una matriz por cada GGUF del catálogo activo: carga, JSON/salida de generación, capas/buffers Vulkan, operaciones CPU remanentes, latencia, RAM/VRAM, contexto real.
- [ ] Para Android, preparar JNI CPU `arm64-v8a`, decidir min API, compilar Vulkan en NDK separado y hacer pruebas en hardware API/driver >=1.2; guardar métricas térmicas, memoria y tasas de cierre del proceso.

## Fuentes primarias

### llama.cpp fijado a b11457

- Release y lista de artefactos por plataforma: https://github.com/ggml-org/llama.cpp/releases/tag/b11457
- Guía de build: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/docs/build.md
- Guía Android: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/docs/android.md
- Sample Android JNI: https://github.com/ggml-org/llama.cpp/tree/5ad1c5da0ad7f6176256b823925aad19134f0263/examples/llama.android
- Opciones de servidor: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/tools/server/README.md
- Parser de flags (`--device`, `--list-devices`, `--no-op-offload`): https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/common/arg.cpp
- Cargador dinámico de plugins: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-backend-reg.cpp
- Backend Vulkan, versión mínima y `GGML_VK_VISIBLE_DEVICES`: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-vulkan/ggml-vulkan.cpp
- Checks `supports_op` Vulkan: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-vulkan/ggml-vulkan.cpp#L15330
- CMake del backend Vulkan y generador de shaders: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-vulkan/CMakeLists.txt
- Arquitecturas/modelos implementados: https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/src/llama-arch.cpp y https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/src/llama-model.cpp

### Estado oficial consultado al 2026-11-09

- Release estable `v0.9.0` (b12110): https://github.com/ggml-org/llama.cpp/releases/tag/v0.9.0
- Nightly oficial b12144 y lista de plataformas: https://github.com/ggml-org/llama.cpp/releases/tag/b12144
- Build guide actual: https://github.com/ggml-org/llama.cpp/blob/master/docs/build.md
- Android guide actual: https://github.com/ggml-org/llama.cpp/blob/master/docs/android.md

### Android y loader

- NDK, API estables/Vulkan/libvulkan: https://developer.android.com/ndk/guides/stable_apis
- Versiones Vulkan por Android API y consultas al driver: https://developer.android.com/games/develop/vulkan/native-engine-support
- Vulkan loader y despliegue en Windows: https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderApplicationInterface.md
