// Adaptive successor of the frozen ABI2 bridge. Original source SHA-256: 1ca23cd6dde3552b82731cc63ba3bfa2f38040982faa2fe07e044db3b56e3110
#include "writing_runtime_options.h"
#include "fit.h"
#include "gguf.h"
#include "nlohmann/json.hpp"
#include <cstdio>
#include <climits>

#include "chat.h"
#include "common.h"
#include "sampling.h"
#include "ggml-backend.h"
#include "llama.h"
#include "writing_json_grammar.h"
#include "writing_prompt_policy.h"

#include <algorithm>
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <memory>
#include <mutex>
#include <new>
#include <stdexcept>
#include <string>
#include <utility>
#include <vector>
#if defined(__ANDROID__)
#include "android_vulkan_preflight.h"
#include <android/log.h>
#include <dlfcn.h>
#include <filesystem>
#endif

struct wg_engine {
    llama_model * model = nullptr;
    llama_context * context = nullptr;
    common_chat_templates_ptr templates;
    std::string backend;
    std::string device;
    std::string fallback_reason;
    int32_t offloaded_layers = 0;
    int32_t total_layers = 0;
    std::string adapter_id;
    int32_t context_tokens = 0;
    std::atomic_bool cancel_requested { false };
    const volatile int32_t * active_cancel_flag = nullptr;
    std::mutex generation_mutex;
    int32_t output_tokens = 0;
    bool closed_thinking_prefill = false;

    ~wg_engine() {
        if (context != nullptr) llama_free(context);
        if (model != nullptr) llama_model_free(model);
    }
};

namespace {

constexpr int32_t kAbiVersion = WG_ABI_VERSION;
constexpr int32_t kMaxTokens = 512;
constexpr int32_t kPenaltyWindow = 64;

std::atomic<int> g_reported_layers{-1};
void adaptive_log(ggml_log_level level, const char * message, void *) {
    if (const char * start = std::strstr(message, "offloaded ")) {
        int layers = 0, total = 0;
        if (std::sscanf(start, "offloaded %d/%d layers to GPU", &layers, &total) == 2)
            g_reported_layers.store(layers);
    }
#if defined(__ANDROID__)
    __android_log_write(level == GGML_LOG_LEVEL_ERROR ? ANDROID_LOG_ERROR : ANDROID_LOG_INFO, "WritingNative", message);
#else
    (void)level;
    std::fputs(message, stderr);
#endif
}
std::once_flag g_cpu_init_once;
std::once_flag g_vulkan_init_once;
std::string g_vulkan_unavailable_reason;
std::string g_cpu_plugin;

#if defined(__ANDROID__)
std::string select_cpu_plugin(const std::string & root) {
    std::string best = root + "libggml-cpu.so";
    if (std::getenv("WRITINGLAB_CPU_BASELINE") != nullptr) return best;
    int best_score = 0;
    std::error_code error;
    for (const auto & entry : std::filesystem::directory_iterator(root, error)) {
        const auto name = entry.path().filename().string();
        if (name.rfind("libggml-cpu-", 0) != 0 || entry.path().extension() != ".so") continue;
        void * module = dlopen(entry.path().c_str(), RTLD_NOW | RTLD_LOCAL);
        if (!module) continue;
        // Upstream compiles its score function without ISA flags/LTO, so checking
        // a variant never executes unsupported instructions from that backend.
        auto score = reinterpret_cast<int (*)(void)>(dlsym(module, "ggml_backend_score"));
        const int value = score ? score() : 0;
        if (value > best_score) {best_score = value; best = entry.path().string();}
        dlclose(module);
    }
    return best;
}
#endif

bool flag_is_set(const volatile int32_t * flag) {
    return flag != nullptr && *flag != 0;
}

bool is_cancelled(const wg_engine * engine, const volatile int32_t * external_flag = nullptr) {
    return (engine != nullptr && engine->cancel_requested.load(std::memory_order_relaxed)) ||
           flag_is_set(external_flag) ||
           (engine != nullptr && flag_is_set(engine->active_cancel_flag));
}

bool load_progress_callback(float, void * user_data) {
    const auto * flag = static_cast<const volatile int32_t *>(user_data);
    return !flag_is_set(flag);
}

bool decode_abort_callback(void * user_data) {
    return is_cancelled(static_cast<const wg_engine *>(user_data));
}

void set_error(char * destination, uint32_t capacity, const std::string & message) {
    if (destination == nullptr || capacity == 0) {
        return;
    }
    const size_t count = std::min<size_t>(message.size(), static_cast<size_t>(capacity - 1));
    if (count > 0) {
        std::memcpy(destination, message.data(), count);
    }
    destination[count] = '\0';
}

int32_t copy_text(const std::string & source, char * destination, uint32_t capacity) {
    if (destination == nullptr || capacity == 0) {
        return WG_ERROR_INVALID_ARGUMENT;
    }
    if (source.size() + 1 > capacity) {
        destination[0] = '\0';
        return WG_ERROR_BUFFER;
    }
    std::memcpy(destination, source.c_str(), source.size() + 1);
    return WG_STATUS_OK;
}

void initialize_backends(const char * directory, int32_t preference) {
#if !defined(__ANDROID__)
    (void) preference;
    std::call_once(g_cpu_init_once, [directory]() {
        const std::string root = directory != nullptr ? std::string(directory) + "/" : "";
        if (!ggml_backend_load((root + "ggml-cpu.dll").c_str())) throw std::runtime_error("CPU plugin unavailable.");
        llama_log_set(adaptive_log, nullptr);
        llama_backend_init();
    });
    if (preference != WG_BACKEND_CPU) std::call_once(g_vulkan_init_once, [directory]() {
        const std::string root = directory != nullptr ? std::string(directory) + "/" : "";
        if (!ggml_backend_load((root + "ggml-vulkan.dll").c_str())) g_vulkan_unavailable_reason = "Vulkan plugin unavailable.";
    });
#else
    const std::string root = directory != nullptr && directory[0] != '\0' ? std::string(directory) + "/" : "";
    const char * vulkan_library = "libggml-vulkan.so";
    std::call_once(g_cpu_init_once, [&]() {
        llama_log_set(adaptive_log, nullptr);
        g_cpu_plugin = select_cpu_plugin(root);
        if (!ggml_backend_load(g_cpu_plugin.c_str()))
            throw std::runtime_error("Could not load the packaged CPU backend.");
        __android_log_write(ANDROID_LOG_INFO, "WritingNative", ("CPU plugin: " + g_cpu_plugin).c_str());
        llama_backend_init();
    });
    // Explicit CPU never initializes the Vulkan plugin or creates a Vulkan instance.
    if (preference == WG_BACKEND_CPU) return;
    std::call_once(g_vulkan_init_once, [&]() {
        g_vulkan_unavailable_reason = android_vulkan_unavailable_reason();
        if (!g_vulkan_unavailable_reason.empty()) {
            __android_log_write(ANDROID_LOG_WARN, "WritingNative", g_vulkan_unavailable_reason.c_str());
            return;
        }
        if (!ggml_backend_load((root + vulkan_library).c_str()))
            g_vulkan_unavailable_reason = "Packaged Vulkan backend could not be loaded or initialized.";
    });
#endif
}

ggml_backend_dev_t find_cpu_device() {
    return ggml_backend_dev_by_type(GGML_BACKEND_DEVICE_TYPE_CPU);
}

ggml_backend_dev_t find_vulkan_device(int selected = 0) {
    int ordinal = 0;
    for (size_t index = 0; index < ggml_backend_dev_count(); ++index) {
        ggml_backend_dev_t device = ggml_backend_dev_get(index);
        if (device == nullptr) {
            continue;
        }
        ggml_backend_reg_t registry = ggml_backend_dev_backend_reg(device);
        const char * registry_name = registry == nullptr ? nullptr : ggml_backend_reg_name(registry);
        if (registry_name != nullptr && std::strcmp(registry_name, "Vulkan") == 0) {
            if (ordinal++ == selected) return device;
        }
    }
    return nullptr;
}

struct load_result {
    llama_model * model = nullptr;
    llama_context * context = nullptr;
    std::string error;
};

load_result load_for_device(const char * model_path, int32_t context_tokens,
                            ggml_backend_dev_t device, bool use_gpu, int gpu_layers,
                            const volatile int32_t * cancel_flag, wg_engine * engine) {
    load_result result;
    if (flag_is_set(cancel_flag)) {
        result.error = "Loading was cancelled.";
        return result;
    }

    llama_model_params model_params = llama_model_default_params();
    std::array<ggml_backend_dev_t, 2> devices { use_gpu ? device : nullptr, nullptr };
    // An empty, terminated device list plus n_gpu_layers=0 makes CPU placement explicit.
    model_params.devices = devices.data();
    model_params.n_gpu_layers = use_gpu ? (gpu_layers < 0 ? INT_MAX : gpu_layers) : 0;
    g_reported_layers.store(-1);
    model_params.progress_callback = load_progress_callback;
    // The callback interprets user_data as the caller-owned cancellation flag.
    model_params.progress_callback_user_data = const_cast<int32_t *>(cancel_flag);

    result.model = llama_model_load_from_file(model_path, model_params);
    if (result.model == nullptr) {
        result.error = flag_is_set(cancel_flag) ? "Loading was cancelled." : "llama_model_load_from_file returned null.";
        return result;
    }

    llama_context_params context_params = llama_context_default_params();
    context_params.n_ctx = static_cast<uint32_t>(context_tokens);
    context_params.n_batch = static_cast<uint32_t>(context_tokens);
    context_params.n_ubatch = std::min<uint32_t>(static_cast<uint32_t>(context_tokens), 512);
    context_params.n_seq_max = 1;
    context_params.offload_kqv = use_gpu;
    context_params.op_offload = use_gpu;
    context_params.no_perf = false;
    context_params.abort_callback = decode_abort_callback;
    context_params.abort_callback_data = engine;
    result.context = llama_init_from_model(result.model, context_params);
    if (result.context == nullptr) {
        llama_model_free(result.model);
        result.model = nullptr;
        result.error = flag_is_set(cancel_flag) ? "Loading was cancelled." : "llama_init_from_model returned null.";
    }
    return result;
}

void free_load_result(load_result & result) {
    if (result.context != nullptr) {
        llama_free(result.context);
        result.context = nullptr;
    }
    if (result.model != nullptr) {
        llama_model_free(result.model);
        result.model = nullptr;
    }
}

void store_output(const std::string & output, char ** out_text, uint32_t * out_length) {
    if (output.size() > UINT32_MAX - 1) {
        throw std::length_error("Generated output exceeds the C ABI length limit.");
    }
    auto * allocation = static_cast<char *>(std::malloc(output.size() + 1));
    if (allocation == nullptr) {
        throw std::bad_alloc();
    }
    std::memcpy(allocation, output.data(), output.size());
    allocation[output.size()] = '\0';
    *out_text = allocation;
    *out_length = static_cast<uint32_t>(output.size());
}

} // namespace

extern "C" {

int32_t WG_CALL wg_abi_version(void) {
    return kAbiVersion;
}

static int32_t load_config_impl(const char * model_path_utf8, int32_t backend_preference,
                        int32_t context_tokens, const char * backend_directory_utf8,
                        const volatile int32_t * cancel_flag, wg_engine ** out_engine,
                        char * error_utf8, uint32_t error_capacity, int adapter_index, int gpu_layers, const char * adapter_id) {
    if (out_engine != nullptr) {
        *out_engine = nullptr;
    }
    if (model_path_utf8 == nullptr || model_path_utf8[0] == '\0' || out_engine == nullptr ||
        context_tokens <= 0 || backend_preference < WG_BACKEND_AUTO_VULKAN_CPU ||
        backend_preference > WG_BACKEND_CPU) {
        set_error(error_utf8, error_capacity, "Invalid model path, backend preference, context, or output handle.");
        return WG_ERROR_INVALID_ARGUMENT;
    }

    std::unique_ptr<wg_engine> engine;
    try {
        initialize_backends(backend_directory_utf8, backend_preference);
        ggml_backend_dev_t cpu = find_cpu_device();
        if (cpu == nullptr) {
            set_error(error_utf8, error_capacity, "CPU backend was not found in the loaded llama.cpp backend registry.");
            return WG_ERROR_BACKEND_UNAVAILABLE;
        }

        engine = std::make_unique<wg_engine>();
        engine->active_cancel_flag = cancel_flag;
        load_result loaded;
        bool loaded_on_gpu = false;

        if (backend_preference != WG_BACKEND_CPU) {
            ggml_backend_dev_t vulkan = find_vulkan_device(adapter_index);
            if (vulkan == nullptr) {
                if (backend_preference == WG_BACKEND_VULKAN) {
                    set_error(error_utf8, error_capacity, g_vulkan_unavailable_reason.empty()
                        ? "Vulkan was requested but no Vulkan backend device was loaded." : g_vulkan_unavailable_reason);
                    return WG_ERROR_BACKEND_UNAVAILABLE;
                }
                engine->fallback_reason = g_vulkan_unavailable_reason.empty()
                    ? "Vulkan backend/device unavailable at load; selected CPU."
                    : g_vulkan_unavailable_reason;
            } else {
                ggml_backend_dev_props props{};
                ggml_backend_dev_get_props(vulkan, &props);
                engine->adapter_id = props.device_id && props.device_id[0] ? props.device_id : ggml_backend_dev_description(vulkan);
                if (adapter_id && adapter_id[0] && engine->adapter_id != adapter_id) {
                    set_error(error_utf8, error_capacity, "GPU identity changed after inspection.");
                    return WG_ERROR_BACKEND_UNAVAILABLE;
                }
                loaded = load_for_device(model_path_utf8, context_tokens, vulkan, true, gpu_layers, cancel_flag, engine.get());
                if (loaded.context != nullptr) {
                    loaded_on_gpu = true;
                    engine->backend = "Vulkan";
                    engine->device = ggml_backend_dev_name(vulkan);
                } else if (flag_is_set(cancel_flag)) {
                    set_error(error_utf8, error_capacity, "Loading was cancelled.");
                    return WG_STATUS_CANCELLED;
                } else if (backend_preference == WG_BACKEND_VULKAN) {
                    set_error(error_utf8, error_capacity, loaded.error);
                    return WG_ERROR_MODEL_LOAD;
                } else {
                    engine->fallback_reason = "Vulkan load failed; selected CPU during load: " + loaded.error;
                }
            }
        }

        if (!loaded_on_gpu) {
            free_load_result(loaded);
            if (flag_is_set(cancel_flag)) {
                set_error(error_utf8, error_capacity, "Loading was cancelled.");
                return WG_STATUS_CANCELLED;
            }
            loaded = load_for_device(model_path_utf8, context_tokens, cpu, false, 0, cancel_flag, engine.get());
            if (loaded.context == nullptr) {
                set_error(error_utf8, error_capacity, loaded.error);
                return flag_is_set(cancel_flag) ? WG_STATUS_CANCELLED : WG_ERROR_MODEL_LOAD;
            }
            engine->backend = "CPU";
            engine->device = ggml_backend_dev_name(cpu);
#if defined(__ANDROID__)
            engine->device += " / " + std::filesystem::path(g_cpu_plugin).filename().string();
#endif
            engine->offloaded_layers = 0;
        } else {
            // llama.cpp exposes the total layer count, but not a public
            // getter for the number actually offloaded after allocation.
            engine->offloaded_layers = g_reported_layers.load();
        }

        engine->model = loaded.model;
        engine->total_layers = llama_model_n_layer(engine->model) + 1;
        engine->context = loaded.context;
        engine->context_tokens = static_cast<int32_t>(llama_n_ctx(engine->context));
        engine->active_cancel_flag = nullptr;
        engine->templates = common_chat_templates_init(engine->model, "");
        if (!engine->templates) {
            set_error(error_utf8, error_capacity, "Could not initialize the model's native chat template.");
            return WG_ERROR_MODEL_LOAD;
        }
        *out_engine = engine.release();
        return WG_STATUS_OK;
    } catch (const std::exception & exception) {
        set_error(error_utf8, error_capacity, exception.what());
        return WG_ERROR_INTERNAL;
    } catch (...) {
        set_error(error_utf8, error_capacity, "Unknown native error during model load.");
        return WG_ERROR_INTERNAL;
    }
}


int32_t WG_CALL wg_runtime_options_version(void) { return 1; }
int32_t WG_CALL wg_get_total_layers(const wg_engine * e) { return e ? e->total_layers : 0; }
int32_t WG_CALL wg_copy_adapter_id(const wg_engine * e, char * p, uint32_t n) {
    return e ? copy_text(e->adapter_id, p, n) : WG_ERROR_INVALID_ARGUMENT;
}
int32_t WG_CALL wg_load(const char * path, int32_t preference, int32_t context, const char * directory,
    const volatile int32_t * cancel, wg_engine ** engine, char * error, uint32_t capacity) {
    return load_config_impl(path, preference, context, directory, cancel, engine, error, capacity, 0, -1, nullptr);
}
int32_t WG_CALL wg_load_config(const char * path, int32_t context, const char * directory, int32_t adapter,
    const char * adapter_id, int32_t layers, const volatile int32_t * cancel, wg_engine ** engine, char * error, uint32_t capacity) {
    if (layers < 0 || (layers > 0 && (adapter < 0 || !adapter_id || !adapter_id[0]))) {
        if (engine) *engine = nullptr;
        set_error(error, capacity, "An explicit GPU and nonnegative layer count are required.");
        return WG_ERROR_INVALID_ARGUMENT;
    }
    return load_config_impl(path, layers ? WG_BACKEND_VULKAN : WG_BACKEND_CPU, context, directory,
        cancel, engine, error, capacity, adapter, layers, adapter_id);
}
int32_t WG_CALL wg_probe_runtime(const char * path, int32_t context, const char * directory,
    char ** output, uint32_t * length, char * error, uint32_t capacity) {
    if (output) *output = nullptr;
    if (!path || !path[0] || !output || !length || context <= 0) return WG_ERROR_INVALID_ARGUMENT;
    try {
        initialize_backends(directory, WG_BACKEND_AUTO_VULKAN_CPU);
        using json = nlohmann::ordered_json;
        const gguf_init_params gp{true, nullptr};
        std::unique_ptr<gguf_context, decltype(&gguf_free)> metadata(gguf_init_from_file(path, gp), gguf_free);
        if (!metadata) throw std::runtime_error("GGUF metadata could not be read.");
        const auto arch_key = gguf_find_key(metadata.get(), "general.architecture");
        if (arch_key < 0) throw std::runtime_error("Missing GGUF architecture.");
        const std::string key = std::string(gguf_get_val_str(metadata.get(), arch_key)) + ".block_count";
        const auto layer_key = gguf_find_key(metadata.get(), key.c_str());
        if (layer_key < 0 || gguf_get_kv_type(metadata.get(), layer_key) != GGUF_TYPE_UINT32)
            throw std::runtime_error("Missing GGUF block count.");
        const auto full = static_cast<int>(gguf_get_val_u32(metadata.get(), layer_key)) + 1;
        json devices = json::array();
        for (int ordinal = 0; ; ordinal++) {
            auto device = find_vulkan_device(ordinal);
            if (!device) break;
            ggml_backend_dev_props props{};
            ggml_backend_dev_get_props(device, &props);
            const std::string id = props.device_id && props.device_id[0] ? props.device_id : ggml_backend_dev_description(device);
            const size_t margin = std::max<size_t>(256ull << 20, props.memory_total / 12);
            json item{{"Index",ordinal},{"Id",id},{"Name",props.description},
                {"FreeBytes",props.memory_free},{"TotalBytes",props.memory_total},
                {"EstimatedLayers",0},{"FullLayers",full},{"EstimatedBytes",0},
                {"MarginBytes",margin},{"EstimateError",nullptr},{"IsIntegrated",props.type == GGML_BACKEND_DEVICE_TYPE_IGPU}};
            try {
                std::array<ggml_backend_dev_t,2> selected{device,nullptr};
                auto mp = llama_model_default_params(); mp.devices = selected.data();
                auto cp = llama_context_default_params();
                cp.n_ctx = context; cp.n_batch = context; cp.n_ubatch = std::min(context,512); cp.n_seq_max = 1;
                cp.offload_kqv = true; cp.op_offload = true;
                std::vector<float> split(llama_max_devices(),0);
                std::vector<size_t> margins(llama_max_devices(),margin);
                std::vector<llama_model_tensor_buft_override> overrides(llama_max_tensor_buft_overrides());
                auto fit_context = cp;
                const auto fit = common_fit_params({path}, &mp, &fit_context, split.data(), overrides.data(), margins.data(),
                    context, nullptr, GGML_LOG_LEVEL_ERROR);
                if (fit != COMMON_PARAMS_FIT_STATUS_SUCCESS) throw std::runtime_error("No memory fit at the fixed context.");
                int layers = mp.n_gpu_layers < 0 ? full : std::min(full, mp.n_gpu_layers);
                for (int attempt = 0; layers > 0 && attempt < 4; ++attempt) {
                    // Measure our exact layer-only placement, without fit's optional tensor overrides.
                    auto exact = llama_model_default_params(); exact.devices = selected.data(); exact.n_gpu_layers = layers;
                    const auto rows = common_fit_measure({path}, &exact, &cp, nullptr, nullptr, GGML_LOG_LEVEL_ERROR);
                    size_t projected = 0;
                    for (const auto & row : rows) if (row.kind == common_memory_breakdown_row::DEVICE)
                        projected += row.model + row.context + row.compute;
                    if (projected > 0 && props.memory_free > margin && projected <= props.memory_free - margin) {
                        item["EstimatedLayers"] = layers; item["EstimatedBytes"] = projected; break;
                    }
                    const auto available = props.memory_free > margin ? props.memory_free - margin : 0;
                    layers = projected ? std::min(layers-1,static_cast<int>(layers * static_cast<double>(available) / projected)) : 0;
                }
            } catch (const std::exception & e) { item["EstimateError"] = e.what(); }
            devices.push_back(item);
        }
        llama_log_set(adaptive_log, nullptr);
        json result{{"Runtime","b12359/adaptive-v1"},{"DriverFingerprint",""},{"FullLayers",full},{"Devices",devices}};
        store_output(result.dump(), output, length);
        return WG_STATUS_OK;
    } catch (const std::exception & e) { set_error(error, capacity, e.what()); return WG_ERROR_INTERNAL; }
}

int32_t WG_CALL wg_generate(wg_engine * engine, const char * system_prompt_utf8,
                            const char * user_prompt_utf8, int32_t seed, int32_t max_tokens, int32_t guided_json,
                            float temperature, float top_p, int32_t top_k, float min_p,
                            float repeat_penalty, float presence_penalty, float frequency_penalty,
                            const volatile int32_t * cancel_flag, char ** out_text_utf8,
                            uint32_t * out_text_length, int32_t * out_finish_reason,
                            double * out_seconds, char * error_utf8, uint32_t error_capacity) {
    if (out_text_utf8 != nullptr) *out_text_utf8 = nullptr;
    if (out_text_length != nullptr) *out_text_length = 0;
    if (out_finish_reason != nullptr) *out_finish_reason = WG_FINISH_ERROR;
    if (out_seconds != nullptr) *out_seconds = 0.0;
    if (engine == nullptr || engine->model == nullptr || engine->context == nullptr ||
        system_prompt_utf8 == nullptr || user_prompt_utf8 == nullptr || out_text_utf8 == nullptr ||
        out_text_length == nullptr || out_finish_reason == nullptr || out_seconds == nullptr ||
        max_tokens < 1 || max_tokens > kMaxTokens || (guided_json != 0 && guided_json != 1) || top_k < 0 ||
        !std::isfinite(temperature) || temperature < 0 ||
        !std::isfinite(top_p) || top_p <= 0 || top_p > 1 ||
        !std::isfinite(min_p) || min_p < 0 || min_p > 1 ||
        !std::isfinite(repeat_penalty) || repeat_penalty <= 0 ||
        !std::isfinite(presence_penalty) || !std::isfinite(frequency_penalty)) {
        set_error(error_utf8, error_capacity, "Invalid generation arguments or sampling values.");
        return WG_ERROR_INVALID_ARGUMENT;
    }

    std::lock_guard<std::mutex> lock(engine->generation_mutex);
    engine->cancel_requested.store(false, std::memory_order_relaxed);
    engine->active_cancel_flag = cancel_flag;
    struct active_cancel_reset {
        wg_engine * engine;
        ~active_cancel_reset() { engine->active_cancel_flag = nullptr; }
    } reset { engine };

    const auto start = std::chrono::steady_clock::now();
    try {
        if (is_cancelled(engine)) {
            *out_finish_reason = WG_FINISH_CANCELLED;
            set_error(error_utf8, error_capacity, "Generation was cancelled.");
            return WG_STATUS_CANCELLED;
        }

        common_chat_templates_inputs inputs;
        common_chat_msg system_message;
        system_message.role = "system";
        system_message.content = system_prompt_utf8;
        common_chat_msg user_message;
        user_message.role = "user";
        user_message.content = user_prompt_utf8;
        inputs.messages = { std::move(system_message), std::move(user_message) };
        inputs.add_generation_prompt = true;
        inputs.use_jinja = true;
        inputs.enable_thinking = false;
        inputs.chat_template_kwargs["enable_thinking"] = "false";

        const common_chat_params chat = common_chat_templates_apply(engine->templates.get(), inputs);
        std::string rendered_prompt = chat.prompt.str();
        if (rendered_prompt.empty()) {
            set_error(error_utf8, error_capacity, "The model's chat template produced an empty prompt.");
            return WG_ERROR_GENERATION;
        }

        engine->closed_thinking_prefill = close_prefilled_thinking(rendered_prompt, guided_json != 0);
        engine->output_tokens = 0;
        llama_perf_context_reset(engine->context);
        const llama_vocab * vocab = llama_model_get_vocab(engine->model);
        std::vector<llama_token> prompt_tokens = common_tokenize(vocab, rendered_prompt, false, true);
        if (prompt_tokens.empty()) {
            set_error(error_utf8, error_capacity, "The model's chat template produced no tokens.");
            return WG_ERROR_GENERATION;
        }
        const uint32_t context_size = llama_n_ctx(engine->context);
        if (prompt_tokens.size() >= context_size) {
            set_error(error_utf8, error_capacity, "The formatted prompt leaves no room for generation in the selected context.");
            return WG_ERROR_GENERATION;
        }

        llama_memory_clear(llama_get_memory(engine->context), true);
        llama_batch prompt_batch = llama_batch_get_one(prompt_tokens.data(), static_cast<int32_t>(prompt_tokens.size()));
        if (llama_decode(engine->context, prompt_batch) != 0) {
            if (is_cancelled(engine)) {
                *out_finish_reason = WG_FINISH_CANCELLED;
                return WG_STATUS_CANCELLED;
            }
            set_error(error_utf8, error_capacity, "llama_decode failed while evaluating the formatted prompt.");
            return WG_ERROR_GENERATION;
        }

        llama_sampler_chain_params chain_params = llama_sampler_chain_default_params();
        chain_params.no_perf = true;
        llama_sampler * sampler = llama_sampler_chain_init(chain_params);
        if (sampler == nullptr) {
            set_error(error_utf8, error_capacity, "Could not allocate the llama.cpp sampler chain.");
            return WG_ERROR_GENERATION;
        }
        struct sampler_scope {
            llama_sampler * sampler;
            ~sampler_scope() { llama_sampler_free(sampler); }
        } sampler_guard { sampler };

        common_sampler_ptr guided_sampler;
        if (guided_json) {
            common_params_sampling params;
            params.seed = static_cast<uint32_t>(seed);
            params.top_k = top_k; params.top_p = top_p; params.min_p = min_p; params.temp = temperature;
            params.penalty_last_n = kPenaltyWindow; params.penalty_repeat = repeat_penalty;
            params.penalty_freq = frequency_penalty; params.penalty_present = presence_penalty;
            params.min_keep = 1;
            params.samplers = {COMMON_SAMPLER_TYPE_PENALTIES, COMMON_SAMPLER_TYPE_TOP_K,
                COMMON_SAMPLER_TYPE_TOP_P, COMMON_SAMPLER_TYPE_MIN_P, COMMON_SAMPLER_TYPE_TEMPERATURE};
            params.grammar = common_grammar(COMMON_GRAMMAR_TYPE_USER, writing_json_grammar);
            // Upstream first validates the sampled token against the grammar, and
            // filters the entire vocabulary only when rejection requires it.
            guided_sampler.reset(common_sampler_init(engine->model, params));
            if (!guided_sampler) throw std::runtime_error("Could not initialize the interactive JSON sampler.");
        }

        if (repeat_penalty != 1.0f || presence_penalty != 0.0f || frequency_penalty != 0.0f) {
            llama_sampler_chain_add(sampler, llama_sampler_init_penalties(
                llama_vocab_n_tokens(vocab), kPenaltyWindow, repeat_penalty,
                frequency_penalty, presence_penalty));
        }
        if (top_k > 0) llama_sampler_chain_add(sampler, llama_sampler_init_top_k(top_k));
        if (top_p < 1.0f) llama_sampler_chain_add(sampler, llama_sampler_init_top_p(top_p, 1));
        if (min_p > 0.0f) llama_sampler_chain_add(sampler, llama_sampler_init_min_p(min_p, 1));
        llama_sampler_chain_add(sampler, llama_sampler_init_temp(temperature));
        llama_sampler_chain_add(sampler, llama_sampler_init_dist(static_cast<uint32_t>(seed)));

        std::string output;
        const int32_t generation_limit = std::min<int32_t>(max_tokens,
            static_cast<int32_t>(context_size - prompt_tokens.size()));
        *out_finish_reason = WG_FINISH_LENGTH;
        for (int32_t generated = 0; generated < generation_limit; ++generated) {
            if (is_cancelled(engine)) {
                *out_finish_reason = WG_FINISH_CANCELLED;
                store_output(output, out_text_utf8, out_text_length);
                *out_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
                set_error(error_utf8, error_capacity, "Generation was cancelled.");
                return WG_STATUS_CANCELLED;
            }
            const llama_token token = guided_sampler
                ? common_sampler_sample(guided_sampler.get(), engine->context, -1)
                : llama_sampler_sample(sampler, engine->context, -1);
            if (llama_vocab_is_eog(vocab, token)) {
                *out_finish_reason = WG_FINISH_STOP;
                break;
            }
            if (guided_sampler) common_sampler_accept(guided_sampler.get(), token, true);
            output += common_token_to_piece(vocab, token, false);
            engine->output_tokens++;

            if (generated + 1 < generation_limit) {
                llama_token next_token = token;
                llama_batch next = llama_batch_get_one(&next_token, 1);
                if (llama_decode(engine->context, next) != 0) {
                    if (is_cancelled(engine)) {
                        *out_finish_reason = WG_FINISH_CANCELLED;
                        store_output(output, out_text_utf8, out_text_length);
                        *out_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
                        set_error(error_utf8, error_capacity, "Generation was cancelled.");
                        return WG_STATUS_CANCELLED;
                    }
                    set_error(error_utf8, error_capacity, "llama_decode failed while generating a token.");
                    return WG_ERROR_GENERATION;
                }
            }
        }

        store_output(output, out_text_utf8, out_text_length);
        *out_seconds = std::chrono::duration<double>(std::chrono::steady_clock::now() - start).count();
        return WG_STATUS_OK;
    } catch (const std::exception & exception) {
        set_error(error_utf8, error_capacity, exception.what());
        return WG_ERROR_GENERATION;
    } catch (...) {
        set_error(error_utf8, error_capacity, "Unknown native error during generation.");
        return WG_ERROR_INTERNAL;
    }
}

int32_t WG_CALL wg_cancel(wg_engine * engine) {
    if (engine == nullptr) return WG_ERROR_INVALID_ARGUMENT;
    engine->cancel_requested.store(true, std::memory_order_relaxed);
    return WG_STATUS_OK;
}

void WG_CALL wg_unload(wg_engine * engine) {
    if (engine == nullptr) return;
    std::unique_lock<std::mutex> lock(engine->generation_mutex);
    lock.unlock();
    delete engine;
}

void WG_CALL wg_free_text(char * text_utf8) {
    std::free(text_utf8);
}

int32_t WG_CALL wg_copy_backend(const wg_engine * engine, char * destination_utf8, uint32_t capacity) {
    return engine == nullptr ? WG_ERROR_INVALID_ARGUMENT : copy_text(engine->backend, destination_utf8, capacity);
}

int32_t WG_CALL wg_copy_device(const wg_engine * engine, char * destination_utf8, uint32_t capacity) {
    return engine == nullptr ? WG_ERROR_INVALID_ARGUMENT : copy_text(engine->device, destination_utf8, capacity);
}

int32_t WG_CALL wg_copy_fallback_reason(const wg_engine * engine, char * destination_utf8, uint32_t capacity) {
    return engine == nullptr ? WG_ERROR_INVALID_ARGUMENT : copy_text(engine->fallback_reason, destination_utf8, capacity);
}

int32_t WG_CALL wg_get_offloaded_layers(const wg_engine * engine) {
    return engine == nullptr ? WG_ERROR_INVALID_ARGUMENT : engine->offloaded_layers;
}

int32_t WG_CALL wg_get_context_tokens(const wg_engine * engine) {
    return engine == nullptr ? WG_ERROR_INVALID_ARGUMENT : engine->context_tokens;
}

int32_t WG_CALL wg_get_last_metrics(const wg_engine * engine, int32_t * prompt_tokens,
    int32_t * output_tokens, int32_t * decoded_tokens, double * prompt_seconds,
    double * decode_seconds, int32_t * closed_thinking_prefill) {
    if (!engine || !prompt_tokens || !output_tokens || !decoded_tokens || !prompt_seconds ||
        !decode_seconds || !closed_thinking_prefill) return WG_ERROR_INVALID_ARGUMENT;
    const auto metrics = llama_perf_context(engine->context);
    *prompt_tokens = metrics.n_p_eval;
    *output_tokens = engine->output_tokens;
    *decoded_tokens = metrics.n_eval;
    *prompt_seconds = metrics.t_p_eval_ms / 1000.0;
    *decode_seconds = metrics.t_eval_ms / 1000.0;
    *closed_thinking_prefill = engine->closed_thinking_prefill ? 1 : 0;
    return WG_STATUS_OK;
}

} // extern "C"
