cmake_minimum_required(VERSION 3.21)
project(writing_llama_bridge LANGUAGES C CXX)

set(WG_LLAMA_COMMIT "b1b770d90d94cad9e9ea5b993bdbc383a522fb28")
set(WG_LLAMA_BUILD 12359)
set(LLAMA_CPP_SOURCE "${CMAKE_CURRENT_SOURCE_DIR}/../../tools/llama.cpp/llama.cpp-${WG_LLAMA_COMMIT}"
    CACHE PATH "Path to the pinned llama.cpp checkout")
get_filename_component(_llama_source_name "${LLAMA_CPP_SOURCE}" NAME)
if(NOT EXISTS "${LLAMA_CPP_SOURCE}/include/llama.h" OR NOT _llama_source_name STREQUAL "llama.cpp-${WG_LLAMA_COMMIT}")
    message(FATAL_ERROR "LLAMA_CPP_SOURCE must point to llama.cpp-${WG_LLAMA_COMMIT}. Configure an empty build directory when upgrading the runtime.")
endif()

option(WG_ENABLE_VULKAN "Build the optional Vulkan backend from source (requires Vulkan headers, loader import library, and glslc)" OFF)
set(WG_OFFICIAL_VULKAN_PLUGIN "" CACHE FILEPATH "Optional ggml-vulkan.dll/.so built from the exact pinned llama.cpp commit")
set(WG_ARTIFACT_DIR "${CMAKE_CURRENT_SOURCE_DIR}/artifacts/native-runtime" CACHE PATH "Directory where runtime native assets are staged")
if(ANDROID AND WG_ENABLE_VULKAN)
    # The NDK legacy toolchain reports CMAKE_SYSTEM_VERSION=1.
    set(_android_api "${CMAKE_SYSTEM_VERSION}")
    if(DEFINED ANDROID_PLATFORM_LEVEL)
        set(_android_api "${ANDROID_PLATFORM_LEVEL}")
    endif()
    if(_android_api VERSION_LESS 28)
        message(FATAL_ERROR "Build the Vulkan plugin with Android API 28+ for vkGetPhysicalDeviceFeatures2.")
    endif()
endif()

# llama.cpp requires shared libraries when GGML_BACKEND_DL is enabled. The bridge
# and backend modules are loaded in-process, while plugin choice remains explicit.
set(BUILD_SHARED_LIBS ON CACHE BOOL "Build the llama.cpp core as shared libraries" FORCE)
set(LLAMA_BUILD_COMMON ON CACHE BOOL "Build Jinja chat-template support" FORCE)
set(LLAMA_BUILD_NUMBER "${WG_LLAMA_BUILD}" CACHE STRING "Pinned llama.cpp build number" FORCE)
set(LLAMA_BUILD_COMMIT "${WG_LLAMA_COMMIT}" CACHE STRING "Pinned llama.cpp commit" FORCE)
set(LLAMA_BUILD_TESTS OFF CACHE BOOL "Do not build llama.cpp tests" FORCE)
set(LLAMA_BUILD_EXAMPLES OFF CACHE BOOL "Do not build llama.cpp examples" FORCE)
set(LLAMA_BUILD_TOOLS OFF CACHE BOOL "Do not build llama.cpp tools" FORCE)
set(LLAMA_BUILD_APP OFF CACHE BOOL "Do not build llama.cpp app" FORCE)
set(LLAMA_BUILD_MTMD OFF CACHE BOOL "Do not build multimodal helpers" FORCE)
set(LLAMA_OPENSSL OFF CACHE BOOL "Keep native inference independent of OpenSSL" FORCE)
set(LLAMA_SUBPROCESS OFF CACHE BOOL "Do not build subprocess helpers" FORCE)
set(LLAMA_LLGUIDANCE OFF CACHE BOOL "Do not build optional guidance library" FORCE)
set(GGML_BACKEND_DL ON CACHE BOOL "Build CPU/GPU backends as runtime-loadable modules" FORCE)
set(GGML_CPU ON CACHE BOOL "Build the CPU backend" FORCE)
option(WG_ANDROID_CPU_VARIANTS "Build runtime-scored ARM CPU variants for Android" ON)
if(ANDROID AND CMAKE_ANDROID_ARCH_ABI STREQUAL "arm64-v8a" AND WG_ANDROID_CPU_VARIANTS AND NOT WG_ENABLE_VULKAN)
    set(GGML_CPU_ALL_VARIANTS ON CACHE BOOL "Runtime-scored Android ARM backends" FORCE)
else()
    set(GGML_CPU_ALL_VARIANTS OFF CACHE BOOL "Build only the host CPU backend" FORCE)
endif()
set(GGML_NATIVE OFF CACHE BOOL "Use portable codegen" FORCE)
set(GGML_OPENMP OFF CACHE BOOL "Avoid an extra OpenMP runtime dependency" FORCE)
set(GGML_VULKAN "${WG_ENABLE_VULKAN}" CACHE BOOL "Build Vulkan backend" FORCE)

# The NDK ships SPIRV-Headers as part of its shaderc source tree but does not
# ship a SPIRV-Headers CMake package. Its Vulkan backend still needs the package
# lookup, so provide a tiny config that points at those pinned NDK headers.
if(ANDROID)
    set(SPIRV-Headers_DIR "${CMAKE_CURRENT_SOURCE_DIR}/cmake/android-ndk-spirv" CACHE PATH
        "SPIRV-Headers package metadata backed by the selected Android NDK" FORCE)
endif()

set(CMAKE_RUNTIME_OUTPUT_DIRECTORY "${CMAKE_BINARY_DIR}/bin")

add_subdirectory("${LLAMA_CPP_SOURCE}" "${CMAKE_BINARY_DIR}/llama.cpp" EXCLUDE_FROM_ALL)
if(ANDROID AND TARGET ggml-vulkan)
    # llama.cpp checks for SPIRV-Headers, but this pinned revision does not link
    # the package target. Keep the NDK-bundled headers on the Vulkan plugin's
    # include path explicitly.
    target_link_libraries(ggml-vulkan PRIVATE SPIRV-Headers::SPIRV-Headers)
endif()

add_library(writing_llama_bridge SHARED src/writing_llama_bridge.cpp)
if(ANDROID)
    target_sources(writing_llama_bridge PRIVATE src/android_vulkan_preflight.cpp)
    target_link_libraries(writing_llama_bridge PRIVATE log dl)
endif()
target_compile_features(writing_llama_bridge PRIVATE cxx_std_17)
target_compile_definitions(writing_llama_bridge PRIVATE WRITING_LLAMA_BRIDGE_BUILD)
target_include_directories(writing_llama_bridge
    PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
    PRIVATE "${LLAMA_CPP_SOURCE}/common")
target_link_libraries(writing_llama_bridge PRIVATE llama-common)
set_target_properties(writing_llama_bridge PROPERTIES OUTPUT_NAME writing_llama_bridge)

if(TARGET ggml-cpu)
    add_dependencies(writing_llama_bridge ggml-cpu)
endif()
if(TARGET ggml-vulkan)
    add_dependencies(writing_llama_bridge ggml-vulkan)
endif()

file(MAKE_DIRECTORY "${WG_ARTIFACT_DIR}")
set(_wg_runtime_targets writing_llama_bridge llama llama-common ggml ggml-base ggml-cpu)
set(_wg_arm_variants android_armv8.0_1 android_armv8.2_1 android_armv8.2_2 android_armv8.6_1
    android_armv9.0_1 android_armv9.2_1 android_armv9.2_2)
foreach(_variant IN LISTS _wg_arm_variants)
    if(TARGET "ggml-cpu-${_variant}")
        add_dependencies(writing_llama_bridge "ggml-cpu-${_variant}")
        list(APPEND _wg_runtime_targets "ggml-cpu-${_variant}")
    endif()
endforeach()
if(TARGET ggml-vulkan)
    list(APPEND _wg_runtime_targets ggml-vulkan)
endif()
set(_wg_stage_commands)
foreach(_target IN LISTS _wg_runtime_targets)
    if(TARGET "${_target}")
        list(APPEND _wg_stage_commands
            COMMAND "${CMAKE_COMMAND}" -E copy_if_different "$<TARGET_FILE:${_target}>" "${WG_ARTIFACT_DIR}")
    endif()
endforeach()
if(TARGET ggml-cpu-android_armv8.0_1)
    # Preserve a universally compatible fallback filename for the Android bootstrap.
    list(APPEND _wg_stage_commands COMMAND "${CMAKE_COMMAND}" -E copy_if_different
        "$<TARGET_FILE:ggml-cpu-android_armv8.0_1>" "${WG_ARTIFACT_DIR}/libggml-cpu.so")
endif()
if(ANDROID AND CMAKE_ANDROID_ARCH_ABI AND CMAKE_SYSROOT)
    if(CMAKE_ANDROID_ARCH_ABI STREQUAL "arm64-v8a")
        set(_wg_android_cxx_triple "aarch64-linux-android")
    elseif(CMAKE_ANDROID_ARCH_ABI STREQUAL "armeabi-v7a")
        set(_wg_android_cxx_triple "arm-linux-androideabi")
    elseif(CMAKE_ANDROID_ARCH_ABI STREQUAL "x86")
        set(_wg_android_cxx_triple "i686-linux-android")
    elseif(CMAKE_ANDROID_ARCH_ABI STREQUAL "x86_64")
        set(_wg_android_cxx_triple "x86_64-linux-android")
    endif()
    if(_wg_android_cxx_triple)
        set(_wg_android_cxx_runtime "${CMAKE_SYSROOT}/usr/lib/${_wg_android_cxx_triple}/libc++_shared.so")
        if(EXISTS "${_wg_android_cxx_runtime}")
            list(APPEND _wg_stage_commands
                COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${_wg_android_cxx_runtime}" "${WG_ARTIFACT_DIR}")
        else()
            message(FATAL_ERROR "The selected Android c++_shared runtime was not found: ${_wg_android_cxx_runtime}")
        endif()
    endif()
endif()
if(WG_OFFICIAL_VULKAN_PLUGIN)
    if(NOT EXISTS "${WG_OFFICIAL_VULKAN_PLUGIN}")
        message(FATAL_ERROR "WG_OFFICIAL_VULKAN_PLUGIN does not exist: ${WG_OFFICIAL_VULKAN_PLUGIN}")
    endif()
    list(APPEND _wg_stage_commands
        COMMAND "${CMAKE_COMMAND}" -E copy_if_different "${WG_OFFICIAL_VULKAN_PLUGIN}" "${WG_ARTIFACT_DIR}")
endif()
add_custom_command(TARGET writing_llama_bridge POST_BUILD
    COMMAND "${CMAKE_COMMAND}" -E make_directory "${WG_ARTIFACT_DIR}"
    ${_wg_stage_commands}
    VERBATIM)
