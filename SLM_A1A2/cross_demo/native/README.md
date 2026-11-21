# Native llama.cpp bridge

This folder contains the C ABI bridge, its CMake project, and platform runtime artifacts for the cross-platform writing demo. Version 0.1.4 builds against llama.cpp b12359 from `../../tools/llama.cpp/llama.cpp-b1b770d90d94cad9e9ea5b993bdbc383a522fb28`.

- Windows x64 DLLs stage under `artifacts/b12359/win-x64`.
- Android CPU/core libraries stage under `artifacts/b12359/android-arm64-v8a` and `artifacts/b12359/android-x86_64`. The Vulkan plugin is arm64-only.
- Build trees, downloaded headers, and binary artifacts are ignored by Git.

See the [WritingApp.Native build instructions](../WritingApp.Native/README.md) for commands and ABI behavior and the [0.1.4 report](../docs/llama_cpp_turnip_20261113.md) for provenance, validation, and the separate Turnip experiment.

Android 0.1.5 uses `tools/inference_worker.cpp` as a packaged PIE executable named `libwriting_worker.so`. Build it with `scripts/build_android_worker.ps1`. The app launches it from Android's extracted native library directory with a private loader environment. `TURNIP_MANIFEST.json` pins every driver dependency. `scripts/package_turnip_runtime.ps1 -LibraryDirectory <verified-library-directory>` builds the driver asset from those files. Third-party notices stage under `artifacts/b12359/turnip-notices/` and are included in the APK. [Measured Android backend and tests](../docs/android_measured_backend_20261117.md).

`BUILD_MANIFEST.md` records the initial 0.1.0 capture. Android 0.1.1 adds a loader/physical-device version preflight and lazy CPU/Vulkan initialization; the [phone-fix report](../docs/android_phone_load_fix_20261109.md) and [updated hashes](../manifests/android_phone_fix_verification_20261109.json) describe that update. The original Android runtime set is retained locally under `artifacts/v0.1.0-snapshot/`; the original source is recoverable from Git commit `1d36ed7`. Upstream llama.cpp sources and the Vulkan plugin were not patched for this fix.

Version 0.1.2 introduced ABI2, runtime-scored Android ARM variants, an interactive JSON grammar, and performance metrics. The pre-update native set is retained under `artifacts/v0.1.1-snapshot/`. [0.1.2 report](../docs/mobile_downloads_and_runtime_20261109.md), [artifact and source hashes](../manifests/mobile_update_verification_20261109.json).
