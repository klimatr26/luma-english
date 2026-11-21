// Read-only capability probe: creates a logical device, but loads no model.
#include <vulkan/vulkan.h>
#include <cstdio>
#include <vector>
#include <cstring>
#include "vulkan_version_policy.h"
#include "android_vulkan_preflight.h"

int main(int argc, char ** argv) {
    if (argc == 2 && std::strcmp(argv[1], "--self-test") == 0) {
        struct test { uint32_t loader, device; bool expected; };
        const test cases[] = {
            {VK_API_VERSION_1_3, VK_MAKE_VERSION(1, 1, 128), false},
            {VK_API_VERSION_1_1, VK_API_VERSION_1_3, false},
            {VK_API_VERSION_1_2, VK_API_VERSION_1_2, true},
            {VK_API_VERSION_1_3, VK_API_VERSION_1_2, true},
            {VK_API_VERSION_1_2, VK_API_VERSION_1_3, true},
            {VK_API_VERSION_1_0, VK_API_VERSION_1_0, false},
            {0, VK_API_VERSION_1_3, false},
            {VK_API_VERSION_1_3, 0, false},
        };
        for (const auto & item : cases) {
            if (writing::supports_vulkan_backend(item.loader, item.device) != item.expected) return 10;
        }
        std::puts("PASS 8/8 Vulkan loader/physical-device version policy cases");
        return 0;
    }
    uint32_t version = VK_API_VERSION_1_0;
    auto enumerate_version = reinterpret_cast<PFN_vkEnumerateInstanceVersion>(
        vkGetInstanceProcAddr(VK_NULL_HANDLE, "vkEnumerateInstanceVersion"));
    if (enumerate_version) enumerate_version(&version);
    std::printf("loader_version=%u.%u.%u\n", VK_VERSION_MAJOR(version), VK_VERSION_MINOR(version), VK_VERSION_PATCH(version));
    const auto unavailable = android_vulkan_unavailable_reason();
    std::printf("writinglab_preflight=%s\n", unavailable.empty() ? "VERSION_CHECK_PASSED" : unavailable.c_str());
    if (version < VK_API_VERSION_1_2) return 2;
    VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
    app.pApplicationName = "WritingLab dispatch probe";
    app.apiVersion = version;
    VkInstanceCreateInfo info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
    info.pApplicationInfo = &app;
    VkInstance instance = VK_NULL_HANDLE;
    if (vkCreateInstance(&info, nullptr, &instance) != VK_SUCCESS) return 3;
    uint32_t count = 0;
    vkEnumeratePhysicalDevices(instance, &count, nullptr);
    std::vector<VkPhysicalDevice> devices(count);
    vkEnumeratePhysicalDevices(instance, &count, devices.data());
    for (auto physical : devices) {
        VkPhysicalDeviceProperties properties{};
        vkGetPhysicalDeviceProperties(physical, &properties);
        std::printf("device=%s api=%u.%u.%u driver=%u\n", properties.deviceName,
            VK_VERSION_MAJOR(properties.apiVersion), VK_VERSION_MINOR(properties.apiVersion),
            VK_VERSION_PATCH(properties.apiVersion), properties.driverVersion);
        if (properties.apiVersion < VK_API_VERSION_1_2) continue;
        VkPhysicalDeviceVulkan12Features features12{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_VULKAN_1_2_FEATURES};
        VkPhysicalDeviceFeatures2 features{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_FEATURES_2};
        features.pNext = &features12;
        vkGetPhysicalDeviceFeatures2(physical, &features);
        std::printf("bufferDeviceAddress=%u\n", features12.bufferDeviceAddress);
        uint32_t queues = 0;
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &queues, nullptr);
        std::vector<VkQueueFamilyProperties> families(queues);
        vkGetPhysicalDeviceQueueFamilyProperties(physical, &queues, families.data());
        uint32_t family = 0;
        while (family < queues && !(families[family].queueFlags & VK_QUEUE_COMPUTE_BIT)) ++family;
        if (family == queues) continue;
        float priority = 1;
        VkDeviceQueueCreateInfo queue{VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO};
        queue.queueFamilyIndex = family; queue.queueCount = 1; queue.pQueuePriorities = &priority;
        VkDeviceCreateInfo device_info{VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO};
        device_info.pNext = &features;
        device_info.queueCreateInfoCount = 1; device_info.pQueueCreateInfos = &queue;
        VkDevice device = VK_NULL_HANDLE;
        const auto result = vkCreateDevice(physical, &device_info, nullptr, &device);
        std::printf("create_device_result=%d\n", result);
        if (result != VK_SUCCESS) continue;
        for (const char* name : {"vkGetBufferDeviceAddress", "vkGetBufferDeviceAddressKHR", "vkCreateBuffer", "vkAllocateMemory"}) {
            std::printf("%s instance=%s device=%s\n", name,
                vkGetInstanceProcAddr(instance, name) ? "present" : "null",
                vkGetDeviceProcAddr(device, name) ? "present" : "null");
        }
        vkDestroyDevice(device, nullptr);
    }
    vkDestroyInstance(instance, nullptr);
}
