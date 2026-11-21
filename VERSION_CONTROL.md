# Control de cambios local

Este proyecto utiliza Git local, sin remoto configurado ni publicación de datos.
La primera revisión conserva los borradores recibidos y los artefactos pequeños
de la fase de 40 casos; no equivale a aprobar el benchmark de 120.

Se excluyen la junction `SLM_A1A2/models`, checkpoints/GGUF, binarios llama.cpp,
cachés, entorno virtual, credenciales y nuevos RAW/logs de inferencia. Los hashes,
revisiones y recetas de esos activos se guardarán en manifiestos versionados.
Los ZIP originales permanecen en disco, fuera de Git.

Antes de incorporar archivos nuevos:

```powershell
python SLM_A1A2/scripts/check_git_assets.py
git status --short
git diff --check
```

El control rechaza candidatos de más de 10 MiB y formatos de modelos/binarios.
`.gitignore` no puede imponer un límite por tamaño por sí solo. No usar
`git add -f` para sortear estas exclusiones. No publicar un remoto sin revisar
los textos, resultados y cualquier información sensible primero.

## Aplicaciones

Las aplicaciones anteriores (`SLM_A1A2/demo` y `SLM_A1A2/cross_demo`) ya estaban
versionadas. La aplicación final Windows está en `SLM_A1A2/course_app`, con sus
fuentes Avalonia/.NET, contenido, pruebas, scripts, locks de dependencias y
documentación. La implementación se registró en la rama local
`codex/final-course-windows`, sin remoto.

Sus paquetes quedan bajo `course_app/artifacts`, excluidos de Git, y sus bases
personales en el directorio de aplicación del usuario. Los comprobantes pequeños,
hashes y capturas de pruebas están en `course_app/docs`. La extensión del catálogo
pertenece al curso y conserva byte por byte el catálogo ligado al experimento de
200 casos. No se incorporan pesos, binarios ni directorios de RAW/logs técnicos.
La documentación incluye una sesión ficticia del curso exportada desde la UI
para vincular el resultado visible con su JSON original.

Desde el 20 de noviembre de 2026, `course_app/Course.Android` contiene también
el host Android del curso **Luma English**, compartiendo núcleo e interfaz con
Windows. Su implementación y las pruebas automáticas del emulador están en la
rama local `codex/luma-android`. Las evidencias seleccionadas se guardan en
`course_app/docs/evidence/android-20261120`; los APK, el AVD de pruebas y sus datos
privados permanecen bajo `course_app/artifacts`, excluidos del repositorio.
La misma identidad y firma Android permiten actualizar conservando los modelos.

La rama `codex/f8-phone-validation` añade el arnés de teléfono, el controlador
ADB dirigido a un serial explícito y la validación del F8 Pro en Android 17.
Los informes seleccionados están en `course_app/docs/evidence/f8-android17-20261120`;
los respaldos privados del teléfono y sus APK permanecen fuera de Git.
