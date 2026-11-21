# Writing Lab 0.1.4 y prueba de Mesa Turnip

13 de noviembre de 2026, UTC−5.

## Actualización del motor

La demo Avalonia usa llama.cpp **b12359**, commit `b1b770d90d94cad9e9ea5b993bdbc383a522fb28`, en Windows y Android. Liquid AI documenta la compatibilidad con LFM3-1.7B a partir de b11960 (v0.8.0). b12359 es la compilación nocturna enlazada desde el lanzamiento de v1.0.0. El código fijado registra la arquitectura `lfm3` y la despacha a `llama_model_lfm3`. La prueba con los pesos de LFM3-1.7B queda pendiente para cuando se incorpore al catálogo. [Ficha GGUF de Liquid AI](https://huggingface.co/LiquidAI/LFM3-1.7B-GGUF), [implementación de LFM3](https://github.com/ggml-org/llama.cpp/pull/31252), [lanzamiento v1.0.0](https://github.com/ggml-org/llama.cpp/releases/tag/v1.0.0), [b12359](https://github.com/ggml-org/llama.cpp/releases/tag/b12359).

Se compiló el código fuente publicado por llama.cpp sin parches. El puente de Writing Lab adapta el prompt estructurado de la nueva API a una cadena mediante `chat.prompt.str()`. Mantiene ABI 2, el control de thinking de las plantillas y el formato guiado de la demo. Los artefactos se preparan en `native/artifacts/b12359/` para que cada paquete use el núcleo y los plugins de la misma revisión. El cambio se aplicó al runtime de Avalonia. Los runtimes de los experimentos y WinForms se conservan por separado. [Instrucciones de compilación](../WritingApp.Native/README.md).

- **Windows x64.** CMake y Ninja con MSVC 14.52.37025. El núcleo se compiló localmente y el plugin Vulkan procede del ZIP oficial de b12359. El smoke completó una generación con LFM2.5 1.2B Q4_K_M en CPU y en la RTX 3070 con 17/17 capas en Vulkan. En ambos casos el parser registró `INCONSISTENT` porque el modelo afirmó que el texto era correcto y a la vez lo cambió.
- **Android.** NDK 29.0.14206865 y Clang 21.0.0. CPU y núcleo para ARM64 y x86_64 con API 26. El plugin ARM64 se compiló en un árbol separado con API 28, Vulkan-Headers v1.3.275 y `glslc` del NDK. Se comprobó la firma del APK, la alineación de 16 KiB y la coincidencia de las 22 bibliotecas nativas empaquetadas con las de la compilación. La app arrancó en un emulador x86_64 con Android 16. En el F8 Pro se instaló como actualización, se verificó el SHA-256 del APK instalado y se comprobó el arranque de la actividad principal.
- **Pruebas y trazabilidad.** Pasaron 26/26 comprobaciones compartidas y 4/4 de interfaz. Las pruebas de generación de este informe usaron el ejercicio sintético de la demo. Los logs están en `SLM_A1A2/logs/cross_demo/v014/`. En la compilación desde un tarball, la detección automática del commit de GGML puede encontrar el Git del proyecto externo. La procedencia se fija con el commit de llama.cpp, el hash del tarball y los hashes de los paquetes.

| Artefacto | SHA-256 |
|---|---|
| [Fuente oficial de llama.cpp](https://codeload.github.com/ggml-org/llama.cpp/tar.gz/b1b770d90d94cad9e9ea5b993bdbc383a522fb28) | `ae8556670b17c25931cd39eb7c95617650eaf6091bbcff206750583ddde1acb4` |
| ZIP oficial `llama-b12359-bin-win-vulkan-x64.zip`, cotejado con el digest de GitHub | `e8d18c6e4210cca87e7307c2ea78363ac8d158e4e1397358ec96ab70b53a0d5e` |
| Plugin Windows `ggml-vulkan.dll` | `9cc0d9416bf032caa58af66fc7fe700e35a476b74cab94fcb45e08f4eca8213c` |
| Plugin Android ARM64 `libggml-vulkan.so` | `95880109156f24f826259e5c2504deace910c45dbe5e746245422f0da4091283` |
| `artifacts/windows-0.1.4/WritingApp.Desktop.exe` | `f261f33d95df01b80bbaa37dabf75b711afbf0a69c91b062fb6a5aba7671bb75` |
| `artifacts/android-0.1.4/org.kevinlima.writinglab-Signed.apk`, código 5 | `728030c59a1de163becd36d4033c492899d5355a6914dcbfbae9479af1c47f5e` |

## Por qué Auto eligió CPU con Q8

El POCO F8 Pro probado usa Android 16, HyperOS `OS3.0.302.0.WPKMIXM`, Snapdragon SM8750 y Adreno 830. El controlador del sistema reporta Vulkan 1.3.284 y Qualcomm 0800.71 (`0x80320047`). La versión 0.1.3 incorporó una comprobación de esa combinación de GPU y controlador propietario tras observar fallos de creación de pipelines y pérdida del dispositivo. El puente ejecuta esa comprobación antes de cargar el modelo, así que Q8_0 también entra por CPU. En b12359 se reprodujo la elección de CPU en Auto con LFM2.5 1.2B Q8_0. Se comprobó también el rechazo en modo Vulkan explícito con Q4_K_M. Queda pendiente medir la inferencia Q8 con ese controlador de fábrica. [Diagnóstico anterior del controlador Qualcomm](poco_f8_vulkan_downloads_20261113.md).

## Ensayo de Turnip en el Adreno 830

Se ejecutó `native/tools/inference_smoke.cpp` en un proceso ADB separado con el mismo puente b12359 y su plugin Vulkan para ARM64. El loader Khronos para Android/bionic 1.4.368 se eligió mediante la ruta de bibliotecas del proceso. `VK_DRIVER_FILES` seleccionó un manifiesto local con el ICD de Mesa Turnip 26.2.7. `vulkaninfo` confirmó el dispositivo físico Adreno 830 con `DRIVER_ID_MESA_TURNIP` y Vulkan **1.4.354**. Esta sesión fue independiente del APK y del controlador de fábrica. [Mesa en Android y KGSL](https://docs.mesa3d.org/android.html), [documentación del loader Khronos](https://github.com/KhronosGroup/Vulkan-Loader/blob/main/docs/LoaderDriverInterface.md), [notas de Mesa 26.2.7](https://docs.mesa3d.org/relnotes/26.2.7.html).

Se usaron paquetes de Termux para poder probar un binario de Mesa para Android con KGSL. Se verificó la firma de `InRelease` con la clave `CC72CF8BA7DBFA0182877D045A897D96E57CF20C`, el hash del índice y los SHA-256 de los 23 paquetes extraídos para preparar el ensayo. El manifiesto local `turnip-packages/packages-verified.json` registra todas las versiones y hashes. Se usó una sola `libc++_shared.so` para el proceso. El primer intento con la biblioteca del NDK 29 falló porque el loader de Termux requería `std::__ndk1::__hash_memory`. Dar prioridad a la biblioteca del paquete Termux `libc++_30` permitió ejecutar el loader, Mesa y llama.cpp. Una futura compilación para la app deberá comprobar la compatibilidad de su biblioteca C++ con las tres piezas. [Receta de Mesa de Termux](https://github.com/termux/termux-packages/blob/master/packages/mesa/build.sh).

| Paquete de diagnóstico | SHA-256 |
|---|---|
| `mesa-vulkan-icd-freedreno_26.2.7_aarch64.deb` | `a0af1519b1eae2d32424d3259ccbe7d7e43adf19e226863fa669e682cfcc699e` |
| `vulkan-loader-generic_1.4.368_aarch64.deb` | `8043459b6d4efd4834b756c6eeb539e8ae184d71046ffddff3ca75e85b1fcb27` |
| `libc++_30_aarch64.deb` | `53d0b84a7ba7459024257cb94d5b136fe13ef858567f65a8064b35950799f2ca` |

Con el ejecutable, los pesos verificados y las bibliotecas preparados en un directorio de diagnóstico, el entorno usado para elegir el driver fue el siguiente. El manifiesto local identifica `./libvulkan_freedreno.so`. El diagnóstico de CPU utilizó el mismo ejecutable y solo las bibliotecas del runtime de la app.

```sh
testroot=/data/local/tmp/writinglab-b12359
LD_LIBRARY_PATH="$testroot/turnip:$testroot/runtime" \
VK_DRIVER_FILES="$testroot/turnip/freedreno_icd.json" \
MESA_SHADER_CACHE_DIR="$testroot/turnip-cache" \
    "$testroot/inference_smoke" "$testroot/turnip-q8-input.json"
```

Las cinco generaciones completaron la decodificación y terminaron en `stop`. Se empleó el ejemplo incorrecto A1, contexto 2048, semilla 42, tope 512, gramática JSON y la política de thinking de la demo. El parser compartido validó después cada RAW. Los tiempos son de generación y excluyen carga y verificación del GGUF.

| Modelo | Backend efectivo | Entrada / salida (tokens) | Entrada (s) | Decodificación (s) | Total (s) | Parser |
|---|---|---:|---:|---:|---:|---|
| LFM2.5 1.2B Q4_K_M | Vulkan con Turnip | 301 / 48 | 2,71 | 1,09 | 3,89 | `INCONSISTENT` |
| LFM2.5 1.2B Q8_0 | Vulkan con Turnip | 301 / 52 | 1,28 | 1,30 | 2,70 | `INCONSISTENT` |
| LFM2.5 1.2B Q8_0 | CPU (Auto) | 301 / 52 | 0,92 | 1,14 | 2,08 | `INCONSISTENT` |
| Qwen 3.5 4B Q4_K_M (Unsloth) | Vulkan con Turnip | 714 / 155 | 10,36 | 12,42 | 23,13 | `STRICT` |
| Qwen 3.5 4B Q4_K_M (Unsloth) | CPU (Auto) | 714 / 167 | 17,25 | 12,34 | 29,77 | `STRICT` |

El registro de carga de LFM Q4 mostró 17/17 capas en GPU. El de Qwen confirmó un búfer de cómputo en `Vulkan0`. Los dos resultados Qwen detectaron y corrigieron `I wakes up`. Los tres resultados LFM cambiaron el texto pese a declarar `is_correct=true`. Esa inconsistencia pertenece a la respuesta del modelo. La ganancia observada con Qwen se concentra en el procesamiento de entrada. Estas son observaciones de una generación por fila, con distinta longitud de salida y sin estabilizar la caché del driver. Harían falta repeticiones controladas para elegir un backend por latencia. Los archivos `*-input.json`, `*-result.json` y `*-parsed.json` conservan el protocolo, el RAW y el dictamen del parser. Se retiró del teléfono el directorio temporal del ensayo.

## Viabilidad de integración

**POCO F3.** El Adreno 650 es candidato para Turnip por el soporte de la familia 6xx. En la prueba anterior, su GPU con el controlador de fábrica reportó Vulkan 1.1.128, por debajo del mínimo actual del plugin. La prueba pendiente es cargar el ICD de Turnip para KGSL en ese teléfono y completar una generación. El F3 estuvo desconectado durante este ensayo. [Documentación de Freedreno/Turnip](https://docs.mesa3d.org/drivers/freedreno.html), [medición previa del F3](android_phone_load_fix_20261109.md).

**Aplicación general.** La selección debe partir de la GPU, el controlador que realmente se cargó, las capacidades de cómputo y una prueba breve de generación. Un proceso auxiliar de la app con su propio loader permite evaluar Turnip y aislar un eventual fallo nativo. El controlador del sistema sigue siendo candidato en GPU compatibles y CPU queda disponible cuando la prueba falle. La selección por latencia requiere comparar modelos del catálogo en el dispositivo y registrar el controlador y backend efectivos en la sesión.

**Opciones de carga.** El ensayo por ADB funciona con el loader genérico de Khronos. Para trasladarlo a un APK, primero hay que verificar que el proceso y su namespace pueden resolver todas las llamadas de preflight y GGML contra el mismo loader. Otra opción es que el puente abra el controlador con `libadrenotools` y use el `vkGetInstanceProcAddr` del handle devuelto. En b12359, GGML inicializa el dispatcher con el símbolo enlazado e importa directamente `vkGetPhysicalDeviceFeatures2`, `vkGetDeviceProcAddr` y `vkCmdCopyBuffer`. Inyectar otro dispatcher exigiría resolver esas llamadas de forma coherente. Eso puede requerir un cambio en GGML. La primera validación propuesta es un APK de diagnóstico con una compilación de Mesa acotada a KGSL y dependencias fijadas. Incluir Turnip en Writing Lab queda pendiente de validar esa ruta y su fallback. [Interfaz de libadrenotools](https://github.com/bylaws/libadrenotools/blob/master/include/adrenotools/driver.h), [backend Vulkan fijado](https://github.com/ggml-org/llama.cpp/blob/b1b770d90d94cad9e9ea5b993bdbc383a522fb28/ggml/src/ggml-vulkan/ggml-vulkan.cpp).
