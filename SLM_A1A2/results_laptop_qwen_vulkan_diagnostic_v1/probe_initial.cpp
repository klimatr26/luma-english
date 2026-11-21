// Standalone diagnostic client for the frozen b12359 DLLs.
#define WIN32_LEAN_AND_MEAN
#include <windows.h>

#include "ggml-backend.h"
#include "llama.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <filesystem>
#include <iterator>
#include <memory>
#include <string>

using Clock = std::chrono::steady_clock;

static double seconds_since(Clock::time_point start) {
    return std::chrono::duration<double>(Clock::now() - start).count();
}

static bool report_progress(float progress, void * state) {
    auto & last = *static_cast<int *>(state);
    const int percent = static_cast<int>(progress * 100);
    if (percent != last) {
        std::printf("load_progress_pct=%d\n", percent);
        std::fflush(stdout);
        last = percent;
    }
    return true;
}

static bool uses_library_from(const std::filesystem::path & directory, const wchar_t * name) {
    wchar_t path[32768]{};
    const HMODULE module = GetModuleHandleW(name);
    if (!module || !GetModuleFileNameW(module, path, static_cast<DWORD>(std::size(path)))) {
        return false;
    }
    std::error_code error;
    return std::filesystem::equivalent(directory / name, path, error);
}

int wmain(int argc, wchar_t ** argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS | SEM_NOGPFAULTERRORBOX);
    if (argc != 5) {
        std::fputs("Usage: probe native_directory model_path gpu_layers mmap|none\n", stderr);
        return 2;
    }
    const auto directory = std::filesystem::path(argv[1]);
    const auto mode = std::wstring(argv[4]);
    if (mode != L"mmap" && mode != L"none") {
        return 2;
    }
    for (const auto * name : {L"llama.dll", L"ggml.dll", L"ggml-base.dll"}) {
        if (!uses_library_from(directory, name)) {
            std::fputs("Imported DLL path mismatch.\n", stderr);
            return 3;
        }
    }
    ggml_backend_load_all_from_path(directory.u8string().c_str());
    llama_backend_init();
    if (!uses_library_from(directory, L"ggml-vulkan.dll") || !uses_library_from(directory, L"ggml-cpu.dll")) {
        std::fputs("Backend DLL path mismatch.\n", stderr);
        return 3;
    }
    auto * registry = ggml_backend_reg_by_name("Vulkan");
    if (!registry || ggml_backend_reg_dev_count(registry) != 1) {
        return 4;
    }
    auto * device = ggml_backend_reg_dev_get(registry, 0);
    ggml_backend_dev_props properties{};
    ggml_backend_dev_get_props(device, &properties);
    std::printf("adapter=%s pci=%s free_bytes=%zu total_bytes=%zu\n",
                properties.description, properties.device_id ? properties.device_id : "",
                properties.memory_free, properties.memory_total);
    if (!properties.description || std::string(properties.description) != "Quadro P1000" ||
        !properties.device_id || std::string(properties.device_id) != "0000:01:00.0") {
        return 4;
    }
    ggml_backend_dev_t devices[] = {device, nullptr};
    auto model_params = llama_model_default_params();
    model_params.devices = devices;
    model_params.n_gpu_layers = std::stoi(argv[3]);
    model_params.load_mode = mode == L"mmap" ? LLAMA_LOAD_MODE_MMAP : LLAMA_LOAD_MODE_NONE;
    int last_percent = -1;
    model_params.progress_callback = report_progress;
    model_params.progress_callback_user_data = &last_percent;
    std::printf("stage=model_load layers=%d mode=%s\n", model_params.n_gpu_layers,
                llama_load_mode_name(model_params.load_mode));
    std::fflush(stdout);
    auto start = Clock::now();
    const auto model_path = std::filesystem::path(argv[2]).u8string();
    std::unique_ptr<llama_model, decltype(&llama_model_free)> model(
        llama_model_load_from_file(model_path.c_str(), model_params), &llama_model_free);
    std::printf("model_load_ok=%d elapsed_s=%.3f\n", bool(model), seconds_since(start));
    std::fflush(stdout);
    if (!model) {
        return 5;
    }

    auto context_params = llama_context_default_params();
    context_params.n_ctx = 2048;
    context_params.n_batch = 2048;
    context_params.n_ubatch = 512;
    context_params.n_seq_max = 1;
    context_params.offload_kqv = true;
    context_params.op_offload = true;
    std::puts("stage=context");
    std::fflush(stdout);
    std::unique_ptr<llama_context, decltype(&llama_free)> context(
        llama_init_from_model(model.get(), context_params), &llama_free);
    if (!context) {
        return 6;
    }

    const std::string prompt = "Write one short sentence about your morning. I wake up at";
    const auto * vocab = llama_model_get_vocab(model.get());
    llama_token tokens[128]{};
    const int count = llama_tokenize(vocab, prompt.c_str(), static_cast<int>(prompt.size()), tokens, 128, true, false);
    if (count <= 0) {
        return 7;
    }
    std::puts("stage=prefill");
    std::fflush(stdout);
    start = Clock::now();
    if (llama_decode(context.get(), llama_batch_get_one(tokens, count)) != 0) {
        return 8;
    }
    std::unique_ptr<llama_sampler, decltype(&llama_sampler_free)> sampler(
        llama_sampler_init_greedy(), &llama_sampler_free);
    for (int i = 0; i < 8; ++i) {
        auto next = llama_sampler_sample(sampler.get(), context.get(), -1);
        const auto * logits = llama_get_logits_ith(context.get(), -1);
        if (next < 0 || next >= llama_vocab_n_tokens(vocab) || !logits || !std::isfinite(logits[next])) {
            return 9;
        }
        if (llama_decode(context.get(), llama_batch_get_one(&next, 1)) != 0) {
            return 8;
        }
        std::printf("decode_token=%d id=%d\n", i + 1, next);
        std::fflush(stdout);
    }
    llama_synchronize(context.get());
    std::printf("probe_ok=1 prefill_tokens=%d decode_steps=8 elapsed_s=%.3f\n", count, seconds_since(start));
    return 0;
}
