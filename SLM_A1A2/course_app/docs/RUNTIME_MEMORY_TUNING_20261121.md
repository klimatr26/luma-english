# Luma English 1.1.2 · calibración y propuesta de memoria

21 de noviembre de 2026, America/Guayaquil. Implementación sobre `2bb77b9`.
Esta actualización atiende los hallazgos de la
[validación del F3](F3_ANDROID13_VALIDATION_20261120.md); conserva aquel informe
como registro del comportamiento de 1.1.1.

## Plazos y recuperación de Vulkan

La política compartida pasa a `paired-placement-v2`:

- La CPU conserva un calentamiento y tres muestras. Cada generación GPU recibe
  un plazo de tres veces la mediana CPU, acotado a 20–120 segundos. Sin una
  referencia CPU completa se aplica el límite de 120 segundos.
- La carga de un candidato GPU también queda acotada: su plazo es el mayor de
  30 segundos o el plazo de generación anterior. Continúa el límite total de diez minutos para
  equipos o modelos excepcionalmente lentos; no se presenta como la duración
  habitual de una preparación.
- Un timeout, pérdida del dispositivo o fallo de generación no dispara otra
  prueba casi idéntica con una capa menos. Se conserva el intento y se vuelve
  a CPU o se considera otro adaptador disponible.
- Los fallos de carga y las asignaciones de memoria fallidas siguen permitiendo
  una distribución menor. Se mantiene el máximo de tres candidatos GPU, la
  recuperación parcial y la selección explícita de adaptador/capas.
- Si dos muestras GPU ya superan el umbral de mejora, una tercera no podría
  hacer elegible la mediana de tres: se interrumpe esa ruta y se conservan ambas.
  Una muestra real de formato inutilizable también impide cumplir las tres
  salidas utilizables requeridas. El calentamiento sigue excluido de la mediana.

Los perfiles CPU con una referencia CPU completa y un fallo GPU se reutilizan
hasta 24 horas, en lugar de caducar a los cinco minutos. Si la CPU tampoco se
pudo medir, se mantiene la caducidad corta de cinco minutos. Cambios en modelo,
prompt, sampling, contexto, runtime, controlador o condiciones relevantes
invalidan la identidad; una mejora sustancial del presupuesto GPU vuelve a
evaluar distribuciones restringidas. La acción Recalibrar permite repetir la
comparación archivando el perfil anterior. No se establece una exclusión por SoC.

Cada fallo conserva ahora su fase (`load`, `load-timeout`, `memory`, `timeout`,
`generation`, `slower` o `unusable`). Los RAW completos se guardan antes de
considerar una cancelación posterior a su retorno. No se cambian prompts,
thinking, gramática, semilla, sampling ni presupuesto de tokens.

## Primer plano y pantalla

Durante una calibración nueva, Android comprueba pantalla interactiva e
importancia de proceso de interfaz en primer plano; se comprueba entre llamadas
y mediante un monitor de 500 ms. Si se pierde esa condición, se cancela el
worker y no se guarda una decisión con esos tiempos. La app muestra cómo
reanudar. Las trazas que sí lleguen completas se conservan y señalan si la
condición de primer plano era válida.

La actividad mantiene la pantalla encendida durante preparación/inferencia y
libera esa bandera al terminar o salir de la actividad. La descarga independiente
no solicita esa bandera: continúa con DownloadManager y su ciclo de vida propio.
No se cambiaron ajustes globales de pantalla ni de seguridad.

La distinción se apoya en las APIs de
[importancia de proceso de Android](https://developer.android.com/reference/android/app/ActivityManager.RunningAppProcessInfo):
un servicio en primer plano no equivale a una interfaz activa. Es una protección
de la calibración; la evaluación ordinaria conserva su cancelación y ciclo de
vida existentes.

## Memoria: capacidad, margen inmediato y almacenamiento

La propuesta del curso pasa a `balanced-course-v3`. Se retira el límite fijo del
45 % de RAM total. Tampoco se rebaja el tamaño previsto de Gemma para hacerlo
encajar. El plan calcula:

1. **Trabajo previsto con margen:** estimación anterior por archivo/contexto,
   más el mayor de 256 MiB o el 10 % del GGUF.
2. **Reserva del sistema:** en Android, un cuarto de la RAM total acotado a
   1,25–2 GiB. El trabajo completo debe caber en la capacidad restante. En
   Windows la reserva es un sexto, acotado a 1–4 GiB.
3. **Memoria disponible para preparar:** en Android se exige el mayor de
   768 MiB o trabajo previsto menos archivo de pesos. Se distingue el archivo
   mapeado de los buffers adicionales; no se supone que todo el trabajo deba
   estar libre a la vez ni se promete que la carga vaya a terminar bien. En
   Windows se exige el trabajo completo dentro del 85 % de la memoria disponible.
4. **Espacio de descarga:** Android reserva dos copias más 256 MiB para staging
   y publicación; Windows, una copia más ese margen. Una copia local ya disponible
   no vuelve a reservar espacio de descarga.

La implementación CPU retenida usa la carga mapeada disponible en llama.cpp;
no se modificó ese comportamiento nativo. Véase el
[cargador upstream del commit retenido](https://github.com/ggml-org/llama.cpp/blob/b1b770d90d94cad9e9ea5b993bdbc383a522fb28/src/llama-model.cpp).
Esta separación es una heurística de planificación, no una medición de memoria
anónima ni una garantía de consumo físico o de aceleración GPU.

Se rechaza la preparación automática si la memoria total/disponible es
desconocida o Android informa presión de memoria. La
[API MemoryInfo](https://developer.android.com/reference/android/app/ActivityManager.MemoryInfo)
ofrece memoria disponible y una señal específica de presión; ambas se consultan
sin tratar la cifra disponible como una garantía absoluta.

En el perfil del F3, Gemma pasa de 4,039 a **4,289 GiB de trabajo previsto**,
manteniendo más margen. Se requieren aproximadamente **1,848 GiB disponibles**
y se reservan unos **1,836 GiB para el sistema**. En vez de exigir que 4,289 GiB
estén libres a la vez, se permiten las páginas de pesos mapeadas bajo esas
condiciones. La explicación de la propuesta avisa del margen ajustado. Los
tests mantienen las alternativas MiniCPM/LFM en dispositivos menores y al bajar
la memoria disponible o aumentar el contexto.

Si falla una carga automática, se libera el motor, se conserva una traza del
fallo y se intenta una alternativa menor ya presente que cumpla el plan. No se
descarga otra variante silenciosamente: si falta la copia local, la interfaz
propone el modelo y exige la acción Preparar existente para iniciar su descarga.
No se borran pesos. La elección manual y la cancelación no cambian de modelo.

## Comprobaciones de software y Windows

- Runtime/descargas compartidos: **48/48** tests sintéticos.
- Lógica del curso: **38/38**, incluidos capacidad, presión/contexto, dispositivos
  menores, espacio de staging, fallback acotado, elección manual y cancelación.
- Interfaz Avalonia: **20/20**, con preparación/inferencia pendientes que mantienen
  la pantalla activa y descarga que no la mantiene.

En Windows se ejecutó readiness nativa fuera del benchmark con Gemma UD-Q4_K_XL,
contexto 2048: calentamiento y tres muestras por CPU/GPU, dos ejemplos de la
primera unidad y nueva carga para probar caché. RTX 3070, driver observado
617.42. CPU: mediana **13,247 s**; Vulkan: **1,342 s**, 36 capas. Auto conservó
Vulkan. Los ejemplos correcto/incorrecto devolvieron `STRICT` y los veredictos
esperados en aproximadamente **0,91 / 1,13 s**. La carga posterior tardó
**4,529 s**, con la misma clave/fecha y sin nuevas trazas de calibración.

Las salidas de CPU y GPU tuvieron distinta longitud: esos tiempos describen
esta tarea completa, no una comparación de kernels con salida idéntica. No se
atribuyen diferencias con mediciones anteriores solo al código: el driver y las
condiciones observadas también pueden variar.

## Comprobación en el F3

El selector físico propuso Gemma con 1.987.805.184 bytes disponibles, dejó
constancia del margen ajustado y pasó las tres comprobaciones de selección.

La prueba de segundo plano pasó cinco comprobaciones: inició una calibración
CPU, confirmó la petición de pantalla activa, abrió el inicio de Android mediante
un Intent y comprobó la cancelación, ausencia de perfil final y mensaje de
recuperación. No requirió inyectar pulsaciones ni cambiar permisos. Una
precondición posterior rechazó iniciar otro ensayo con el teléfono bloqueado;
se conservó esa incidencia y se esperó al desbloqueo del usuario.

Con la pantalla desbloqueada se completó la calibración de Gemma y sus siete
comprobaciones, con contexto 2048 y un intento por ejemplo:

| Medida | Resultado de 1.1.2 |
|---|---:|
| CPU, tres muestras de calibración | 21,348 / 20,779 / 20,971 s |
| Mediana CPU | 20,971 s |
| Distribución GPU intentada | 36/36 capas, Turnip Adreno 650, Mesa 26.2.7 |
| Plazo de generación GPU | 62,913 s, derivado de la CPU |
| Resultado GPU | timeout; sin repetir con 35 capas |
| Preparación completa, incluida verificación y calibración | 180,024 s |
| Ejemplos correcto / incorrecto, CPU | 21,236 / 26,241 s; ambos `STRICT` |
| Preparación posterior con perfil reutilizado | 13,797 s |

La preparación anterior de 1.1.1 había tardado 501,083 s. Este ensayo confirma
que la nueva política detuvo antes una ruta fallida y no repitió el timeout
con una capa menos. No es una comparación controlada de velocidad del motor:
antes se estimaron 18/17 capas, ahora 36, y cambiaron las condiciones de memoria
y temperatura. No se demuestra una aceleración de Vulkan en este F3; la decisión
comprobada para este modelo continúa siendo CPU.

Una segunda fase verificó el flujo **automático** completo: propuso Gemma,
preparó su copia local en **12,774 s**, reutilizó la misma clave y fecha de perfil
y pasó sus **siete comprobaciones**. Los dos ejemplos devolvieron `STRICT` y
veredictos correcto/incorrecto en **14,045 / 16,590 s**. La carga adicional tardó
13,946 s. No inició otra comparación CPU/GPU. Estas diferencias entre fases no
se atribuyen a una optimización de inferencia: se conservaron modelo, prompt,
semilla y salida de los ejemplos; el estado térmico y las cachés pueden variar.

La recomendación sigue dependiendo de los recursos presentes: durante la fase
de segundo plano propuso MiniCPM con 1.942.999.040 bytes disponibles, ligeramente
por debajo del mínimo calculado para Gemma. El ensayo de cancelación eligió
Gemma manualmente. No se convirtió «F3» o «8 GB» en una regla de selección.

Se recogieron RSS/PSS por proceso aproximadamente cada tres segundos. Durante
la fase automática, exclusivamente CPU, el máximo RSS muestreado del worker
fue **3.297.980 KiB (3,145 GiB)** y el de la interfaz **351.680 KiB (0,335 GiB)**.
Son máximos separados, no simultáneos, y no deben sumarse como consumo físico
exclusivo. RSS puede contar páginas compartidas. En la calibración completa se
observaron también páginas intercambiadas; el resultado no garantiza un margen
equivalente en todos los equipos con la misma RAM. Los registros por fase
permiten distinguir la carga de prueba y la reutilización posterior. En Windows
se registró un máximo de vida del worker de 2.030.313.472 bytes y picos VRAM del
dispositivo de 2.970/3.003 MiB en los ejemplos; esta VRAM incluye otros procesos.

Se restauró mediante actualización el **APK normal ARM64 1.1.2 (100102)** y se
verificaron arranque, actividad principal visible y rechazo de `run-as` por no
ser depurable. La captura final muestra el curso y el resumen sin superposición.
Se conservó el identificador/firma y no se desinstaló ni se vaciaron datos. Antes
de restaurar se registraron los dos GGUF permanentes y se retuvo localmente una
copia de la base personal; las pruebas usaron bases separadas. Tras restaurar,
la protección del APK normal impide volver a leer esa base privada por ADB;
no se afirma una comparación de hashes posterior que no se pudo efectuar.

## Evidencia y reproducción

La [evidencia seleccionada](evidence/runtime-memory-20261121/index.json) contiene
SHA-256 de los informes, pruebas, capturas y metadatos de entrega. Las bases
privadas, los modelos, los binarios y los logs nativos completos permanecen en
`artifacts/` o en sus almacenes locales, fuera de Git.

- [Pruebas compartidas: 48/48](evidence/runtime-memory-20261121/shared-tests.json),
  [curso: 38/38](evidence/runtime-memory-20261121/core-tests.json) e
  [interfaz: 20/20](evidence/runtime-memory-20261121/ui-tests.json).
- [Readiness Windows](evidence/runtime-memory-20261121/windows-native/report.json)
  y [reutilización del perfil](evidence/runtime-memory-20261121/windows-native/cache-check.json).
- F3: [selección](evidence/runtime-memory-20261121/phone/selection/selection.json),
  [cancelación en segundo plano](evidence/runtime-memory-20261121/phone/background/background-guard.json),
  [calibración](evidence/runtime-memory-20261121/phone/gemma-foreground/gemma.json) y
  [flujo automático](evidence/runtime-memory-20261121/phone/automatic/automatic.json).
- [Curso con el APK normal](evidence/runtime-memory-20261121/phone/normal-home.png),
  [identidad instalada](evidence/runtime-memory-20261121/phone/normal-package.json) y
  [verificación de los dos APK de entrega](evidence/runtime-memory-20261121/android-packages.json).

Desde la raíz del repositorio se reproducen los tests y paquetes con:

```powershell
dotnet run --project SLM_A1A2/cross_demo/WritingApp.Tests -c Release
dotnet run --project SLM_A1A2/course_app/Course.Tests -c Release -- --report <carpeta-nueva>/core-tests.json
dotnet run --project SLM_A1A2/course_app/Course.UiTests -c Release -- --report <carpeta-nueva>/ui-tests.json --screenshots <carpeta-nueva>/screenshots
& ./SLM_A1A2/course_app/scripts/windows_publish.ps1
& ./SLM_A1A2/course_app/scripts/android_publish.ps1 -Runtime android-arm64
& ./SLM_A1A2/course_app/scripts/android_publish.ps1 -Runtime android-x64
./SLM_A1A2/.venv/Scripts/python.exe SLM_A1A2/course_app/scripts/verify_android_packages.py
```

La readiness nativa Windows utiliza `Course.Smoke --execute --adaptive-readiness
--output <carpeta-nueva>`. Las fases físicas utilizaron el APK firmado de
automatización y `verify_android_phone.py --serial a508dcc3 --run <id-nuevo>
--mode selection|background-guard|gemma|automatic --output <carpeta-nueva>`;
`--fresh` se utilizó únicamente para la calibración completa de Gemma. El ID es
un destino explícito de esta prueba, no una condición del producto. Cada fase
conserva su propio informe; el runner rechaza sobrescribirlos. Se debe restaurar
siempre el APK normal al terminar y mantener la app visible durante mediciones.
No se necesita una inferencia para comprobar únicamente el selector.

## Alcance

No se alteraron llama.cpp, el puente C++, los binarios de inferencia retenidos,
los GGUF, el curso, el catálogo o los prompts. Los cambios de ejecución son C#
y la instrumentación. Las pruebas 40/120/200 y sus resultados permanecen fuera
de esta ejecución. Se conserva la firma y el identificador Android.
