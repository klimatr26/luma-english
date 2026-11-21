#pragma once

#include <stdint.h>

#if defined(_WIN32)
#  if defined(WRITING_LLAMA_BRIDGE_BUILD)
#    define WG_API __declspec(dllexport)
#  else
#    define WG_API __declspec(dllimport)
#  endif
#  define WG_CALL __cdecl
#else
#  define WG_API __attribute__((visibility("default")))
#  define WG_CALL
#endif

#ifdef __cplusplus
extern "C" {
#endif

typedef struct wg_engine wg_engine;
#define WG_ABI_VERSION 2

enum wg_backend_preference {
    WG_BACKEND_AUTO_VULKAN_CPU = 0,
    WG_BACKEND_VULKAN = 1,
    WG_BACKEND_CPU = 2,
};

enum wg_status {
    WG_STATUS_OK = 0,
    WG_STATUS_CANCELLED = 1,
    WG_ERROR_INVALID_ARGUMENT = -1,
    WG_ERROR_BACKEND_UNAVAILABLE = -2,
    WG_ERROR_MODEL_LOAD = -3,
    WG_ERROR_GENERATION = -4,
    WG_ERROR_BUFFER = -5,
    WG_ERROR_INTERNAL = -6,
};

enum wg_finish_reason {
    WG_FINISH_STOP = 0,
    WG_FINISH_LENGTH = 1,
    WG_FINISH_CANCELLED = 2,
    WG_FINISH_ERROR = -1,
};

WG_API int32_t WG_CALL wg_abi_version(void);

/* All text arguments and buffers are UTF-8. cancel_flag is an optional caller-owned
   aligned int32; set it to 1 from another thread to request cancellation. */
WG_API int32_t WG_CALL wg_load(
    const char * model_path_utf8,
    int32_t backend_preference,
    int32_t context_tokens,
    const char * backend_directory_utf8,
    const volatile int32_t * cancel_flag,
    wg_engine ** out_engine,
    char * error_utf8,
    uint32_t error_capacity);

WG_API int32_t WG_CALL wg_generate(
    wg_engine * engine,
    const char * system_prompt_utf8,
    const char * user_prompt_utf8,
    int32_t seed,
    int32_t max_tokens,
    int32_t guided_json,
    float temperature,
    float top_p,
    int32_t top_k,
    float min_p,
    float repeat_penalty,
    float presence_penalty,
    float frequency_penalty,
    const volatile int32_t * cancel_flag,
    char ** out_text_utf8,
    uint32_t * out_text_length,
    int32_t * out_finish_reason,
    double * out_seconds,
    char * error_utf8,
    uint32_t error_capacity);

WG_API int32_t WG_CALL wg_cancel(wg_engine * engine);
WG_API int32_t WG_CALL wg_get_last_metrics(const wg_engine * engine, int32_t * prompt_tokens,
    int32_t * output_tokens, int32_t * decoded_tokens, double * prompt_seconds,
    double * decode_seconds, int32_t * closed_thinking_prefill);
WG_API void WG_CALL wg_unload(wg_engine * engine);
WG_API void WG_CALL wg_free_text(char * text_utf8);
WG_API int32_t WG_CALL wg_copy_backend(const wg_engine * engine, char * destination_utf8, uint32_t capacity);
WG_API int32_t WG_CALL wg_copy_device(const wg_engine * engine, char * destination_utf8, uint32_t capacity);
WG_API int32_t WG_CALL wg_copy_fallback_reason(const wg_engine * engine, char * destination_utf8, uint32_t capacity);
WG_API int32_t WG_CALL wg_get_offloaded_layers(const wg_engine * engine);
WG_API int32_t WG_CALL wg_get_context_tokens(const wg_engine * engine);

#ifdef __cplusplus
}
#endif
