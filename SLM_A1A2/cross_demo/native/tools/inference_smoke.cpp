// One explicit synthetic generation through the packaged C ABI. No case/gold files.
#include "writing_llama_bridge.h"
#include "nlohmann/json.hpp"
#include <dlfcn.h>
#include <fstream>
#include <iostream>
#include <string>

using json = nlohmann::ordered_json;
int main(int argc, char ** argv) {
    if (argc != 2) return 2;
    try {
        std::ifstream input(argv[1]); json spec; input >> spec;
        const auto directory = spec.at("backend_directory").get<std::string>();
        void * library = dlopen((directory + "/libwriting_llama_bridge.so").c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!library) throw std::runtime_error(dlerror());
#define FUNCTION(name) auto name##_fn = reinterpret_cast<decltype(&name)>(dlsym(library, #name)); if (!name##_fn) throw std::runtime_error(#name " missing")
        FUNCTION(wg_abi_version); FUNCTION(wg_load); FUNCTION(wg_generate); FUNCTION(wg_unload);
        FUNCTION(wg_free_text); FUNCTION(wg_copy_backend); FUNCTION(wg_copy_device); FUNCTION(wg_get_last_metrics);
        FUNCTION(wg_copy_fallback_reason);
        if (wg_abi_version_fn() != WG_ABI_VERSION) throw std::runtime_error("ABI mismatch");
        wg_engine * engine = nullptr; char error[4096]{};
        const auto path = spec.at("model_path").get<std::string>();
        const auto requested = spec.value("backend", std::string("cpu"));
        const int32_t preference = requested == "cpu" ? WG_BACKEND_CPU :
            requested == "vulkan" ? WG_BACKEND_VULKAN : WG_BACKEND_AUTO_VULKAN_CPU;
        if (requested != "cpu" && requested != "vulkan" && requested != "auto")
            throw std::runtime_error("backend must be cpu, vulkan, or auto");
        json result = { {"purpose", "SYNTHETIC_DEMO_NOT_BENCHMARK"}, {"input", spec} };
        int status = wg_load_fn(path.c_str(), preference, 2048, directory.c_str(), nullptr, &engine, error, sizeof(error));
        result["load_status"] = status;
        if (status != WG_STATUS_OK) {result["error"] = error; std::cout << result.dump(2) << '\n'; return 3;}
        const auto system = spec.at("system_prompt").get<std::string>();
        const auto user = spec.at("user_prompt").get<std::string>();
        const auto & s = spec.at("sampling");
        char * output = nullptr; uint32_t length = 0; int32_t finish = -1; double seconds = 0;
        status = wg_generate_fn(engine,system.c_str(),user.c_str(),42,512,1,
            s.at("Temperature"),s.at("TopP"),s.at("TopK"),s.at("MinP"),s.at("RepeatPenalty"),
            s.at("PresencePenalty"),s.at("FrequencyPenalty"),nullptr,&output,&length,&finish,&seconds,error,sizeof(error));
        char backend[4096]{}, device[4096]{}, fallback_reason[4096]{};
        wg_copy_backend_fn(engine, backend, sizeof(backend));
        wg_copy_device_fn(engine, device, sizeof(device));
        wg_copy_fallback_reason_fn(engine, fallback_reason, sizeof(fallback_reason));
        result["backend"] = backend;
        result["device"] = device;
        result["fallback_reason"] = fallback_reason;
        result["generation_status"] = status; result["finish_reason"] = finish;
        result["seconds"] = seconds; result["raw"] = output ? std::string(output,length) : "";
        int32_t prompt=0, count=0, decoded=0, closed=0; double prefill=0, decode=0;
        wg_get_last_metrics_fn(engine,&prompt,&count,&decoded,&prefill,&decode,&closed);
        result["metrics"] = { {"prompt_tokens",prompt},{"output_tokens",count},{"decoded_tokens",decoded},
            {"prompt_seconds",prefill},{"decode_seconds",decode},{"closed_thinking_prefill",closed!=0} };
        if(status) result["error"] = error;
        wg_free_text_fn(output); wg_unload_fn(engine); dlclose(library);
        std::cout << result.dump(2) << '\n';
        return status == WG_STATUS_OK ? 0 : 4;
    } catch(const std::exception & error) {std::cerr << error.what() << '\n'; return 5;}
}
