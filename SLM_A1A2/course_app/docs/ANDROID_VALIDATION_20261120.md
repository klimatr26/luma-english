# Luma English 1.1.0 · Android y validación en emulador

Fecha local: 20 de noviembre de 2026, America/Guayaquil. Alcance: portar el curso
final a Android, cambiar la identidad visual y comprobar el funcionamiento antes
de instalarlo en un teléfono. Código: commit `3a15092afbefe72efec5088cf690e8fee0bb57e7`,
rama local `codex/luma-android`. No se configuró un remoto.

## Resultado y entregables

La aplicación se llama **Luma English**, tanto en Windows como en Android. Se
conservan el curso, sus identificadores y los almacenes anteriores. El cambio de
nombre no mueve ni borra modelos, sesiones o progreso. La entrega incluye:

- `artifacts/LumaEnglish-Android-android-arm64-1.1.0.apk`: teléfonos ARM64.
- `artifacts/LumaEnglish-Android-android-x64-1.1.0.apk`: emulador x64, sin arnés.
- `artifacts/LumaEnglish-Windows-x64-1.1.0.zip` y
  `artifacts/windows-1.1.0/LumaEnglish.exe`: Windows actualizado.
- [Evidencia seleccionada](evidence/android-20261120/): informes JSON, resultados
  de pruebas y capturas; los hashes de los APK y bibliotecas están en
  [packages.json](evidence/android-20261120/packages.json).

El APK normal usa configuración Release, no permite depuración y excluye las
actividades de diagnóstico y la instrumentación. Es una distribución directa para
el proyecto, firmada con la clave local de desarrollo anterior; no es una
publicación de tienda. Se verificó que la firma coincide con Writing Lab 0.1.6:
SHA-256 del certificado
`53be4be7642bf02d09439c1bd990f4dd4fc3bacba6804e06d8d9195085851f00`.
El identificador sigue siendo `org.kevinlima.writinglab`, con versión visible
1.1.0 y código 100100. Debe actualizarse sin desinstalar la versión anterior.

## Qué se implementó y por qué

`Course.Android` aloja las mismas bibliotecas `Course.Core` y `Course.UI` que
Windows: tres unidades, 30 actividades cerradas y tres Writing; progreso SQLite,
borradores, historial, exportación JSON/CSV y respaldo/restauración. No se creó
un segundo curso ni un evaluador distinto para móvil.

El host usa los directorios privados persistentes `files/models`, `files/sessions`
y `files/Course/course.db`. No guarda los GGUF definitivos en una carpeta de
caché. Las sesiones del prototipo se conservan; no se convierten en actividades
completadas del curso.

Se reutilizan por enlace los componentes Android de descargas y del motor de la
aplicación anterior. La finalización de descargas depende ahora de un contrato
`IModelDownloadHost`, en lugar de una clase concreta del prototipo. El transporte
y el registro de transferencias aceptan el catálogo de 18 entradas del curso,
incluidas las tres cuantizaciones Qwen 3.5 2B Unsloth. El catálogo anterior de
15 entradas sigue intacto y continúa siendo el valor predeterminado del prototipo.
Se conserva el identificador de las descargas antiguas para poder recuperarlas.

DownloadManager conserva la transferencia cuando se deja de seguir desde la
interfaz. La recuperación del trabajo, la verificación de tamaño/SHA y la
publicación en archivos permanentes mantienen el flujo previamente implementado.
Esta sesión no repitió una descarga de varios GB desde Internet con pantalla
apagada; sí ejecutó las regresiones sintéticas de reanudación, cancelación,
verificación y recuperación, incluida la nueva prueba del catálogo extendido.

Android mantiene el motor aislado, las comparaciones CPU/Vulkan y carga parcial,
los perfiles de calibración y las protecciones de actividad del dispositivo. La
coordinación del curso puede consultar el perfil del adaptador Android sin asumir
que el objeto sea directamente `AdaptiveInferenceEngine`. Las capacidades y la
memoria se consultan de nuevo al recomendar/preparar.

Se reutiliza **b12359-adaptive-v1**: no se modificaron ni recompilaron llama.cpp,
el puente C++ o los controladores. ARM64 incluye el backend Vulkan y el runtime
Turnip retenido, con sus avisos de licencia. x64 usa CPU para inferencia: la sonda
no anuncia Vulkan cuando falta `libggml-vulkan.so`, aunque el emulador pueda
anunciar una GPU virtual para dibujar la interfaz.

## Adaptación de interfaz y correcciones encontradas

- Navegación inferior en ventanas estrechas y disposición según el ancho.
- Respeto de las zonas de las barras del sistema mediante Avalonia.
- Creación de vista por actividad en Avalonia 12, inicialización idempotente y
  suscripciones liberadas al separar la vista. Girar no reinicia los servicios.
- Guardado de borradores al pausar; botón Atrás vuelve por el curso conservando
  el texto. No cancela una descarga por abrir el selector de documentos.
- El teclado real de Android reveló que `AdjustResize` no bastaba con la
  presentación de borde a borde. Ahora se descuenta solamente la zona de teclado
  que solapa la vista y se desplaza el cursor a una región visible. Cabecera,
  estado y navegación inferior ceden espacio mientras se escribe. Si el sistema
  ya redujo la ventana, no se descuenta dos veces la misma zona.
- Se corrigió una notificación ausente de `SelectedModel` al leer preferencias:
  una elección manual podía volver visualmente a Gemma al reiniciar o restaurar.
  La regresión comprueba tanto LFM como Qwen 2B avanzado, en Windows y en la lógica
  compartida de la interfaz.

## Entorno y método

- .NET SDK 11.0.100 GA; workload Android 37.2.31; Avalonia 12.1.5.
- SDK Android 37.0, build-tools 37.0.0 y JDK 21 de Android Studio.
- Emulador Android 36.3.10; imagen instalada Android 16/API 36.1, x86_64.
- AVD separado `Luma_English_API_36_1`, 4096 MiB de RAM y partición de 16 GiB.
- Ejecución sin ventana, sin cargar/guardar snapshots, con WHPX disponible.

El AVD existente tenía una partición de 6 GiB y Android rechazó una actualización
por espacio insuficiente. Se creó otro perfil a partir de su configuración y de
la imagen instalada; no se borraron ni ampliaron sus datos. El nuevo AVD y sus
datos están bajo `artifacts/android-1.1.0/Luma_English.avd`, fuera de Git.

Para verificar la aplicación se compiló una variante x64 `-Automation`, con una
actividad de prueba exportada y depuración habilitada. El controlador Python
rechaza seriales de teléfonos, comprueba que el destino sea un emulador y opera
los controles reales de Avalonia mediante su vista/VM. También usa ADB para
capturar la pantalla, girar mediante la actividad y probar pulsación, teclado,
escritura y borrado reales. Este arnés se excluye del APK normal.

Los mensajes de control y los informes se guardan en archivos privados. El GGUF
se transfirió desde los pesos locales existentes y se importó mediante el
almacén de la aplicación, con verificación completa de SHA-256; no se descargó
otra copia de Internet. En Windows, la entrada binaria de `adb shell` se truncaba
en Ctrl-Z; el controlador usa transporte Base64 y decodificación bajo el UID de
la app. Se comprobó previamente con 1 MiB de datos que contienen los 256 valores
posibles de byte y después con el tamaño y hash del GGUF completo.

Una primera alternativa con `Instrumentation.OnCreate` produjo recursión JNI en
el arnés de .NET; se sustituyó por la actividad de prueba y ADB. Una comprobación
intermedia de borrador también falló después de que gestos manuales tocaran el
teclado y modificaran la entrada de prueba: se repitió el recorrido completo para
restablecer la entrada y verificar de nuevo su persistencia. Esas incidencias no
se contabilizan como resultados de modelos ni como pérdida de datos de la app.

## Resultados de software

| Grupo | Resultado | Cobertura principal |
|---|---:|---|
| Course.Tests | 29/29 | Contenido, claves, SQLite, respaldo, evaluación, recomendación y memoria |
| Course.UiTests | 15/15 | Controles, navegación, tamaños, borradores, teclado, JSON y selección manual persistente |
| WritingApp.Tests | 40/40 | Parser/runtime compartido y transferencias HTTP/sistema, con catálogo extendido |
| Recorrido Android completo | 49/49 comprobaciones | Tres lecciones, 30 respuestas cerradas, giro, importación, motor CPU, historial y respaldo |
| Reinicio e interacción Android | 14/14 comprobaciones | Progreso, modelo conservado, RAW histórico, teclado real, entrada y preferencias |
| APK normales | 2/2 | Firma, identidad, ABI, diagnóstico excluido, bibliotecas y alineación de 16 KiB |

Los recuentos son los de cada grupo, no muestras independientes de precisión
lingüística. El recorrido se repitió durante las correcciones y los ejercicios
cerrados permanecieron en 30 practicados, sin inflar el progreso por repetición.
El fallo de Writing descrito debajo permaneció pendiente. JSON y CSV incluyeron
el historial; restaurar el respaldo recuperó los aciertos y conservó el GGUF.

El APK normal se instaló encima de la variante de pruebas sin desinstalarla y
arrancó correctamente. Se comprobó en pantalla el progreso 30/33 y el modelo
local seleccionado. Después se reinstaló la variante de automatización con la
misma firma y se repitieron las 14 comprobaciones de reinicio: modelo con SHA
verificado, borrador, RAW, progreso, preferencias y teclado permanecieron
correctos. Finalmente se dejó instalado el APK normal. El informe de esta ronda
es [resume-after-release.json](evidence/android-20261120/resume-after-release.json).
La actividad de diagnóstico no pudo abrirse en el APK normal porque no existe
en ese paquete. Esta prueba de actualización corresponde al emulador y a las
variantes 1.1.0; no se presenta como una actualización ya probada en un teléfono
con Writing Lab 0.1.6.

La prueba de teclado comprobó geométricamente que el borde inferior del contenido
queda por encima de su zona: 577.90 DIP en ambos casos, y que el cursor queda
visible. La escritura real de un carácter y su borrado conservaron exactamente
el borrador. Cerrar el teclado restituyó la distribución.

Las comprobaciones de paquete verifican la alineación ZIP y todos los segmentos
ELF `PT_LOAD` de las bibliotecas incluidas para páginas de 16 KiB. Los `.so` del
runtime del proyecto se comparan byte a byte con los activos retenidos. Esto
valida el empaquetado; no sustituye ejecutar ARM64 en un teléfono.

## Inferencia real: resultado y límites

Se realizaron **dos generaciones técnicas** con LFM2.5 1.2B Q4_K_M en CPU, usando
el mismo texto de demostración del curso, seed 42, contexto 2048, máximo 512 tokens
y un intento. La segunda siguió a la corrección de interfaz; no se cambiaron
prompt, gramática o sampling para mejorar su respuesta. No se ejecutó un
benchmark ni se consultaron preguntas de los conjuntos experimentales.

Entrada: `Hello, my name is Sofia. I am a student.`; actividad `u01-writing-01`.
SHA del GGUF:
`b1b3de114215d9507409a662a501a631095a479a419584e8a2ded6304b19b4f5`.

| Ejecución | Motor | Capas GPU | Tiempo del motor | Salida |
|---|---|---:|---:|---|
| Antes de la corrección de teclado | CPU | 0/17 | 15.250 s | JSON legible; contrato `INCONSISTENT` |
| Después de la corrección de teclado | CPU | 0/17 | 14.913 s | JSON legible; contrato `INCONSISTENT` |

El modelo afirmó que la entrada era correcta, pero añadió información en
`corrected_text` —por ejemplo, una ciudad y preferencias no escritas por el
estudiante—. El parser lo rechazó, mostró advertencia y mantuvo el RAW y el
borrador; no mostró ese texto como corrección válida ni completó el Writing.
Por tanto, la integración de seguridad funcionó, pero **estos ejemplos no son
dos respuestas útiles del modelo**. No demuestran precisión de LFM ni de otros
modelos, y no motivan un cambio de parámetros.

El emulador ejecuta instrucciones sobre el PC anfitrión: estos tiempos no
representan un teléfono ni permiten decidir CPU frente a Vulkan móvil. No se
midió consumo energético, VRAM o rendimiento GPU móvil. Los modelos mayores
quedan disponibles en la app, pero no se cargaron en este emulador de 4 GiB.

## Reproducción y siguiente prueba

Desde `SLM_A1A2/course_app`, con los activos locales presentes:

```powershell
.\scripts\android_publish.ps1 -Runtime android-arm64
.\scripts\android_publish.ps1 -Runtime android-x64 -Automation
.\scripts\start_android_emulator.ps1
python scripts/verify_android_emulator.py --serial emulator-5580
python scripts/verify_android_emulator.py --serial emulator-5580 --mode resume
.\scripts\android_publish.ps1 -Runtime android-x64
python scripts/verify_android_packages.py
```

Para repetir el análisis de software, los comandos `dotnet run` del README
generan sus informes con `--report`. La variante de automatización no debe
instalarse como entrega final. Se conserva el AVD para repetir las pruebas sin
alterar el emulador anterior.

La siguiente validación es instalar el APK ARM64 normal como actualización en
un teléfono, confirmar sus modelos anteriores y comprobar interacción, permisos
del selector de archivos, recuperación de descargas y CPU/Vulkan efectivo. La
compatibilidad mínima declarada es API 26; esta sesión ejecutó API 36.1 y no
certifica todas las versiones intermedias, controladores o gestiones de batería.

Se recomprobaron los **24 artefactos de Fase 1** y las **27 vinculaciones SHA**
del manifiesto de finalistas de 200 casos: sin diferencias. No se alteraron
casos, gold, prompts congelados, resultados históricos o activos originales de
llama.cpp. Los APK, GGUF, bases de datos y registros voluminosos siguen fuera de
Git; se guardan fuentes y evidencias técnicas seleccionadas.
También se compararon los **23 blobs del commit inicial** con los mismos archivos:
son idénticos; el ZIP de Fase 1 continúa fuera de Git.

## Fuentes técnicas

- [Despliegue Android de Avalonia](https://docs.avaloniaui.net/docs/deployment/android):
  formato APK y conservación de firma para actualizaciones.
- [Emulador desde línea de comandos](https://developer.android.com/studio/run/emulator-commandline):
  arranque, AVD y opciones de ejecución.
- [IInputPane de Avalonia](https://api-docs.avaloniaui.net/docs/T_Avalonia_Controls_Platform_IInputPane):
  estado y región del teclado. La implementación se contrastó con el paquete
  instalado 12.1.5 y sus referencias; los tests se ejecutan contra ese paquete.
