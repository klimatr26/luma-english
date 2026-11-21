# Android 0.1.1: cierre al cargar LFM y comprobación en teléfono

Fecha: 9 de noviembre de 2026. Corrección posterior a la entrega inicial `1d36ed7`, realizada sin subagentes. Se actualizaron el puente Android y el APK; no se modificaron modelos, prompts, parámetros, la aplicación WinForms ni resultados experimentales.

## Problema y causa comprobada

El usuario informó que el teléfono conectado cerraba la aplicación al cargar LFM2.5 1.2B. Se leyeron los registros existentes antes de modificar nada. Dos cierres a las18:33:31 y18:33:53 (UTC−5) quedaron registrados como **APP CRASH(NATIVE)**, señal11/SIGSEGV y dirección nula; no como una terminación por falta de memoria. El stack sitúa el fallo en `ggml_vk_create_buffer`, dentro de `libggml-vulkan.so`, durante la carga de tensores. La simbolización del offset `0x13de9c8` con el SO original señala `vk::Device::getBufferAddress` de Vulkan-Hpp, que invoca `vkGetBufferDeviceAddress`.

El dispositivo observado es Android13/API33, ARM64, producto POCO/alioth, modeloM2012K11AG, GPU Adreno(TM)650. Un ejecutable de diagnóstico propio, sin modelo, consultó ambas versiones:

| Consulta | Resultado |
|---|---|
| `vkEnumerateInstanceVersion` del loader del sistema | 1.3.0 |
| `VkPhysicalDeviceProperties.apiVersion` de la GPU | **1.1.128** |
| `driverVersion`, entero de implementación | 2149539840 |
| Mínimo del backend llama.cpp b11457 fijado | 1.2 |

El backend fijado comprobaba el mínimo en la versión de instancia/loader, pero ese dato no garantizaba el mínimo de la GPU que terminó usando. La diferencia está prevista por la [guía oficial de versiones de Khronos](https://docs.vulkan.org/guide/latest/versions.html) y la [especificación de `VkPhysicalDeviceProperties`](https://docs.vulkan.org/refpages/latest/refpages/source/VkPhysicalDeviceProperties.html). Los headers recientes o una versión alta del loader no actualizan el controlador físico.

La conclusión se refiere al **controlador actualmente instalado**, no a una imposibilidad permanente de acelerar esa familia de hardware. No se instaló otro controlador ni se cambiaron ajustes de seguridad del teléfono.

## Corrección y comportamiento

- `native/src/android_vulkan_preflight.cpp` abre opcionalmente el loader mediante `dlopen`, consulta su versión, crea una instancia de consulta1.2 y lee la versión de cada GPU física integrada/discreta. Libera la instancia y su referencia al loader antes de retornar. No carga un GGUF ni crea un dispositivo lógico en este preflight.
- La política exige loader y GPU1.2 o superior. Con varias GPU expuestas se bloquea conservadoramente el registro si alguna no cumple: esta revisión de GGML selecciona todas por defecto. Superar la comprobación de versión sigue sin garantizar todas las capacidades o la estabilidad del driver.
- El puente Android carga primero el plugin CPU. **CPU explícita no consulta Vulkan ni carga su plugin**. Vulkan se inicializa de manera diferida solo si se solicita Auto o Vulkan.
- En este teléfono, **Auto carga por CPU**, con un motivo que incluye Adreno650, Vulkan1.1.128 y el mínimo1.2. **Vulkan explícito devuelve `WG_ERROR_BACKEND_UNAVAILABLE` (−2)** antes de tocar el modelo. El motivo llega al error visible de la aplicación.
- El logging nativo Android se dirige al tag `WritingNative`, para poder comprobar backend, buffers y errores por ADB.
- El APK pasa a `versionCode=2`, versión **0.1.1**. Su carpeta propia conserva el APK inicial para trazabilidad. Los scripts de publicación/emulador apuntan a la versión nueva de manera explícita.

El fallback sigue limitado al inicio/carga. No se cambia backend ni se repite una generación por un mal resultado del modelo. Un SIGSEGV arbitrario no puede convertirse en una excepción C# dentro de este proceso; la corrección previene la ruta incompatible identificada. No se afirma que proteja contra cualquier fallo de un controlador futuro.

Los fuentes upstream de llama.cpp y el plugin Vulkan original permanecen sin parches. El core y CPU Android siguen compilados para API26; el plugin ARM64 original sigue enlazado contra API28 y conserva su hash. El preflight no añade una dependencia obligatoria del puente con `libvulkan.so`.

## Validación realizada

| Comprobación | Evidencia y resultado |
|---|---|
| Compilación nativa | Puente/core CPU ARM64 y x86_64, NDK29.0.14206865, `WG_ENABLE_VULKAN=OFF` explícito; éxito |
| Paquete | APK firmado de desarrollo, firmas v2/v3 y alineación verificadas; 15 SO comparados con staging |
| Actualización del teléfono | `adb install -r`: éxito; versión0.1.1; se conserva el GGUF privado existente |
| Carga real por Auto | LFM1.2 Q4_K_M; contexto2048; interfaz y logs confirman CPU y0 capas GPU; sin cierre |
| CPU aislada, puente instalado | Fixture `/dev/null`: devuelve−3 por GGUF inválido; ni `libvulkan.so` ni `libggml-vulkan.so` aparecen en sus mapas |
| Vulkan explícito, puente instalado | Devuelve−2 y motivo de versión física; no se carga el plugin Vulkan |
| Auto con fixture inválido, puente instalado | Alcanza CPU y devuelve−3 por GGUF inválido; no se carga el plugin Vulkan; no se genera texto |
| Política de versiones | 8/8 casos: incluye loader1.3/GPU1.1.128, mínimos1.2, versiones superiores y valores ausentes |
| Fixtures de servicios/UI | 15/15 servicios y4/4 estado de interfaz/exportación |
| Conservación | 24 artefactos Fase1 byte-idénticos; cambios limitados al prototipo y su documentación |

La primera compilación intentó reutilizar una caché ARM64 con Vulkan activado/API26; el guard de CMake la rechazó antes de compilar. Se reconfiguró CPU con `WG_ENABLE_VULKAN=OFF`; se conservaron los logs del intento y de la compilación final. No se sustituyó el core API26 por el de API28.

El teléfono permitió ADB y lectura de UI, pero rechazó `input tap` con `INJECT_EVENTS`. No se intentó habilitar esa capacidad. El usuario desbloqueó el dispositivo, pulsó Cargar modelo y ejecutó el ejemplo desde la interfaz; se capturaron la UI, los logs y el estado del proceso para verificarlo. La prueba es asistida, no una automatización táctil completa.

### Una evaluación de demostración en el teléfono

Se pidió al usuario seleccionar el ejemplo incorrecto de la app y mantener un intento. El usuario confirmó que apareció el resultado. La UI observada contiene:

- Estado **INCONSISTENT**, con explicación de que el modelo marca correcto pero cambia el texto o devuelve errores.
- Texto corregido: `I wake up at seven. I eat breakfast at home.`
- Feedback: `The sentences are clear and correct.`
- Fin de la evaluación tras **un intento**, con advertencia en lugar de una marca concluyente de correcto/incorrecto.

La aplicación no se cerró; el mismo proceso continuó activo después de carga y evaluación. El buffer de crash conservó los dos cierres iniciales y no registró otro de la aplicación durante estas comprobaciones. El resultado contradictorio del modelo se conserva; no se ajustaron prompts/sampling ni se repitió por calidad.

Se conserva evidencia local de la UI y los registros. El checkpoint/RAW sigue en el almacenamiento privado del teléfono; no se exportó a este ordenador durante la corrección. Por ello no se atribuyen un tiempo preciso ni un SHA de sesión exportada a esta evaluación. El snapshot posterior de `dumpsys meminfo` dio PSS1094480KiB y RSS1177420KiB; **no son picos de consumo**. En la carga, llama.cpp informó buffers CPU de694,76MiB para el modelo mapeado, 24MiB para KV y150,02MiB de cómputo; esos buffers tampoco describen toda la memoria del proceso.

Esta corrección añade **una generación de demostración asistida**; las sondas de versiones y de rechazo no generan texto. No se ejecutaron benchmarks de40/120 casos ni se accedió al test final. Los ocho ensayos técnicos de la entrega inicial se mantienen separados.

## Artefactos y reproducción

APK actual: `cross_demo/artifacts/android-0.1.1/org.kevinlima.writinglab-Signed.apk`, 176419040 bytes. Los hashes de APK, fuentes, bibliotecas y evidencia local se registran en [android_phone_fix_verification_20261109.json](../manifests/android_phone_fix_verification_20261109.json). El APK original permanece en `artifacts/android-final/`; los SO originales, en `native/artifacts/v0.1.0-snapshot/`. Los binarios y logs siguen excluidos de Git. La publicación Windows no se reemplazó para esta corrección Android.

Desde `cross_demo`, con el toolchain ya documentado y las cachés nativas existentes:

```powershell
$cmake = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
foreach ($abi in @('arm64-v8a','x86_64')) {
    & $cmake -S native -B "native/build/android-$abi" -DWG_ENABLE_VULKAN=OFF
    if ($LASTEXITCODE) { throw 'Falló la configuración nativa' }
    & $cmake --build "native/build/android-$abi" --target writing_llama_bridge --parallel 2
    if ($LASTEXITCODE) { throw 'Falló la compilación nativa' }
}
.\scripts\android_build.ps1
```

Para configurar desde cero, usar antes la receta NDK/API26 de [WritingApp.Native](../WritingApp.Native/README.md). Mantener el plugin Vulkan ARM64 preparado de API28 al lado del core API26, sin copiar el core de la build Vulkan.

Las sondas son `native/tools/vulkan_dispatch_probe.cpp` y `backend_rejection_probe.cpp`. Se compilan con el Clang del NDK, C++17 y `-static-libstdc++`. La primera enlaza `-lvulkan -ldl`, incluye `native/include` y `native/src`, y compila también `native/src/android_vulkan_preflight.cpp`; `--self-test` ejecuta solo los ocho casos de política. La segunda incluye `native/include` y enlaza únicamente `-ldl`: recibe el `NativeLibraryDir` del paquete instalado y usa ese mismo puente mediante `dlopen`, con `LD_LIBRARY_PATH` apuntando a dicho directorio. Su fixture `/dev/null` no es un modelo y debe ser rechazado. Los temporales de diagnóstico/lectura creados bajo `/data/local/tmp/writinglab-*` se retiraron al terminar; no se eliminó caché ni datos de la app.

La siguiente comprobación de GPU requiere otro teléfono con un controlador Vulkan1.2+ y las capacidades adicionales del backend. Este teléfono, con el controlador observado, debe permanecer en CPU.
