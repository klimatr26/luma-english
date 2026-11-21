#pragma once
#include "writing_llama_bridge.h"

// Additive API. The original ABI2 interface and frozen benchmark runtime remain available.
#ifdef __cplusplus
extern "C" {
#endif
WG_API int32_t WG_CALL wg_runtime_options_version(void);
WG_API int32_t WG_CALL wg_probe_runtime(const char * model_path_utf8, int32_t context_tokens,
    const char * backend_directory_utf8, char ** out_json_utf8, uint32_t * out_length,
    char * error_utf8, uint32_t error_capacity);
WG_API int32_t WG_CALL wg_load_config(const char * model_path_utf8, int32_t context_tokens,
    const char * backend_directory_utf8, int32_t adapter_index, const char * adapter_id_utf8,
    int32_t gpu_layers, const volatile int32_t * cancel_flag, wg_engine ** out_engine,
    char * error_utf8, uint32_t error_capacity);
WG_API int32_t WG_CALL wg_get_total_layers(const wg_engine * engine);
WG_API int32_t WG_CALL wg_copy_adapter_id(const wg_engine * engine, char * destination_utf8, uint32_t capacity);
#ifdef __cplusplus
}
#endif
