if(NOT CMAKE_ANDROID_NDK)
    if(NOT CMAKE_TOOLCHAIN_FILE)
        message(FATAL_ERROR "The Android NDK toolchain must be selected before locating SPIRV-Headers.")
    endif()
    get_filename_component(_wg_ndk_cmake_dir "${CMAKE_TOOLCHAIN_FILE}" DIRECTORY)
    get_filename_component(_wg_ndk_build_dir "${_wg_ndk_cmake_dir}" DIRECTORY)
    get_filename_component(CMAKE_ANDROID_NDK "${_wg_ndk_build_dir}" DIRECTORY)
endif()

set(_wg_spirv_headers "${CMAKE_ANDROID_NDK}/sources/third_party/shaderc/third_party/spirv-tools/external/spirv-headers/include")
if(NOT EXISTS "${_wg_spirv_headers}/spirv/unified1/spirv.hpp")
    message(FATAL_ERROR "SPIRV-Headers were not found in the selected NDK: ${_wg_spirv_headers}")
endif()

if(NOT TARGET SPIRV-Headers::SPIRV-Headers)
    add_library(SPIRV-Headers::SPIRV-Headers INTERFACE IMPORTED GLOBAL)
    set_target_properties(SPIRV-Headers::SPIRV-Headers PROPERTIES
        INTERFACE_INCLUDE_DIRECTORIES "${_wg_spirv_headers}")
endif()

set(SPIRV-Headers_FOUND TRUE)
