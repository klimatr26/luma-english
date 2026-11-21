using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace WritingApp.Native;

internal static unsafe partial class NativeMethods
{
    private const string LibraryName = "writing_llama_bridge";

    [LibraryImport(LibraryName, EntryPoint = "wg_abi_version")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int AbiVersion();

    [LibraryImport(LibraryName, EntryPoint = "wg_load")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int Load(byte* modelPathUtf8, int backendPreference, int contextTokens,
        byte* backendDirectoryUtf8, int* cancelFlag, nint* engine, byte* errorUtf8, uint errorCapacity);

    [LibraryImport(LibraryName, EntryPoint = "wg_generate")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int Generate(nint engine, byte* systemPromptUtf8, byte* userPromptUtf8,
        int seed, int maxTokens, int guidedJson, float temperature, float topP, int topK, float minP,
        float repeatPenalty, float presencePenalty, float frequencyPenalty, int* cancelFlag,
        byte** outputUtf8, uint* outputLength, int* finishReason, double* seconds,
        byte* errorUtf8, uint errorCapacity);

    [LibraryImport(LibraryName, EntryPoint = "wg_cancel")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int Cancel(nint engine);

    [LibraryImport(LibraryName, EntryPoint = "wg_unload")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial void Unload(nint engine);

    [LibraryImport(LibraryName, EntryPoint = "wg_free_text")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial void FreeText(byte* outputUtf8);

    [LibraryImport(LibraryName, EntryPoint = "wg_copy_backend")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int CopyBackend(nint engine, byte* destinationUtf8, uint capacity);

    [LibraryImport(LibraryName, EntryPoint = "wg_copy_device")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int CopyDevice(nint engine, byte* destinationUtf8, uint capacity);

    [LibraryImport(LibraryName, EntryPoint = "wg_copy_fallback_reason")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int CopyFallbackReason(nint engine, byte* destinationUtf8, uint capacity);

    [LibraryImport(LibraryName, EntryPoint = "wg_get_offloaded_layers")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int GetOffloadedLayers(nint engine);

    [LibraryImport(LibraryName, EntryPoint = "wg_get_context_tokens")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int GetContextTokens(nint engine);

    [LibraryImport(LibraryName, EntryPoint = "wg_get_last_metrics")]
    [UnmanagedCallConv(CallConvs = new[] { typeof(CallConvCdecl) })]
    internal static partial int GetLastMetrics(nint engine, int* promptTokens, int* outputTokens,
        int* decodedTokens, double* promptSeconds, double* decodeSeconds, int* closedThinkingPrefill);
}
