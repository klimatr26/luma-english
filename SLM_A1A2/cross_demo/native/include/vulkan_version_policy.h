#pragma once
#include <cstdint>

namespace writing {
// The loader version does not establish the physical device's API version.
constexpr uint32_t vulkan_1_2 = (1u << 22) | (2u << 12);
constexpr bool supports_vulkan_backend(uint32_t loader, uint32_t physical_device) {
    return loader >= vulkan_1_2 && physical_device >= vulkan_1_2;
}
}
