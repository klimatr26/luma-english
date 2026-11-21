# Componentes y procedencia

- Avalonia 12.1.5: MIT. https://github.com/AvaloniaUI/Avalonia/tree/12.1.5
- .NET 11 / runtime: MIT y avisos de terceros de Microsoft.
  https://github.com/dotnet/runtime
- Microsoft.Data.Sqlite 11.0.0: MIT; SQLitePCLRaw y su SQLite nativo conservan sus
  licencias/avisos propios. https://www.nuget.org/packages/Microsoft.Data.Sqlite/11.0.0
- llama.cpp b12359, commit `b1b770d90d94cad9e9ea5b993bdbc383a522fb28`: MIT.
  Fuente retenida en el proyecto y recetas de `cross_demo/native`.
  https://github.com/ggml-org/llama.cpp/tree/b1b770d90d94cad9e9ea5b993bdbc383a522fb28

Los GGUF no se distribuyen dentro de la aplicación. Cada entrada del catálogo
indica su fuente fijada, tamaño, SHA-256 y licencia. LFM conserva `lfm1.0`, con sus
condiciones comerciales; no se presenta como Apache/MIT. El catálogo es metadato;
no amplía derechos sobre los pesos.

El paquete de Windows incorpora sus dependencias y archivos LICENSE/NOTICE que
produzca la publicación del SDK. Estos enlaces identifican las fuentes; los
avisos particulares de cada dependencia siguen siendo aplicables.

Android ARM64 incluye además el runtime Turnip/loader y sus avisos ya retenidos
en `cross_demo/native/artifacts/b12359-adaptive-v1/turnip-notices`, empaquetados
en `assets/third-party/`. El APK x64 del emulador usa CPU para inferencia y no
incluye esos controladores ARM64. No se modificó llama.cpp para esta entrega.
