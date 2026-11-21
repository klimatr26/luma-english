# Viabilidad de Vulkan para llama.cpp en Windows y Android

**Fecha de revisión:** 2026-11-09. **Alcance:** lectura de fuentes upstream y del checkout local. No se compilaron binarios, no se instalaron SDK/NDK ni drivers y no se probaron dispositivos.

## Conclusión

- **Windows: sí, es una ruta directa y oficialmente documentada.** El commit fijado b11457 trae la opción CMake `GGML_VULKAN`; su release oficial ofrece un artefacto Vulkan para Windows x64. El demo C# puede conservar su cliente HTTP y reemplazar el `llama-server` hijo CUDA por uno compilado con Vulkan, sujeto a actualizar los hashes/rutas que valida el runtime.
- **Android: técnicamente plausible, pero no queda confirmado como objetivo Android Vulkan genérico por upstream.** El NDK aporta headers y la biblioteca de enlace `libvulkan`; el loader y el driver Vulkan se proporcionan en el dispositivo. Sin embargo, los documentos de build de llama.cpp presentan el cross-build Android como CPU y no dan una receta de `GGML_VULKAN` para Android; las releases listan Android CPU y una variante Snapdragon, pero no un artefacto Android Vulkan genérico. Haría falta un port/build experimental y medirlo en dispositivos reales.
- **La reducción frente al paquete CUDA podría ser grande, pero no se puede afirmar el tamaño final sin producir el binario Vulkan.** En el paquete local se observaron 663.82 MiB en cuatro DLL asociadas a CUDA. Vulkan necesita su propia DLL backend, el loader y el driver; el tamaño final de esos elementos no se midió aquí.

## Versión fijada y verificación de versión actual

El manifiesto local [runtime_asset_hashes_120.json](../manifests/runtime_asset_hashes_120.json) fija `b11457`, commit completo `5ad1c5da0ad7f6176256b823925aad19134f0263`. La página de la release confirma que se publicó el **6 de octubre de 2026**, muestra el mismo SHA corto `5ad1c5d` y lista **Windows x64 Vulkan** y **Windows arm64 Vulkan**. Para Android lista CPU y Snapdragon (CPU, Adreno GPU, Hexagon NPU), no una build Vulkan genérica. ([Release b11457](https://github.com/ggml-org/llama.cpp/releases/tag/b11457))

Verificación independiente al 9 de noviembre: GitHub marca `v0.9.0` como release más reciente, publicada el 4 de noviembre desde `cd959ba`; la página indica que sus artefactos nocturnos corresponden a `b12110`. La release nightly más reciente consultada es `b12144`, publicada el 6 de noviembre desde `69ee2ec`. Esta también lista builds Vulkan Windows x64/arm64 y Android CPU/Snapdragon, sin build Android Vulkan genérica. Esto indica continuidad de Vulkan en Windows y ausencia de un objetivo Android Vulkan listo en los artefactos upstream consultados; **no demuestra que el backend no pueda compilarse para Android**. ([Latest estable `v0.9.0`](https://github.com/ggml-org/llama.cpp/releases/latest), [Nightly b12144](https://github.com/ggml-org/llama.cpp/releases/tag/b12144))

## Tamaños observados en este checkout

Se midieron longitudes de archivos existentes, sin abrir ni modificar modelos. Los GGUF viven en el junction `models` → `D:\SLM_A1A2_models`; son datos del modelo y no parte del runtime.

| Grupo observado | Tamaño | Qué significa |
|---|---:|---|
| Seis archivos centrales de `llama-server` (`llama-server.exe`, `llama-server-impl.dll`, `llama-common.dll`, `llama.dll`, `ggml.dll`, `ggml-base.dll`) | 20.38 MiB | Subtotal de archivos centrales, **no** es el cierre completo de dependencias. No suma el plugin CPU seleccionado, módulos opcionales ni un futuro `ggml-vulkan.dll`. |
| Cuatro archivos CUDA (`ggml-cuda.dll`, `cublas64_13.dll`, `cublasLt64_13.dll`, `cudart64_13.dll`) | 663.82 MiB | Candidatos a desaparecer con un build sin CUDA. Los tres DLL `cublas/cudart` suman 522.85 MiB; `ggml-cuda.dll` suma 140.98 MiB. |
| Todos los `.exe`/`.dll` de `tools/llama.cpp/b11457` | 711.14 MiB, 55 archivos | Paquete local completo, con utilidades y 14 variantes de backend CPU además de los archivos de CUDA; no representa un paquete mínimo para el demo. |
| `.gguf` en `models` | 45.62 GiB, 17 archivos | Almacenamiento local observado, separado del runtime. Los GGUF observados van de 0.68 a 7.85 GiB por archivo. Tamaño en disco no equivale a memoria de inferencia: contexto/KV, buffers y otros procesos elevan el consumo. |

La resta del paquete actual menos los cuatro DLL CUDA deja 47.32 MiB, pero incluye herramientas y variantes CPU redundantes. No debe presentarse como tamaño estimado del runtime Vulkan ni como ahorro neto: faltan por medir el backend Vulkan, el conjunto mínimo realmente cargado y cualquier loader que se decida distribuir.

## Windows: empaquetado y distribución

La guía de build de b11457 configura Vulkan con `-DGGML_VULKAN=ON`; el CMake del backend requiere Vulkan, `glslc` y SPIRV-Headers. El build compila los shaders `.comp` a SPIR-V y genera un header C++ con ellos, así que `glslc` es **herramienta de build**, no dependencia de inferencia instalada en el equipo final. El build dinámico produce un backend `ggml-vulkan.dll` en lugar de `ggml-cuda.dll`; el resto de `llama.cpp` y el plugin CPU siguen siendo necesarios. ([Build docs en el commit fijado](https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/docs/build.md), [CMake de ggml-vulkan en el commit fijado](https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-vulkan/CMakeLists.txt))

En Windows, el loader se llama `vulkan-1.dll` y normalmente lo instala el driver Vulkan del proveedor GPU. Khronos desaconseja copiar el loader dentro de cada aplicación porque puede quedar desfasado frente a los drivers; si se necesita asegurar su presencia, documenta el instalador Vulkan Runtime como alternativa. La build aún requiere un driver Vulkan compatible en el equipo destino: el SDK compila, pero no instala el soporte GPU del usuario. Las cuatro DLL CUDA medidas son dependencias del paquete de usuario, no el driver del fabricante; quitarlas del paquete no elimina la necesidad de un driver gráfico Vulkan instalado. ([Khronos Vulkan Loader: aplicación y distribución](https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderApplicationInterface.md))

## Android: NDK, loader, GPU y memoria

- llama.cpp documenta el cross-build Android con NDK/CMake, ABI `arm64-v8a`, `GGML_NATIVE=OFF` y opciones de CPU; no incluye `GGML_VULKAN=ON` en esa receta. El Android NDK documenta `<vulkan/vulkan.h>` y `libvulkan`, presentes para API level 24 o superior. Que esté disponible la biblioteca **no garantiza que el dispositivo tenga una GPU Vulkan**; hay que enumerar los dispositivos en runtime. ([llama.cpp Android build docs](https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/docs/android.md), [Android NDK: Stable APIs](https://developer.android.com/ndk/guides/stable_apis))
- Vulkan 1.0 puede existir desde Android 7/API 24; 1.1 requiere plataforma Android 10/API 29 en adelante; 1.3 requiere Android 13/API 33. La versión del sistema no garantiza la versión anunciada por el driver. Android recomienda API 29+, Vulkan 1.1+ y verificar las capacidades efectivas del driver para definir un mínimo práctico. Para cubrir teléfonos antiguos se necesitan comprobaciones y una ruta CPU; API 24 no implica soporte uniforme. ([Android: soporte Vulkan nativo](https://developer.android.com/games/develop/vulkan/native-engine-support))
- FP16, tamaño de subgroup, extensiones y memoria compartida/de cómputo son capacidades reportadas por GPU/driver, no una promesa del NDK ni del API level. El backend fijado consulta soporte de FP16/subgroups y límites como `maxComputeSharedMemorySize`; las rutas aceleradas que requieren extensiones deben habilitarse según esas consultas. La memoria disponible en móviles es compartida y compite con la app, sistema y otras asignaciones; Android puede matar procesos bajo presión de memoria. Hay que registrar memoria del proceso y del dispositivo y probar contexto/KV reales, no inferir ajuste a partir del tamaño GGUF. ([CMake/shader checks de Vulkan](https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-vulkan/CMakeLists.txt), [Android memory management](https://developer.android.com/topic/performance/memory-management))
- El scheduler de ggml puede asignar operaciones solo a backends que declaren soportarlas, con CPU disponible como fallback en el flujo de inferencia. Eso permite inferencia mixta, pero puede introducir transferencias y lentitud; no sustituye la prueba de carga, prefill y generación para cada modelo. La implementación GPU, el GGUF y la familia son tres comprobaciones distintas.
- El sample `examples/llama.android` del commit fijado es Kotlin + JNI + C++ **in-process**: llama.cpp se enlaza en una biblioteca nativa y `ai_chat.cpp` carga modelos desde el proceso Android. Su CMake elige `arm64-v8a`, KleidiAI/CPU, OpenMP, y `GGML_BACKEND_DL`; no activa Vulkan. Es una base concreta para un port JNI, pero el backend dinámico Vulkan debe compilarse y empaquetarse por ABI, además de integrar el loader de Android del sistema. El API `minSdk` del sample observado es 33. ([Android sample en el commit fijado](https://github.com/ggml-org/llama.cpp/tree/5ad1c5da0ad7f6176256b823925aad19134f0263/examples/llama.android))
- La otra opción conceptual es lanzar `llama-server` como proceso hijo arm64 y hablarle por HTTP loopback, similar al demo Windows; no está implementada en este proyecto Android y requiere resolver empaquetado/ejecución del binario, ciclo de vida, almacenamiento del GGUF y cierre seguro del proceso. En este checkout, `WritingDemo.WinForms.csproj` apunta a `net10.0-windows` y `LlamaRuntime` falla fuera de Windows; no hay renderer Android que se pueda reutilizar tal cual.

## Comandos propuestos para una fase posterior (no ejecutados)

### Build Vulkan Windows desde el commit fijado

Desde una consola de desarrollador con CMake/Visual C++ y el Vulkan SDK instalados. `<build-dir>` debe ser una carpeta temporal de salida separada del checkout fijado.

```powershell
cmake -S tools/llama.cpp/llama.cpp-5ad1c5da0ad7f6176256b823925aad19134f0263 `
  -B <build-dir> `
  -DGGML_VULKAN=ON `
  -DGGML_BACKEND_DL=ON `
  -DCMAKE_BUILD_TYPE=Release
cmake --build <build-dir> --config Release --target llama-server
```

Verificación propuesta: `llama-server --list-devices`, ejecutar el mismo GGUF con el backend Vulkan seleccionado y confirmar en log dispositivo Vulkan, capas asignadas al GPU, ausencia de errores de operación/allocación y `/health`. Después comparar latencia, RSS, VRAM y salida JSON del mismo conjunto frente al runtime CUDA, sin rebajar contexto ni parámetros.

### Exploración Android arm64

Partir del `examples/llama.android` JNI o de un build NDK aislado. La siguiente configuración es un **esqueleto para validar CMake**, no una receta confirmada: el backend fija `find_package(Vulkan COMPONENTS glslc)` y genera un helper de shaders; en cross-compilación hay que separar explícitamente el `glslc`/generador ejecutable en el host de los headers y `libvulkan` target de `arm64-v8a` del NDK. Los paths exactos dependen de la instalación NDK/SDK.

```bash
cmake -S <llama.cpp-fijado> -B <build-arm64-vulkan> \
  -DCMAKE_TOOLCHAIN_FILE=<ANDROID_NDK>/build/cmake/android.toolchain.cmake \
  -DANDROID_ABI=arm64-v8a \
  -DANDROID_PLATFORM=android-29 \
  -DGGML_NATIVE=OFF -DGGML_OPENMP=OFF -DGGML_LLAMAFILE=OFF \
  -DLLAMA_OPENSSL=OFF -DGGML_VULKAN=ON -DGGML_BACKEND_DL=ON \
  -DVulkan_GLSLC_EXECUTABLE=<host-vulkan-sdk>/Bin/glslc[.exe]
```

Si CMake no resuelve Vulkan target con el sysroot del NDK, habrá que pasar explícitamente los headers y `libvulkan.so` Android y configurar el toolchain del generador de shaders del host (`GGML_VULKAN_SHADERS_GEN_TOOLCHAIN`). No usar el loader de Windows o Linux del SDK como biblioteca Android. Construir y validar primero en un único dispositivo/API/GPU; consultar Vulkan 1.1, `vkEnumeratePhysicalDevices`, FP16, subgroup, límites de buffers/memoria y salida real de `ggml-vulkan`.

### Matriz de aceptación a medir

1. Windows: misma build y API del demo con Vulkan y CUDA; comparar tamaño del conjunto de archivos distribuibles por dependencia real, carga, primer token, tokens/s, RSS/VRAM y contrato de salida.
2. Android: `arm64-v8a` con API 29+; al menos una GPU Qualcomm Adreno y una GPU de otro proveedor si se busca compatibilidad amplia. Medir install/first-run, RAM del proceso, memoria del dispositivo, térmicas/sostenido, tokens/s, crashes del driver y fallback CPU.
3. En ambas plataformas, abrir/generar con cada cuantización objetivo de **LFM2.5, Qwen3.5 y Gemma 4**. Confirmar por separado carga GGUF, offload real, operaciones Vulkan ejecutadas y respuesta estructurada válida. No asumir compatibilidad de familia/cuanti ni rendimiento por el hecho de que compile.

## Fuentes primarias

- [llama.cpp release b11457](https://github.com/ggml-org/llama.cpp/releases/tag/b11457)
- [llama.cpp release nightly b12144](https://github.com/ggml-org/llama.cpp/releases/tag/b12144)
- [llama.cpp latest stable release](https://github.com/ggml-org/llama.cpp/releases/latest)
- [llama.cpp build guide al commit fijado](https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/docs/build.md)
- [llama.cpp backend scheduler al commit fijado](https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/ggml/src/ggml-backend.cpp)
- [llama.cpp Android build guide al commit fijado](https://github.com/ggml-org/llama.cpp/blob/5ad1c5da0ad7f6176256b823925aad19134f0263/docs/android.md)
- [llama.android sample al commit fijado](https://github.com/ggml-org/llama.cpp/tree/5ad1c5da0ad7f6176256b823925aad19134f0263/examples/llama.android)
- [Android NDK stable APIs](https://developer.android.com/ndk/guides/stable_apis)
- [Android Vulkan: engines nativos, requisitos y detección](https://developer.android.com/games/develop/vulkan/native-engine-support)
- [Android PackageManager: niveles Vulkan hardware/compute](https://developer.android.com/reference/android/content/pm/PackageManager)
- [Android memory management](https://developer.android.com/topic/performance/memory-management)
- [Khronos Vulkan Loader: instalación y distribución](https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderApplicationInterface.md)
