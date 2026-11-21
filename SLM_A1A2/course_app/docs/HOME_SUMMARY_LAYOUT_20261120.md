# Corrección del resumen de progreso · Luma English 1.1.1

Fecha local: 20 de noviembre de 2026 (America/Guayaquil).
Base: commit `05927dd`, versión 1.1.0. Cambio limitado a presentación,
pruebas de interfaz y distribución de la actualización.

## Problema observado

El usuario identificó un defecto en las capturas del emulador y del POCO F8 Pro:
el detalle «0/0 en la última práctica de cada ejercicio» ocupaba una columna
demasiado estrecha y parecía descolgado del indicador. La barra de progreso
también se dibujaba fuera de su espacio previsto. La revisión visual anterior
había pasado por alto este defecto.

El resumen empleaba un `UniformGrid` de tres columnas en todos los anchos.
Las pruebas anteriores comprobaban la adaptación general y el Writing, pero no
los límites de los textos del resumen. La [captura original del usuario](evidence/home-summary-20261120/before-f8-user.png)
se conserva como evidencia del estado anterior.

## Qué cambió y por qué

- Los tres indicadores tienen tarjetas propias, con valor a la izquierda y
  etiqueta/detalle a la derecha. Cada texto ocupa una fila de altura automática.
- El resumen se apila si su espacio disponible es inferior a 900 DIPs; desde ese
  ancho usa tres columnas. Se mide el área del resumen, descontando de forma
  natural el menú lateral y los márgenes, en lugar del ancho total del dispositivo.
- Las barras se recortan a sus propios límites (`ClipToBounds`), lo que evita
  que el contenido de su plantilla pinte fuera del control.
- Sin respuestas comprobadas, el porcentaje sigue siendo «—» y el detalle pasa
  a «Aún no has comprobado ejercicios.». Con progreso se presenta, por ejemplo,
  «1 de 2 · último intento por ejercicio».

Se conserva el cálculo por último intento de cada ejercicio. No cambian las
claves del curso, el historial, la base SQLite, los modelos, los prompts ni el
runtime nativo. Las cifras de las capturas son datos de pruebas del curso;
**no son puntuaciones de calidad de los modelos**.

## Validación realizada

| Comprobación | Procedimiento | Resultado |
|---|---|---|
| Interfaz Avalonia real, en Windows | Suite headless con renderizado Skia | 17/17 |
| UI16, resumen vacío | Anchos de ventana de 360, 385, 411, 480, 800, 1140, 1160 y 1320 DIPs; texto normal y al 150 % | Sin solapamientos ni desbordes en los textos visibles; cambio de distribución correcto |
| UI17, resumen con progreso | Dos ejercicios con tres intentos, incluido un último intento incorrecto; después las 30 actividades cerradas con clave correcta; cinco anchos | 50 % = 1/2 por último intento, después 100 % = 30/30; geometría correcta |
| Lógica del curso y persistencia | Suite `Course.Tests`, con motor sintético | 29/29 |
| APK normal en emulador | Android 16, imagen API 36.1, ABI x86_64, `emulator-5580`; actualización con `install -r` | Arranque y aplicación en primer plano en ambas orientaciones; capturas revisadas visualmente |
| Compilación | Windows x64 autocontenido; Android ARM64 y x86_64 | Tres paquetes 1.1.1 generados |
| Empaquetado Android | Firma, identidad, versión, ausencia de diagnóstico y depuración, ABI, alineación ZIP/ELF a 16 KiB y hashes del runtime retenido | 2/2 APK correctos |
| Integridad histórica | `verify_phase1_integrity.py` | 24 artefactos de Fase 1 byte-idénticos |

UI16/UI17 comprueban los límites de cada tarjeta y texto, el alto y ancho del
texto renderizado, la separación entre etiqueta y detalle, la posición de la
barra y la distribución según el espacio real. El texto ampliado se aplica a
los controles del resumen; esta prueba no equivale a probar todos los ajustes
de accesibilidad del sistema operativo.

La prueba del emulador usa el APK normal, sin actividades de diagnóstico. No
borra los datos instalados, no modifica respuestas del curso y restaura la
configuración de giro. El progreso 30/33 mostrado allí proviene de la validación
anterior. El script verifica que la app sigue en primer plano y captura la
pantalla; las afirmaciones sobre la geometría proceden de UI16/UI17 y de la
inspección visual, no del script de captura.

En esta corrección se realizaron **cero inferencias de modelos**. No se repitieron
los benchmarks ni las pruebas de rendimiento del teléfono. La versión 1.1.1 se
instaló únicamente en el emulador; la prueba física documentada del F8 Pro sigue
correspondiendo a 1.1.0.

## Capturas y evidencia

- [Resumen vacío, ancho 385 DIPs](evidence/home-summary-20261120/summary-empty-portrait.png).
- [Texto del resumen ampliado al 150 %](evidence/home-summary-20261120/summary-enlarged-portrait.png).
- [Progreso parcial, 1 de 2](evidence/home-summary-20261120/summary-progress-portrait.png).
- [Distribución de escritorio](evidence/home-summary-20261120/summary-practiced-1320.png).
- [APK normal: vertical](evidence/home-summary-20261120/home-summary-portrait.png) y
  [horizontal](evidence/home-summary-20261120/home-summary-landscape.png).
- Resultados [de interfaz](evidence/home-summary-20261120/ui-tests.json),
  [de lógica](evidence/home-summary-20261120/core-tests.json),
  [captura Android](evidence/home-summary-20261120/capture-report.json) y
  [verificación de paquetes](evidence/home-summary-20261120/android-packages.json).

## Reproducción

Desde `SLM_A1A2/course_app`, con el entorno y el runtime ya preparados:

```powershell
dotnet run --project Course.UiTests -c Release -- --report artifacts/summary-fix/ui-tests.json --screenshots artifacts/summary-fix/screenshots
dotnet run --project Course.Tests -c Release -- --report artifacts/summary-fix/core-tests.json
./scripts/windows_publish.ps1
./scripts/android_publish.ps1 -Runtime android-x64
./scripts/android_publish.ps1 -Runtime android-arm64
../.venv/Scripts/python.exe scripts/verify_android_packages.py
./scripts/start_android_emulator.ps1
../.venv/Scripts/python.exe scripts/verify_home_summary_android.py --serial emulator-5580
```

El script de captura requiere el AVD existente de 1080 × 2400 y rechaza números
de serie de teléfonos físicos. Las comprobaciones automatizadas de geometría
no dependen de coordenadas de pantalla.

## Entrega

- Windows: `artifacts/LumaEnglish-Windows-x64-1.1.1.zip`.
- Android ARM64: `artifacts/LumaEnglish-Android-android-arm64-1.1.1.apk`.
- Emulador x86_64: `artifacts/LumaEnglish-Android-android-x64-1.1.1.apk`.

Se conserva el identificador Android `org.kevinlima.writinglab` y la firma local
anterior; la actualización conserva los datos. Los scripts toman la versión de
los proyectos para evitar sobrescribir paquetes anteriores. Los paquetes 1.1.0
y los informes anteriores permanecen intactos. Los binarios se guardan fuera de
Git; [sus SHA-256](evidence/home-summary-20261120/delivery-sha256.json) y la evidencia
seleccionada sí se versionan junto con el código.
