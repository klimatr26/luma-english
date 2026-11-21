// Integration check for an Android phone with a Vulkan < 1.2 GPU.
// Uses the installed bridge and /dev/null, so it cannot load or generate a model.
#include "writing_llama_bridge.h"
#include <dlfcn.h>
#include <cstdio>
#include <fstream>
#include <sstream>
#include <string>

static bool mapped(const char * name) {
    std::ifstream maps("/proc/self/maps");
    std::ostringstream text;
    text << maps.rdbuf();
    return text.str().find(name) != std::string::npos;
}

int main(int argc, char ** argv) {
    if (argc != 2) return 2;
    const std::string library_path = std::string(argv[1]) + "/libwriting_llama_bridge.so";
    void * library = dlopen(library_path.c_str(), RTLD_NOW | RTLD_LOCAL);
    if (!library) { std::puts(dlerror()); return 3; }
    auto load = reinterpret_cast<decltype(&wg_load)>(dlsym(library, "wg_load"));
    auto abi = reinterpret_cast<decltype(&wg_abi_version)>(dlsym(library, "wg_abi_version"));
    if (!load || !abi || abi() != WG_ABI_VERSION) return 4;
    char error[4096]{};
    wg_engine * engine = nullptr;
    const int cpu = load("/dev/null", WG_BACKEND_CPU, 2048, argv[1], nullptr, &engine, error, sizeof(error));
    std::printf("CPU invalid-GGUF status=%d; vulkan_loader_mapped=%d; vulkan_plugin_mapped=%d\n",
        cpu, mapped("libvulkan.so"), mapped("libggml-vulkan.so"));
    if (cpu != WG_ERROR_MODEL_LOAD || engine || mapped("libvulkan.so") || mapped("libggml-vulkan.so")) return 5;
    const int vulkan = load("/dev/null", WG_BACKEND_VULKAN, 2048, argv[1], nullptr, &engine, error, sizeof(error));
    std::printf("Vulkan status=%d; reason=%s\n", vulkan, error);
    if (vulkan != WG_ERROR_BACKEND_UNAVAILABLE || engine ||
        std::string(error).find("requires device Vulkan >= 1.2") == std::string::npos) return 6;
    const int automatic = load("/dev/null", WG_BACKEND_AUTO_VULKAN_CPU, 2048, argv[1], nullptr, &engine, error, sizeof(error));
    std::printf("Auto invalid-GGUF status=%d; vulkan_plugin_mapped=%d\n", automatic, mapped("libggml-vulkan.so"));
    if (automatic != WG_ERROR_MODEL_LOAD || engine || mapped("libggml-vulkan.so")) return 7;
    std::puts("PASS CPU isolation, explicit Vulkan rejection, and Auto fallback error path; no model generations");
    dlclose(library);
}
