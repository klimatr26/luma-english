# WritingApp.Native

Version 0.1.6 uses `IsolatedInferenceEngine` and the shared `AdaptiveInferenceEngine` on Windows and Android ARM64/API 28+. It estimates and measures explicit GPU/layer placements and CPU, with one child process per candidate. Android x86_64 and API 26–27 retain the in-process CPU adapter. [Current implementation and checks](../docs/adaptive_runtime_20261118.md).

The new flavor is `b12359-adaptive-v1`, built by `scripts/build_adaptive_runtime.ps1`. `writing_runtime_options.h` adds options API version 1 alongside ABI2: runtime probe, explicit adapter ID/index and GPU layer count, total layers and adapter identity. The worker rejects a feature-version mismatch. The frozen source/header and `b12359` runtime remain intact for old experiments. This documentation's in-process sections below describe the retained low-level adapter, rather than Auto's new selection policy.

`NativeInferenceEngine` is an in-process adapter for `WritingApp.Shared.IInferenceEngine`. It passes the canonical system and user prompts to the pinned llama.cpp Jinja chat-template implementation, requests `enable_thinking=false`, uses the model's sampling values and caller seed, and caps generation at 512 tokens. The selected context is passed explicitly (the app chooses 2048 tokens on Android and 4096 on Windows). Model acquisition and SHA-256 verification stay in `ModelStore` before `LoadAsync`.

The adapter uses source-generated `LibraryImport` declarations containing only blittable pointers and scalar values. UTF-8 strings are encoded and decoded by the adapter; there are no marshaled structs, delegates, or managed strings in the native ABI. The optional backend directory defaults to `AppContext.BaseDirectory`; Android bootstrap must pass `ApplicationInfo.NativeLibraryDir`.

## Native bridge

The C ABI is in `../native/include/writing_llama_bridge.h` and the implementation is in `../native/src/writing_llama_bridge.cpp`. Current ABI **2** adds `guided_json` to `wg_generate` and `wg_get_last_metrics`; the managed adapter rejects an ABI mismatch. Handles own their model, context, template state, and cancellation state. All string parameters are NUL-terminated UTF-8; output is allocated by the bridge and released with `wg_free_text`. Do not mix the current managed assemblies with ABI1 native binaries retained in earlier artifact folders.

Backend selection:

- `Cpu` restricts model placement to the CPU backend.
- `Vulkan` requires an available Vulkan backend device and fails during load if none is present or model/context creation fails.
- `AutoVulkanCpu` tries Vulkan first and retries on CPU only while loading the model/context. A failure after a successful Vulkan load is surfaced to the caller and does not trigger a backend switch.

On Android, the bridge loads CPU independently and initializes Vulkan when requested. Before loading the Vulkan plugin, it checks that the loader and each integrated or discrete GPU support Vulkan 1.2 or later. It reports a failed check as Auto's reason for selecting CPU or as an explicit Vulkan error. This prevents the observed Adreno 650 Vulkan 1.1 device from reaching an unavailable `vkGetBufferDeviceAddress` call through a Vulkan 1.3 loader. GGML performs further capability checks. [Phone test and standalone probe commands](../docs/android_phone_load_fix_20261109.md).

The Android check introduced in 0.1.3 also covers the Qualcomm proprietary Adreno 830 driver with device ID `0x44050001` and driver version `0x80320047` (0800.71). On that combination the preflight rejects Vulkan before the bridge reads the GGUF. Auto loads CPU and records the driver diagnosis in the session. [POCO F8 Pro verification](../docs/poco_f8_vulkan_downloads_20261113.md), [Turnip experiment with b12359](../docs/llama_cpp_turnip_20261113.md).

In the retained in-process adapter, `EngineState.OffloadedLayers` is `0` for CPU and may be `-1` (unknown) for Vulkan. The adaptive worker captures the native offload summary and returns the reported count, total and adapter ID; the shared controller rejects a placement that does not match its request.

The prompt uses the model's GGUF chat template through llama.cpp `common_chat_templates_apply` with both `enable_thinking=false` and the matching Jinja keyword. The bridge does not strip reasoning markers from model output. If a template ignores the thinking flag, or a model still returns a `<think>` block, the returned text remains intact and the evaluation/parser must decide whether it is usable; no such output is presented as valid JSON by this engine.

In interactive guided mode, `writing_prompt_policy.h` explicitly closes a trailing `<think>` prefill before decoding; it does not alter the GGUF or remove output. `writing_json_grammar.h` supplies the envelope grammar. The pinned `common_sampler` validates a sampled token first and filters the full vocabulary only on rejection. Seed, penalties, top-k/top-p/min-p and temperature are explicit. Metrics distinguish prompt processing, decoder work, total time and actual output tokens; total time also includes sampling and other overhead. See [the 0.1.2 report](../docs/mobile_downloads_and_runtime_20261109.md).

ARM64 Android CPU builds enable the seven upstream `android_armv*` variants. The bridge checks their baseline-safe `ggml_backend_score` exports, loads the highest compatible score and records its filename. `libggml-cpu.so` is a copy of the baseline armv8.0 build. `WRITINGLAB_CPU_BASELINE=1` is a per-process diagnostic override. `WG_ANDROID_CPU_VARIANTS=OFF` disables the variant build. x86_64 Android and Windows each use a single CPU backend.

## Windows x64 build

Use the b12359 source at `SLM_A1A2/tools/llama.cpp/llama.cpp-b1b770d90d94cad9e9ea5b993bdbc383a522fb28` and the Windows Vulkan archive of the same build. Run the block from this README's directory in an x64 Visual Studio Developer PowerShell with CMake and Ninja available. Verify the two downloads using the recorded SHA-256 values. [Source and binary provenance](../docs/llama_cpp_turnip_20261113.md).

```powershell
Push-Location ..\native
try {
    $archive = (Resolve-Path '..\..\tools\llama.cpp\llama-b12359-bin-win-vulkan-x64.zip').Path
    $pluginDir = (New-Item -ItemType Directory -Force 'build\stage-b12359\windows-upstream').FullName
    tar.exe -xf $archive -C $pluginDir ggml-vulkan.dll
    if ($LASTEXITCODE -ne 0) { throw 'Vulkan plugin extraction failed.' }
    $plugin = Join-Path $pluginDir 'ggml-vulkan.dll'
    $artifacts = Join-Path (Get-Location).Path 'artifacts\b12359\win-x64'
    cmake -G Ninja -S . -B build\b12359-win-x64 -DCMAKE_BUILD_TYPE=Release `
        "-DWG_ARTIFACT_DIR:PATH=$artifacts" -DWG_ENABLE_VULKAN=OFF `
        "-DWG_OFFICIAL_VULKAN_PLUGIN:FILEPATH=$plugin"
    if ($LASTEXITCODE -ne 0) { throw 'Windows native configuration failed.' }
    cmake --build build\b12359-win-x64 --target writing_llama_bridge --parallel 2
    if ($LASTEXITCODE -ne 0) { throw 'Windows native build failed.' }
} finally {
    Pop-Location
}
```

For a from-source Vulkan build, use the Vulkan SDK with `glslc` and SPIR-V headers, set `-DWG_ENABLE_VULKAN=ON` and omit the `WG_OFFICIAL_VULKAN_PLUGIN` argument in a fresh build directory. Windows uses the Vulkan loader and driver installed with the GPU runtime. [llama.cpp build guide](https://github.com/ggml-org/llama.cpp/blob/b1b770d90d94cad9e9ea5b993bdbc383a522fb28/docs/build.md).

## Android native builds

The app packages the bridge, llama.cpp shared libraries, `ggml-cpu`, and the matching `libc++_shared.so` per ABI. Bootstrap passes `ApplicationInfo.NativeLibraryDir` as the backend directory. CPU libraries target Android API 26. Current artifacts are:

- `arm64-v8a` targets API 26 for CPU/core and uses a separate API 28 Vulkan plugin.
- `x86_64` targets API 26 and uses CPU.

The API 28 plugin imports `vkGetPhysicalDeviceFeatures2`, which is available in the NDK Vulkan stub from API 28. Auto loads CPU when the loader rejects the plugin or the device check fails. Stage `libggml-vulkan.so` beside the API 26 arm64 files. Android supplies the Vulkan loader at runtime.

The CPU build recipe below builds both ABIs from the b12359 source. Run it from this README's directory in PowerShell. [0.1.4 build provenance](../docs/llama_cpp_turnip_20261113.md).

```powershell
Push-Location ..\native
$native = (Get-Location).Path
$ndk = Join-Path $env:LOCALAPPDATA 'Android\Sdk\ndk\29.0.14206865'
$cmake = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe'
$ninja = 'C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe'
$toolchain = Join-Path $ndk 'build\cmake\android.toolchain.cmake'

foreach ($abi in @('arm64-v8a', 'x86_64')) {
    $build = Join-Path $native "build\b12359-android-$abi"
    $artifacts = Join-Path $native "artifacts\b12359\android-$abi"
    & $cmake -G Ninja -S $native -B $build `
        "-DCMAKE_MAKE_PROGRAM:FILEPATH=$ninja" `
        "-DCMAKE_TOOLCHAIN_FILE:FILEPATH=$toolchain" `
        "-DANDROID_ABI=$abi" -DANDROID_PLATFORM=android-26 -DANDROID_STL=c++_shared `
        -DCMAKE_BUILD_TYPE=Release "-DWG_ARTIFACT_DIR:PATH=$artifacts" -DWG_ENABLE_VULKAN=OFF
    if ($LASTEXITCODE -ne 0) { throw "CMake configure failed for $abi" }
    & $cmake --build $build --target writing_llama_bridge --parallel 2
    if ($LASTEXITCODE -ne 0) { throw "Native build failed for $abi" }
}
Pop-Location
```

The arm64 Vulkan build needs Vulkan-Headers v1.3.275. Verify its archive and extract it to `native/build/deps/Vulkan-Headers-v1.3.275/Vulkan-Headers-1.3.275`. The build uses the NDK's SPIR-V headers and Windows `glslc` and links against the API 28 Vulkan stub. The temporary drive mapping keeps the shader-generator paths within the Windows toolchain's limit. Run this block in an x64 Visual Studio Developer Command Prompt from `native` with `W:` available. [Header checksum](../native/BUILD_MANIFEST.md).

```bat
set "NATIVE=%CD%"
set "NDK=%LOCALAPPDATA%\Android\Sdk\ndk\29.0.14206865"
set "CMAKE=C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\CMake\bin\cmake.exe"
set "NINJA=C:\Program Files\Microsoft Visual Studio\18\Community\Common7\IDE\CommonExtensions\Microsoft\CMake\Ninja\ninja.exe"
set "VK_HEADERS=%NATIVE%\build\deps\Vulkan-Headers-v1.3.275\Vulkan-Headers-1.3.275\include"
set "NDK_SYSROOT=%NDK%\toolchains\llvm\prebuilt\windows-x86_64\sysroot"
set "TOOLCHAIN=%NDK%\build\cmake\android.toolchain.cmake"
set "GLSLC=%NDK%\shader-tools\windows-x86_64\glslc.exe"
set "VK_LIB=%NDK_SYSROOT%\usr\lib\aarch64-linux-android\28\libvulkan.so"
set "STAGE=%NATIVE%\build\stage-b12359\android-vulkan-api28"
subst W: "%NATIVE%\build"
"%CMAKE%" -G Ninja -S "%NATIVE%" -B W:\b12359-vk "-DCMAKE_MAKE_PROGRAM:FILEPATH=%NINJA%" "-DCMAKE_TOOLCHAIN_FILE:FILEPATH=%TOOLCHAIN%" -DANDROID_ABI=arm64-v8a -DANDROID_PLATFORM=android-28 -DANDROID_STL=c++_shared -DCMAKE_BUILD_TYPE=Release "-DWG_ARTIFACT_DIR:PATH=%STAGE%" -DWG_ENABLE_VULKAN=ON "-DVulkan_INCLUDE_DIR:PATH=%VK_HEADERS%" "-DVulkan_LIBRARY:FILEPATH=%VK_LIB%" "-DVulkan_GLSLC_EXECUTABLE:FILEPATH=%GLSLC%"
"%CMAKE%" --build W:\b12359-vk --target ggml-vulkan --parallel 2 && copy /Y "W:\b12359-vk\bin\libggml-vulkan.so" "%NATIVE%\artifacts\b12359\android-arm64-v8a\"
subst W: /D
```

The API 28 build has its own build tree. The final `copy` stages the plugin in the ARM64 runtime directory prepared by the CPU build. Choose another unused drive letter if `W:` is mapped. Then run `scripts/android_build.ps1` from the app directory to publish.

## References and limitations

- C API and sampler [include/llama.h](https://github.com/ggml-org/llama.cpp/blob/b1b770d90d94cad9e9ea5b993bdbc383a522fb28/include/llama.h), [src/llama-sampler.cpp](https://github.com/ggml-org/llama.cpp/blob/b1b770d90d94cad9e9ea5b993bdbc383a522fb28/src/llama-sampler.cpp).
- Jinja chat-template inputs, including `enable_thinking` [common/chat.h](https://github.com/ggml-org/llama.cpp/blob/b1b770d90d94cad9e9ea5b993bdbc383a522fb28/common/chat.h).
- Dynamic backends [ggml-backend.h](https://github.com/ggml-org/llama.cpp/blob/b1b770d90d94cad9e9ea5b993bdbc383a522fb28/ggml/include/ggml-backend.h).
- Android Vulkan headers [KhronosGroup/Vulkan-Headers v1.3.275](https://github.com/KhronosGroup/Vulkan-Headers/tree/v1.3.275).

Different hardware and drivers can generate different text with the same seed, token limit, context and prompt.
