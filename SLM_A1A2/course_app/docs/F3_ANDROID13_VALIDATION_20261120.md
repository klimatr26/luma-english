# Luma English · POCO F3 con Android 13

Fecha local: 20 de noviembre de 2026, America/Guayaquil. Base de código:
`1d8a2e9` (Luma English 1.1.1). Validación tecnológica de la aplicación final,
sin repetir los benchmarks ni recalificar sus resultados.
Los ajustes posteriores de calibración y memoria se documentan en la
[actualización 1.1.2](RUNTIME_MEMORY_TUNING_20261121.md); este informe conserva
las mediciones originales de 1.1.1.

## Resultado

El curso y la evaluación local funcionan en el POCO F3. Las 63 comprobaciones
físicas de interfaz pasaron, incluidas las 30 claves de actividades cerradas,
teclado, giro, respaldo/restauración y el resumen de progreso corregido. Auto
eligió **CPU para Gemma y MiniCPM** después de los fallos técnicos de Vulkan.

| Modelo, contexto 2048 | Mediana CPU, 3 muestras | Vulkan | Backend elegido |
|---|---:|---|---|
| Gemma 4 E2B UD-Q4_K_XL | 22,487 s | 18/36 y 17/36 capas: ambos calentamientos agotaron 180 s | CPU |
| MiniCPM 5 2B Q4_K_M | 19,988 s | 43/43: `ErrorDeviceLost`; 42/43: calentamiento agotó 180 s | CPU |

No existe una mediana Vulkan válida para estos ensayos. Enumerar la GPU y
cargar pesos no bastó para completar una respuesta. No se modificaron llama.cpp,
el puente C++, Mesa Turnip, los pesos ni los prompts para intentar cambiar ese
resultado. La aplicación conservó el fallback de CPU y mostró el backend real.

En los dos ejemplos de Writing de la primera unidad se obtuvo lo siguiente:

| Modelo / CPU | Ejemplo correcto | Ejemplo incorrecto | Parser y veredictos |
|---|---:|---:|---|
| Gemma | 18,599 s | 19,882 s | `STRICT`, `true` / `false`, ambos utilizables |
| MiniCPM | 41,867 s | 57,551 s | `STRICT`, `true` / `false`, ambos utilizables |

Se revisó el contenido: ambos conservaron el original correcto y corrigieron
«I are twenty-two years old» por «I am twenty-two years old». Gemma presentó
el consejo de estilo del ejemplo correcto como opcional. Son comprobaciones
funcionales de dos entradas pequeñas, sin una estimación nueva de precisión ni
una revisión docente. Los RAW completos de estas cuatro respuestas están en
los informes de modelos enlazados abajo.

La ligera ventaja de MiniCPM en la consigna de calibración no se repitió en las
actividades del curso. Los tokens generados en calibración fueron 237 por
muestra de Gemma y 69 de MiniCPM. En los ejemplos del curso fueron 124/164 y
63/154, respectivamente. Las mediciones describen la espera total de cada tarea;
no aíslan la velocidad de los kernels ni igualan artificialmente las respuestas.

Para este F3 y estos GGUF, **Gemma en CPU es la opción práctica preferida** por
los tiempos observados del Writing y su papel previo en el proyecto. MiniCPM
queda como alternativa. Esto no introduce una lista de dispositivos excluidos
de Vulkan: el resultado sigue vinculado al modelo, contexto, controlador y
runtime probados.

## Equipo, artefactos y conservación

- POCO F3 `M2012K11AG`, dispositivo `alioth`, ARM64; propiedad SoC `SM8250`,
  GPU enumerada como `Turnip Adreno (TM) 650`.
- Android 13 / API 33; firmware
  `POCO/alioth_global/alioth:13/TKQ1.221114.001/V816.0.5.0.TKHMIXM:user/release-keys`.
- RAM informada: 7.886.557.184 bytes (7,345 GiB); disponible al inventariar:
  2.117.615.616 bytes. La memoria disponible varió durante la ejecución.
- Pantalla 1080 × 2400, densidad 440 dpi. Avalonia midió aproximadamente
  360,73 DIPs de ancho útil para el resumen en vertical y 520,36 en horizontal.
- Alimentación USB, ahorro de batería consultado como desactivado. Temperatura
  de batería observada: 29,7–36,2 °C. No se midió energía ni autonomía.
- .NET 11 / Avalonia 12.1.5; runtime retenido `b12359-adaptive-v1`, loader
  Khronos y Mesa Turnip 26.2.7. No se cambiaron ajustes globales de seguridad,
  batería o pantalla.

| GGUF | SHA-256 |
|---|---|
| Gemma UD-Q4_K_XL, 2.620.370.976 bytes | `e531007218dfab990486a5de7676a6932d6ea8dea233d1f698d7c21cf8a16889` |
| MiniCPM Q4_K_M, 1.561.318.368 bytes | `ec2d5801640099e97d8d7e8003ad4d81f336e757811f03a26173dddf386602fd` |

El teléfono tenía Writing Lab 0.1.2, código 3, con Gemma ya descargado y cero
sesiones anteriores. Se respaldó su APK y se comprobó que el certificado es el
mismo de Luma English. Se actualizó con `install -r`, sin desinstalar ni borrar
datos. Gemma conservó tamaño y fecha de modificación y pasó la verificación SHA.
El TAR de las sesiones anteriores resultó byte idéntico antes/después.

MiniCPM se transfirió desde el GGUF ya verificado del ordenador. El envío USB
al directorio externo de la app tardó 45,06 s; la importación y verificación se
hicieron mediante el almacén de la aplicación. Una copia directa bajo `run-as`
fue rechazada por permisos de almacenamiento y un transporte diagnóstico ASCII
más lento se interrumpió. Se retiraron únicamente su parcial de 151.781.376 bytes
y el staging propio, después de verificar el modelo permanente. No se descargó
de nuevo desde Internet ni se sustituyó Gemma.

Las actividades del arnés emplearon
`files/phone-verification/<run>/course-test.db`, con comprobación de que su ruta
es distinta a la base personal. Al regresar a la aplicación personal se observó
el curso sin actividades practicadas. La base personal no existía en el
inventario inicial; su archivo se creó durante el arranque normal. No se afirma
que ese archivo nuevo sea byte idéntico a un archivo anterior.

Al finalizar quedó instalado el **APK normal ARM64 1.1.1, código 100101**, SHA-256
`61cdf85d00a72f0eebbc140f05bdfeb29afb856b092c8034c3e171022c48e8ae`.
ADB confirmó el arranque; el paquete carece de `DEBUGGABLE` y rechaza `run-as`.
El usuario confirmó que veía el curso y se capturó la app en primer plano.
Gemma y MiniCPM quedaron en el almacén permanente.

## Método e incidencias

Los modelos se eligieron manualmente para poder comparar sus backends. La
política de Auto fue la de producción: estimación de capas, calentamiento
excluido de la mediana y tres muestras por ruta completada. Vulkan requiere
tres salidas utilizables y una mejora de al menos el 15 %. Se mantuvieron
contexto 2048, semilla 42, máximo 512 tokens, un intento en los ejemplos, el
sampling propio de cada modelo, thinking desactivado cuando es compatible y
gramática JSON. No se retocaron parámetros según las respuestas.

La preparación completa, incluidos hash, cargas y comparación, tardó
**501,083 s para Gemma** y **286,269 s para MiniCPM**. Esos tiempos no son los
tiempos de evaluación de la tabla: incluyen los intentos Vulkan fallidos.

Se conservaron dos incidencias de instrumentación sin mezclar sus datos con
los resultados aceptados:

1. Tras completar la calibración y los dos ejemplos de Gemma, el arnés quedó
   esperando que el comando de liberar memoria volviera a estar habilitado.
   Ese botón se deshabilita precisamente al terminar. Se detuvo el arnés propio,
   se conservaron checkpoint, historial y muestras, y se corrigió la espera para
   comprobar el estado liberado. **El checkpoint de Gemma no se presenta como un
   informe final con `success=true`.** Su comprobación posterior de caché quedó
   sin medir. El resumen conserva ese estado incompleto de forma explícita.
2. Durante el primer intento de MiniCPM se detectó pantalla apagada y bloqueada.
   Se retuvo ese intento como excluido, se detuvo el proceso propio y, después
   de que el usuario desbloqueara el teléfono, se repitió con un identificador
   nuevo. Se archivaron los perfiles anteriores mediante `--fresh`. No se
   eligieron salidas por calidad. El controlador se endureció para exigir
   pantalla encendida y sin bloqueo antes de medir y comprobar foco, bloqueo y
   estado interactivo cada diez segundos; las 38 observaciones de la repetición
   fueron favorables.

La repetición de MiniCPM pasó sus **7 comprobaciones**, incluida la liberación y
nueva preparación con exactamente la misma clave y fecha de perfil. Esa carga
con caché tardó **12,605 s**, incluidos hash y carga, sin repetir las muestras de
calibración. Una actualización del paquete puede invalidar la huella del runtime.

La interfaz física pasó **63/63**: las 43 comprobaciones de uso existentes más
20 del resumen en vacío, con progreso y al girar/restaurar orientación. El teclado
real se abrió y se comprobó el contenido visible y la introducción/borrado de un
carácter mediante los eventos del control. El teléfono rechazó eventos externos por
ADB con `INJECT_EVENTS`; no se cambió esa protección. La automatización usó los
controles de la propia compilación diagnóstica, excluidos del APK normal.

La regresión headless de Avalonia en Windows pasó **18/18**, con una nueva prueba
del botón de liberar memoria y conservación del GGUF sintético. No son
inferencias. Los 24 artefactos históricos de Fase 1 se verificaron byte idénticos.
Las bases y resultados de los benchmarks 40/120/200 permanecieron intactos.

## Memoria observada

Se sondearon conjuntamente la app y el worker nativo, aproximadamente cada tres
segundos, con el UID propio y `/proc`. Se excluyeron muestras de los primeros
dos segundos posteriores a un cambio de backend. El resumen suma procesos de
cada instante antes de buscar el máximo.

| Modelo/ruta | Pico PSS observado, MiB | Pico RSS observado, MiB | Pico SwapPss observado, MiB |
|---|---:|---:|---:|
| Gemma/CPU | 3120 | 3132 | 147 |
| Gemma/Vulkan, intentos fallidos | 2899 | 2909 | 1972 |
| MiniCPM/CPU | 2918 | 2920 | 116 |
| MiniCPM/Vulkan, intentos fallidos | 1062 | 1118 | 0,24 |

Son máximos de muestras atribuidas, con transitorios que pueden quedar fuera del
sondeo. Los máximos de columnas distintas no tienen por qué ser simultáneos.
**No son el consumo físico total de CPU más GPU ni un pico atribuible de VRAM.**
La memoria GPU del teléfono es compartida; los contadores de proceso no recogen
todas sus asignaciones. No se interpreta el PSS menor de Vulkan como un ahorro
total. El intercambio observado con Gemma coincide con la presión de memoria,
pero no demuestra la causa del bloqueo del driver.

## Descarga con pantalla apagada

Se creó el trabajo técnico **2777** con la URL fijada de LFM 1.2B y un sufijo
único de ejecución, ajeno al catálogo de descargas normales. El usuario apagó la
pantalla porque el teléfono rechazó hacerlo por ADB. Después se detuvo la app.
Las tres observaciones siguientes registraron `Dozing` y ningún PID de la app:

| Hora UTC del 21 de noviembre | Bytes asignados al archivo temporal |
|---|---:|
| 00:37:18,685 | 361.197.568 |
| 00:37:28,948 | 381.796.352 |
| 00:37:39,221 | 442.118.144 |

El archivo creció **80.920.576 bytes asignados** durante ese intervalo sin el
proceso de interfaz. Su tamaño lógico ya era 730.895.168 bytes por preasignación;
no se usó ese tamaño para afirmar que la transferencia estaba completa.

Al reabrir el transporte real se recuperó el mismo ID 2777, aún `Running`, con
**645.131.103 bytes recibidos según DownloadManager**. Pasaron las tres
comprobaciones de reanudación. Se retiró ese trabajo y su archivo temporal; el
directorio de transferencias quedó vacío. No se publicó un LFM adicional en el
almacén ni se tocaron descargas ajenas. Es una prueba corta por USB, sin simular
Doze prolongado ni medir de forma controlada el ancho de banda de la red.

## Ajustes recomendados antes de cerrar la entrega

Estas pruebas dejan tres mejoras concretas para una iteración posterior:

1. **Acortar la calibración cuando falla Vulkan.** En el F3, los plazos
   de 180 s y la segunda distribución apenas menor prolongaron mucho la espera.
   Conviene ligar el plazo a la medida CPU y evitar repetir distribuciones casi
   iguales ante bloqueos de generación, manteniendo trazas y fallback visible.
   La política actual invalida tras cinco minutos los perfiles CPU que contienen
   fallos técnicos; una carga posterior puede repetir esa espera. Elegir CPU
   manualmente ya permite saltarse la comparación.
2. **Proteger la calibración de la aplicación normal frente al segundo plano.**
   El controlador diagnóstico ya descarta esa condición. La política de producto
   necesita detectar una interrupción de primer plano y conservar una decisión
   sin guardar tiempos contaminados. Las descargas deben seguir independientes
   del estado de la pantalla.
3. **Afinar la propuesta de modelo con memoria medida por arquitectura.** El
   estimador actual calcula 4,039 GiB para Gemma y limita el presupuesto al 45 %
   de la RAM total: 3,305 GiB en este F3. Del código se desprende que no puede
   proponer Gemma automáticamente en esa combinación, aunque la selección manual
   aquí funcionó. El PSS CPU observado fue unos 3,05 GiB; por sí solo no garantiza
   el máximo necesario. Hace falta incorporar consumo medido con margen, contexto
   y estado de memoria, sin convertir una prueba en una regla por dispositivo.

Estos ajustes **no se implementaron en el motor de producción en esta sesión**.
Se corrigió y amplió la instrumentación. El curso y los dos modelos se validaron
con las condiciones documentadas. La comparación anterior del
[F8 Pro con Android 17](F8_PRO_ANDROID17_VALIDATION_20261120.md) permanece separada:
las diferencias de firmware, memoria, estado térmico y ejecución impiden atribuir
la diferencia de tiempos únicamente a la generación del SoC.

## Evidencia y reproducción

El [resumen estructurado](evidence/f3-android13-20261120/summary.json) referencia
el [checkpoint original de Gemma](evidence/f3-android13-20261120/gemma-checkpoint.json),
su [incidencia de arnés](evidence/f3-android13-20261120/gemma-harness-interruption.json)
y el [informe completo de MiniCPM](evidence/f3-android13-20261120/minicpm.json).
También se conservan el [recorrido de interfaz](evidence/f3-android13-20261120/ui.json),
la [regresión](evidence/f3-android13-20261120/ui-regression.json), la
[captura del resumen](evidence/f3-android13-20261120/ui-summary.png) y la
[captura final del APK normal](evidence/f3-android13-20261120/normal-course.png).

Los resultados de descarga están en [inicio](evidence/f3-android13-20261120/download-start.json),
[muestreo apagado](evidence/f3-android13-20261120/download-screen-off.jsonl) y
[recuperación](evidence/f3-android13-20261120/download-resume.json). Identidades,
hashes de APK y conservación se recogen en
[device-and-packages.json](evidence/f3-android13-20261120/device-and-packages.json).
Los logs extensos y el resto de datos privados quedan fuera de Git. Una extracción
auxiliar por TAR agotó su plazo de 90 s; no se usa como prueba de un respaldo
completo del teléfono. Se retuvieron los informes y muestras necesarios en el PC;
las trazas de calibración y logs nativos permanecen además en los archivos de la app.

Desde `SLM_A1A2/course_app`, con un teléfono físico desbloqueado y serial explícito:

```powershell
./scripts/android_publish.ps1 -Runtime android-arm64 -Automation
# Instalar el APK de diagnóstico como actualización, con la firma existente.
# Usar identificadores de ejecución nuevos para conservar cada intento.
../.venv/Scripts/python.exe scripts/verify_android_phone.py --serial SERIAL --run RUN-ui --mode ui --output artifacts/phone-run/ui
../.venv/Scripts/python.exe scripts/verify_android_phone.py --serial SERIAL --run RUN-gemma --mode gemma --fresh --output artifacts/phone-run/gemma
../.venv/Scripts/python.exe scripts/verify_android_phone.py --serial SERIAL --run RUN-mini --mode minicpm --fresh --output artifacts/phone-run/minicpm
../.venv/Scripts/python.exe scripts/summarize_phone_phases.py --directory artifacts/phone-run
# Restaurar siempre el APK normal con install -r; nunca desinstalar ni pm clear.
```

`--fresh` archiva perfiles anteriores del modelo/contexto; no elimina trazas.
El resumen acepta un checkpoint interrumpido únicamente cuando existe una
incidencia explícita y conserva `success: null` y `completed_phase_report: false`.
No convierte un checkpoint en una aprobación ni un timeout en una latencia válida.
