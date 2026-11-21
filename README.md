# Luma English

Aplicación del proyecto de titulación de Kevin Lima: curso básico de inglés con
evaluación de Writing mediante modelos pequeños ejecutados en el dispositivo.
Comparte núcleo e interfaz **Avalonia 12 / .NET 11** entre Windows y Android;
guarda el progreso en SQLite y compara CPU/Vulkan antes de elegir aceleración.

## Empezar

- [Aplicación final: uso, arquitectura, modelos y compilación](SLM_A1A2/course_app/README.md).
- [Anexos: mapa de fuentes, pruebas y resultados](ANEXOS.md).
- [Documentación experimental](SLM_A1A2/documentation/README.md).
- [Paquetes verificados de Windows y Android](https://github.com/klimatr26/luma-english/releases/tag/v1.1.2-thesis).

La entrega de referencia es **1.1.2**. Los paquetes contienen el runtime; los
pesos GGUF se descargan o importan desde la aplicación y se verifican por SHA-256.
El curso funciona sin conexión y, una vez preparado el modelo, también su evaluación.
Los informes distinguen pruebas sintéticas, mediciones reales y revisión humana.
La salida del modelo no constituye una certificación de exactitud lingüística.

## Código y reproducción

`SLM_A1A2/course_app` contiene la aplicación final, sus tests y scripts de publicación.
Depende también de `cross_demo/WritingApp.Shared`, `WritingApp.Native` y del núcleo
del prototipo `demo`; se conservan esas carpetas para resolver las referencias.
Los modelos, SDK, entornos, APK, bases personales y binarios generados no se
guardan como fuentes Git. El [puente nativo](SLM_A1A2/cross_demo/native/README.md)
y los manifiestos identifican los commits y recetas de las dependencias externas.
Compilar el host exige preparar primero ese runtime; clonar este repositorio
por sí solo no instala las herramientas ni genera las bibliotecas nativas.

Los [avisos de terceros](SLM_A1A2/course_app/THIRD_PARTY_NOTICES.md) describen las
dependencias. Las licencias de los modelos siguen siendo independientes; LFM
conserva sus condiciones específicas. No se concede aquí una nueva licencia
general al código propio del proyecto.

## Referencias en el trabajo escrito

Utiliza la etiqueta **`v1.1.2-thesis`** o el SHA completo de un commit para fijar
la versión citada. `CITATION.cff` proporciona los datos básicos de cita y
`ANEXOS.md` muestra enlaces directos a los elementos del proyecto. El repositorio
es privado: los lectores necesitan acceso concedido por su propietario.

La copia de publicación tiene un historial independiente del repositorio de
trabajo. `PUBLICATION_MANIFEST.json` registra el commit local de procedencia y
los hashes de los archivos exportados. Los documentos académicos personales,
la configuración de agentes y los respaldos originales de revisión permanecen
en el entorno local. Las rutas antiguas y referencias a commits locales dentro
de informes históricos se conservan como evidencia, no como enlaces navegables
del historial publicado.
