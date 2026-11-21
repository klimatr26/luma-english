# Native build manifest

Captured 2026-11-09 UTC. This manifest describes the files staged under `artifacts/`; generated binaries, build trees, and downloaded headers remain ignored by Git.

## Source and build settings

- llama.cpp: `5ad1c5da0ad7f6176256b823925aad19134f0263`, build number `11457`; source is the existing checkout at `SLM_A1A2/tools/llama.cpp/llama.cpp-5ad1c5da0ad7f6176256b823925aad19134f0263`.
- ggml source version: `0.26.0`, as recorded by the pinned source's CMake files.
- The generated `ggml-version.h` contains `GGML_COMMIT "6cc3c01"`, but that value is not the upstream ggml revision. The pinned source directory has no `.git`; its CMake runs `git rev-parse --short HEAD` from that directory, which resolves to this workspace's enclosing Git root (`U/IA`, HEAD `6cc3c01655a1e99a8eaf31d508ca08a14bffc4b7`). Treat `6cc3c01` as misleading build-environment metadata, not source provenance. The generated llama `build-info.cpp` correctly reports the explicitly pinned llama.cpp commit above. An independent ggml submodule commit was not established from this extracted source.
- Native bridge sources: `native/src/writing_llama_bridge.cpp` and `native/include/writing_llama_bridge.h`; ABI version 1.
- llama.cpp CMake settings: `BUILD_SHARED_LIBS=ON`, `LLAMA_BUILD_COMMON=ON`, `GGML_BACKEND_DL=ON`, `GGML_CPU=ON`, `GGML_NATIVE=OFF`, `GGML_OPENMP=OFF`, `LLAMA_BUILD_TESTS=OFF`, `LLAMA_BUILD_EXAMPLES=OFF`, `LLAMA_BUILD_TOOLS=OFF`.
- Windows: x64 Release, MSVC toolset 14.51.36231 / compiler 19.51.36260.0. The seven staged DLLs include the bridge, shared llama.cpp core, CPU backend, and the Vulkan plugin described below.
- Android CPU/core: NDK API 26, `c++_shared`, Release; built separately for `arm64-v8a` and `x86_64`.
- Android Vulkan: only `libggml-vulkan.so` is built for `arm64-v8a`, against Android API 28, then copied beside the API-26 CPU/core set. The API-28 build's other libraries are not packaged. `x86_64` is CPU-only.
- Android does not package the NDK's `libvulkan.so` import stub. The Vulkan plugin's `DT_NEEDED` list includes the system `libvulkan.so`.

Native project source hashes:

| File | SHA-256 |
|---|---|
| `native/CMakeLists.txt` | `D63FEA87EC2E5F210AFED96115DA62EEE1D28B1417145E7738738EB07A10B5B4` |
| `native/cmake/android-ndk-spirv/SPIRV-HeadersConfig.cmake` | `E1FD8697E3059E5E85792143C084E9748F66CFFE9D948138F51FC93F20B162A7` |
| `native/include/writing_llama_bridge.h` | `E0ED203404B1B7DA09EC33CFC4AC6B7C46CD86ADFC1A35B73EE26D13E16BBB05` |
| `native/src/writing_llama_bridge.cpp` | `E94C1D426D03C2BBA606DBA23F524018D9A40DB8548190BE1BF0B4A1376AD0C3` |

## Toolchain and dependency pins

| Component | Pin / provenance | SHA-256 |
|---|---|---|
| NDK | `29.0.14206865`, `source.properties` | `716F3518A923198CFAB037ABB32DC3F1B1F7E9A9DCDCDA6B66BE5906215D2658` |
| NDK Android CMake toolchain | `build/cmake/android.toolchain.cmake` | `DBAD92D9DCFEA0D32B7C5E5F82F5072D878DED5D46A5D3F1F581EA108CA7FE89` |
| NDK `clang.exe` | Android clang 21.0.0, based on r563880c | `F2E1B93D9DD27B847773E7DE61B00F1B49AE27EB20BA434297CC020F768A1DFB` |
| NDK `clang++.exe` | Android clang 21.0.0, based on r563880c | `3DA8EB6F49B741AB885854665F10D3793822232F133F8C0233A8A4CB32C97DC0` |
| NDK host `glslc.exe` | shaderc 2022.3; SPIRV-Tools 2022.4; glslang ndk-r28b | `73700734B25DBF4A707F8406D6154E956733885D6E546DC7CB8E66E81BD285C1` |
| Vulkan-Headers | Official KhronosGroup tag [`v1.3.275`](https://github.com/KhronosGroup/Vulkan-Headers/tree/v1.3.275), archive SHA-256 | `2F8B6544E80EE083E11DABDA6B2474B7FF758584107DBA8468903D454A04EF2E` |
| Vulkan-Headers `include/vulkan/vulkan.hpp` | From the official archive above | `2680718D7452870E5B2127B7CBFAFCC2F71AF7DD74106C44D25927698C8B18AC` |
| Vulkan-Headers `include/vulkan/vulkan_core.h` | Version 1.3.275; byte-identical to the NDK header | `3DBA3EF8ADAFF8F24E9080E74D365FC64B5FE53EC8BDA607C29C103E15888FCF` |
| NDK vendored SPIRV-Headers `spirv/unified1/spirv.hpp` | `sources/third_party/shaderc/third_party/spirv-tools/external/spirv-headers/include` | `E4E3A2CADD392141CA9F8B5528D450A39D891526B6CAB25AA578A6E788F7B58D` |
| NDK API-26 arm64 Vulkan stub | Link input for API-26 CPU/core build | `8030A9BBA31D519CE0386C52FDBC81334F6A0AF3B00420CD972EB4003C219E5B` |
| NDK API-28 arm64 Vulkan stub | Link input for optional Vulkan plugin | `8E566E3D309D067BD157FEFD8A4EAAAA83E6EF47A4806F7392374743513ED8B1` |
| CMake | Visual Studio 18 bundled CMake 4.3.1-msvc1 | `87FAFBE6507D4B23C38CCAF72A1859219D070ACB57EF0160332DF10945D2DFAC` |
| Ninja | Visual Studio 18 bundled Ninja 1.13.2 | `9546466F0FECA6D62D7D4EA9B7FBC381F8E302CB7F02F4CE327A39D8577BB293` |
| MSVC host compiler | Toolset 14.51.36231 / compiler 19.51.36260.0 | `B0A1818EBAE6DA7F18230A84E76CE839212584AC4C2AB55B97A0D5268085DA57` |

The Vulkan-Headers archive was downloaded from the official KhronosGroup repository and extracted only into ignored `native/build/deps`. Android's NDK does not include `vulkan.hpp`; `native/cmake/android-ndk-spirv/SPIRV-HeadersConfig.cmake` exposes the NDK-vendored SPIRV-Headers package to the pinned ggml Vulkan build. The native CMake file explicitly links that header target into `ggml-vulkan`.

## Staged runtime file hashes

All hashes below are SHA-256. The Windows `ggml-vulkan.dll` is a byte-for-byte copy of the preserved `SLM_A1A2/tools/llama.cpp/b11457-vulkan/ggml-vulkan.dll` (same hash); root verified it loaded against the staged pinned core during the Windows Vulkan smoke. The existing runtime directory was not modified.

### Windows x64 (`native/artifacts/win-x64`)

| File | Bytes | SHA-256 |
|---|---:|---|
| `ggml-base.dll` | 690,176 | `FECDE27AE315A5BD8C90929D48E2F43026E23F6413B5ACFB23764FC3D262248B` |
| `ggml-cpu.dll` | 1,129,984 | `91CED044C8E695764A22090CAE48A12741B62EF236C00C860FE947F7490CBD3E` |
| `ggml-vulkan.dll` | 45,305,856 | `29E894B75489D149269B8E5A1B0A102B82E58F846322B6EA441D2AF293AEEE74` |
| `ggml.dll` | 62,464 | `9C2B739308D4B2F1615481D350D208708E976B28A1B4A468C037787212631B29` |
| `llama-common.dll` | 8,439,808 | `09E41B13A37455C60D2C769287DF41E2F4A7AAE7A064A0651BB33423C1B43E16` |
| `llama.dll` | 2,786,304 | `6AC37CF91F24A5D509BE7A0093A63CC43193E2491585DE9D6B9A41F77902BF4C` |
| `writing_llama_bridge.dll` | 48,128 | `6D22069209648130C77F449A799C0D5208E54E06A9E84C8D73CBE0C5F9C730A4` |

### Android arm64-v8a (`native/artifacts/android-arm64-v8a`)

| File | Bytes | SHA-256 |
|---|---:|---|
| `libc++_shared.so` | 9,290,184 | `0C52CFAB2DF0D957D8B346A2BDC5AE8D71FECA2591924D77E1CD724D5BF74352` |
| `libggml-base.so` | 5,565,816 | `C594A2F031ED491CCDDA2D7A696F287128D61734A0D546EEA83CF92A1EB464C4` |
| `libggml-cpu.so` | 4,966,072 | `5DA302196578C2A57FB1F762B38095B5753B1396E63FF7970000E9EB543CC836` |
| `libggml-vulkan.so` | 31,334,096 | `0EF0C45EB1F23DFC91C48F477814BAE2ABAC9EF46876E740E87339F722078F9D` |
| `libggml.so` | 471,752 | `E8E89F2C24445F4B4B9CA4C1EDB91C51DBB595A4AB508EF392B440D4FAAD656F` |
| `libllama-common.so` | 69,347,328 | `17D83233E9E58B751D97C07D7A19ADBF30933E45232EF2AA13C153A7475AE1B7` |
| `libllama.so` | 34,888,000 | `23AC530FDD5E8067AE32BC112B3D94B995ACE282E300CCCFE1E4E56142AAF6F8` |
| `libwriting_llama_bridge.so` | 540,072 | `00F3DFBD10C5B726C5891C33FA453CF9EC2327E3108C2394DE1FA8D799413530` |

### Android x86_64 (`native/artifacts/android-x86_64`)

| File | Bytes | SHA-256 |
|---|---:|---|
| `libc++_shared.so` | 9,015,544 | `E28CB9E0F456CAF8498D0E8562B3AC3F73BF78C07555A52B5602396F240ABEC3` |
| `libggml-base.so` | 5,397,832 | `0840ED6174028037609312C3449C04A1D198FF74177B6A76E773862937BE22D6` |
| `libggml-cpu.so` | 4,621,224 | `BE90AEE98083A45626AFB58FF1ED1DA2D8034DE250AB506F24BC0411016E1450` |
| `libggml.so` | 468,136 | `115C079983BC7DF0A287765F290FD993ECC5FDF9E7903909DBE977395C9D4051` |
| `libllama-common.so` | 68,852,600 | `35BACEA482BC54A5066BA4812792136DBC5C2D1285E2569D0A1A2839407ACD8C` |
| `libllama.so` | 34,646,176 | `759AFC30660E9BB34B4AE4188D4CC8C950194DB7A0F0C2F3F7EAEBC90B0B50DF` |
| `libwriting_llama_bridge.so` | 536,912 | `83750B576D5ADA39B01D57829C74310ACCC77F29459FFE669FC70ACE037A1ACA` |

## Verification evidence and limits

- Root's Windows smoke passed CPU and Vulkan load plus one generation after the load-cancellation flag was corrected. This was not a benchmark.
- The Android agent recorded an x86_64 emulator CPU smoke using its existing LFM Q4 model: one generation, 18.65 seconds, zero GPU layers. This was not a benchmark.
- The Android arm64 Vulkan plugin compiled and its dynamic dependencies were inspected. It was not run on a physical Vulkan device; device support and API/driver behavior remain unverified here.
- The Android x86_64 package has no Vulkan plugin and uses CPU.
- `WritingApp.Native` is NativeAOT-friendly by ABI shape, but a NativeAOT publish was not part of this build.
- No weights were downloaded, converted, or generated by the native build.
