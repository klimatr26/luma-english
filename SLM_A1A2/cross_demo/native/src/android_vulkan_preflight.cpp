#include "android_vulkan_preflight.h"
#include "vulkan_version_policy.h"
#include <vulkan/vulkan_core.h>
#include <dlfcn.h>
#include <memory>
#include <vector>

namespace {
std::string version_text(uint32_t version) {
    return std::to_string(VK_VERSION_MAJOR(version)) + "." +
        std::to_string(VK_VERSION_MINOR(version)) + "." + std::to_string(VK_VERSION_PATCH(version));
}
struct instance_scope {
    VkInstance instance = VK_NULL_HANDLE;
    PFN_vkDestroyInstance destroy = nullptr;
    ~instance_scope() { if (instance && destroy) destroy(instance, nullptr); }
};
}

std::string android_vulkan_unavailable_reason() {
    // Load optionally: Android API 26 and devices without Vulkan must retain CPU.
    std::unique_ptr<void, decltype(&dlclose)> library(dlopen("libvulkan.so", RTLD_NOW | RTLD_LOCAL), dlclose);
    if (!library) return "Android Vulkan loader is unavailable.";
    auto get_proc = reinterpret_cast<PFN_vkGetInstanceProcAddr>(dlsym(library.get(), "vkGetInstanceProcAddr"));
    if (!get_proc) return "Android Vulkan loader has no vkGetInstanceProcAddr.";
    auto enumerate_version = reinterpret_cast<PFN_vkEnumerateInstanceVersion>(get_proc(VK_NULL_HANDLE, "vkEnumerateInstanceVersion"));
    uint32_t loader_version = VK_API_VERSION_1_0;
    if (enumerate_version && enumerate_version(&loader_version) != VK_SUCCESS)
        return "Could not query the Android Vulkan loader version.";
    if (loader_version < writing::vulkan_1_2)
        return "Vulkan loader " + version_text(loader_version) + "; llama.cpp requires Vulkan >= 1.2.";
    auto create = reinterpret_cast<PFN_vkCreateInstance>(get_proc(VK_NULL_HANDLE, "vkCreateInstance"));
    if (!create) return "Android Vulkan loader has no vkCreateInstance.";
    VkApplicationInfo application{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    application.pApplicationName = "WritingLab capability check";
    application.apiVersion = VK_API_VERSION_1_2;
    VkInstanceCreateInfo create_info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    create_info.pApplicationInfo = &application;
    instance_scope scope;
    if (create(&create_info, nullptr, &scope.instance) != VK_SUCCESS)
        return "Could not create a Vulkan 1.2 instance for the capability check.";
    scope.destroy = reinterpret_cast<PFN_vkDestroyInstance>(get_proc(scope.instance, "vkDestroyInstance"));
    auto enumerate = reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(get_proc(scope.instance, "vkEnumeratePhysicalDevices"));
    auto properties = reinterpret_cast<PFN_vkGetPhysicalDeviceProperties>(get_proc(scope.instance, "vkGetPhysicalDeviceProperties"));
    auto properties2 = reinterpret_cast<PFN_vkGetPhysicalDeviceProperties2>(get_proc(scope.instance, "vkGetPhysicalDeviceProperties2"));
    if (!scope.destroy || !enumerate || !properties) return "Required Vulkan capability-query entry points are unavailable.";
    uint32_t count = 0;
    if (enumerate(scope.instance, &count, nullptr) != VK_SUCCESS || count == 0)
        return "Android Vulkan exposes no physical GPU.";
    std::vector<VkPhysicalDevice> devices(count);
    if (enumerate(scope.instance, &count, devices.data()) != VK_SUCCESS)
        return "Could not enumerate Android Vulkan physical devices.";
    bool has_gpu = false;
    for (uint32_t i = 0; i < count; ++i) {
        VkPhysicalDeviceProperties device{};
        properties(devices[i], &device);
        if (device.deviceType != VK_PHYSICAL_DEVICE_TYPE_INTEGRATED_GPU &&
            device.deviceType != VK_PHYSICAL_DEVICE_TYPE_DISCRETE_GPU) continue;
        has_gpu = true;
        // This pinned GGML registry selects all GPUs. Do not expose a mixed
        // registry containing an unsupported GPU which it might select first.
        if (!writing::supports_vulkan_backend(loader_version, device.apiVersion))
            return "GPU " + std::string(device.deviceName) + " reports Vulkan " + version_text(device.apiVersion) +
                "; llama.cpp requires device Vulkan >= 1.2 (loader " + version_text(loader_version) + ").";
        if (properties2 && device.vendorID == 0x5143 && device.deviceID == 0x44050001 && device.driverVersion == 0x80320047) {
            VkPhysicalDeviceDriverProperties driver{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
            VkPhysicalDeviceProperties2 extended{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};
            extended.pNext = &driver;
            properties2(devices[i], &extended);
            // This firmware rejected Q4_K matvec and lost the device with the alternate GPU path.
            if (driver.driverID == VK_DRIVER_ID_QUALCOMM_PROPRIETARY)
                return "El controlador Vulkan Qualcomm 0800.71 del Adreno 830 falló durante la inferencia. Vulkan está deshabilitado para este controlador. Selecciona Auto Vulkan/CPU o CPU.";
        }
    }
    return has_gpu ? std::string{} : "Android Vulkan exposes no integrated or discrete GPU for this backend.";
}
