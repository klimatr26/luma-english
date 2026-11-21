// Line-delimited JSON transport for the Android app's isolated inference process.
#include "writing_llama_bridge.h"
#include "nlohmann/json.hpp"
#include <vulkan/vulkan_core.h>
#include <dlfcn.h>
#include <iostream>
#include <string>
#include <vector>

using json = nlohmann::ordered_json;

int main(int argc, char ** argv) {
    if (argc != 2) return 2;
    void * library = dlopen((std::string(argv[1]) + "/libwriting_llama_bridge.so").c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!library) { std::cerr << dlerror() << '\n'; return 3; }
#define FUNCTION(name) auto name##_fn = reinterpret_cast<decltype(&name)>(dlsym(library, #name)); if (!name##_fn) return 4
    FUNCTION(wg_abi_version); FUNCTION(wg_load); FUNCTION(wg_generate); FUNCTION(wg_unload);
    FUNCTION(wg_free_text); FUNCTION(wg_copy_backend); FUNCTION(wg_copy_device);
    FUNCTION(wg_copy_fallback_reason); FUNCTION(wg_get_last_metrics);
    if (wg_abi_version_fn() != WG_ABI_VERSION) return 5;
    wg_engine * engine = nullptr;
    std::string line;
    while (std::getline(std::cin, line)) {
        json result;
        try {
            const auto request = json::parse(line);
            const std::string op = request.at("op");
            char error[4096]{}, backend[4096]{}, device[4096]{}, fallback[4096]{};
            if (op == "load") {
                if (engine) { wg_unload_fn(engine); engine = nullptr; }
                const auto path = request.at("model_path").get<std::string>();
                const int status = wg_load_fn(path.c_str(), request.at("backend"), request.at("context"),
                                               argv[1], nullptr, &engine, error, sizeof(error));
                if (engine) {
                    wg_copy_backend_fn(engine, backend, sizeof(backend));
                    wg_copy_device_fn(engine, device, sizeof(device));
                    wg_copy_fallback_reason_fn(engine, fallback, sizeof(fallback));
                }
                result = {{"status",status},{"error",error},{"backend",backend},{"device",device},{"fallback",fallback}};
            } else if (op == "generate") {
                if (!engine) throw std::runtime_error("Load a model first.");
                const auto system = request.at("system").get<std::string>();
                const auto user = request.at("user").get<std::string>();
                const auto & s = request.at("sampling");
                char * output = nullptr;
                uint32_t size = 0;
                int32_t finish = -1, prompt = 0, count = 0, decoded = 0, closed = 0;
                double seconds = 0, prefill = 0, decode = 0;
                int status = wg_generate_fn(engine, system.c_str(), user.c_str(), request.at("seed"),
                    s.at("max_tokens"), 1, s.at("temperature"), s.at("top_p"), s.at("top_k"), s.at("min_p"),
                    s.at("repeat_penalty"), s.at("presence_penalty"), s.at("frequency_penalty"),
                    nullptr, &output, &size, &finish, &seconds, error, sizeof(error));
                wg_get_last_metrics_fn(engine, &prompt, &count, &decoded, &prefill, &decode, &closed);
                result = {{"status",status},{"error",error},{"content",output ? std::string(output,size) : ""},
                          {"finish",finish},{"seconds",seconds},{"prompt_tokens",prompt},{"output_tokens",count},
                          {"decoded_tokens",decoded},{"prompt_seconds",prefill},{"decode_seconds",decode},
                          {"closed_thinking",closed != 0}};
                wg_free_text_fn(output);
            } else if (op == "driver") {
                void * vk = dlopen("libvulkan.so", RTLD_NOW | RTLD_LOCAL);
                if (!vk) throw std::runtime_error("No Vulkan loader.");
                auto proc = reinterpret_cast<PFN_vkGetInstanceProcAddr>(dlsym(vk,"vkGetInstanceProcAddr"));
                if (!proc) throw std::runtime_error("No Vulkan entry point.");
                auto create = reinterpret_cast<PFN_vkCreateInstance>(proc(nullptr,"vkCreateInstance"));
                VkApplicationInfo app{VK_STRUCTURE_TYPE_APPLICATION_INFO};
                app.pApplicationName = "Writing Lab capability check";
                app.apiVersion = VK_API_VERSION_1_2;
                VkInstanceCreateInfo info{VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO};
                info.pApplicationInfo = &app;
                VkInstance instance{};
                if (!create || create(&info,nullptr,&instance) != VK_SUCCESS) throw std::runtime_error("No Vulkan 1.2 instance.");
                auto enumerate = reinterpret_cast<PFN_vkEnumeratePhysicalDevices>(proc(instance,"vkEnumeratePhysicalDevices"));
                auto props = reinterpret_cast<PFN_vkGetPhysicalDeviceProperties2>(proc(instance,"vkGetPhysicalDeviceProperties2"));
                auto destroy = reinterpret_cast<PFN_vkDestroyInstance>(proc(instance,"vkDestroyInstance"));
                uint32_t count = 0;
                result = {{"status",-1},{"error","No physical GPU."}};
                if (enumerate && props && enumerate(instance,&count,nullptr) == VK_SUCCESS && count) {
                    std::vector<VkPhysicalDevice> devices(count);
                    if (enumerate(instance,&count,devices.data()) == VK_SUCCESS) {
                        VkPhysicalDeviceDriverProperties driver{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_DRIVER_PROPERTIES};
                        VkPhysicalDeviceProperties2 p{VK_STRUCTURE_TYPE_PHYSICAL_DEVICE_PROPERTIES_2};
                        p.pNext = &driver;
                        props(devices.front(),&p);
                        result = {{"status",0},{"device",p.properties.deviceName},{"vendor",p.properties.vendorID},
                                  {"api",p.properties.apiVersion},{"driver_id",driver.driverID},
                                  {"driver",driver.driverInfo}};
                    }
                }
                if (destroy) destroy(instance,nullptr);
                dlclose(vk);
            } else if (op == "exit") {
                break;
            } else {
                throw std::runtime_error("Unknown operation.");
            }
        } catch (const std::exception & e) {
            result = {{"status",-10},{"error",e.what()}};
        }
        std::cout << result.dump() << std::endl;
    }
    if (engine) wg_unload_fn(engine);
    dlclose(library);
    return 0;
}
