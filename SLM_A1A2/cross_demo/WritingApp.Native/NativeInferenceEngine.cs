using System.Text;
using WritingDemo.Core;
using WritingApp.Shared;

namespace WritingApp.Native;

/// <summary>In-process llama.cpp engine. Native assets are loaded from the app package.</summary>
public sealed class NativeInferenceEngine : IInferenceEngine
{
    private const int ExpectedAbiVersion = 2;
    private const int NativeTextCapacity = 4096;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private readonly string _backendDirectory;
    private readonly bool _guidedJson;
    private nint _handle;
    private ModelEntry? _model;
    private EngineState? _state;
    private bool _disposed;

    /// <param name="backendDirectory">
    /// Directory containing llama.cpp backend plugins (ggml-vulkan.dll and ggml-cpu.dll on Windows,
    /// libggml-vulkan.so and libggml-cpu.so on Android). Defaults to the executable directory.
    /// Android callers should pass ApplicationInfo.NativeLibraryDir.
    /// </param>
    public NativeInferenceEngine(string? backendDirectory = null, bool guidedJson = true)
    {
        _backendDirectory = Path.GetFullPath(backendDirectory ?? AppContext.BaseDirectory);
        _guidedJson = guidedJson;
    }

    public async Task<EngineState> LoadAsync(ModelEntry model, string modelPath,
        BackendPreference backend, int context, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(model);
        ArgumentException.ThrowIfNullOrWhiteSpace(modelPath);
        if (context <= 0)
            throw new ArgumentOutOfRangeException(nameof(context), "Context must be explicitly selected.");
        if (backend is not (BackendPreference.AutoVulkanCpu or BackendPreference.Vulkan or BackendPreference.Cpu))
            throw new ArgumentOutOfRangeException(nameof(backend));

        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            await UnloadCoreAsync().ConfigureAwait(false);
            ct.ThrowIfCancellationRequested();

            var fullModelPath = Path.GetFullPath(modelPath);
            if (!File.Exists(fullModelPath))
                throw new FileNotFoundException("Model file does not exist. Verify/download it through ModelStore first.", fullModelPath);

            if (NativeMethods.AbiVersion() != ExpectedAbiVersion)
                throw new InvalidOperationException("Native bridge ABI version does not match this WritingApp.Native build.");

            using var cancelFlag = new NativeCancellationFlag();
            using var registration = ct.Register(cancelFlag.RequestCancellation);
            var result = await Task.Run(() => LoadNative(fullModelPath, backend, context, cancelFlag),
                CancellationToken.None).ConfigureAwait(false);

            if (ct.IsCancellationRequested)
            {
                if (result.Handle != 0)
                    await Task.Run(() => NativeMethods.Unload(result.Handle), CancellationToken.None).ConfigureAwait(false);
                throw new OperationCanceledException(ct);
            }
            if (result.Status != NativeStatus.Success || result.Handle == 0)
                throw CreateNativeException("load", result.Status, result.Error, ct);

            _handle = result.Handle;
            _model = model;
            _state = new EngineState(
                Requested: backend,
                Backend: CopyText(_handle, 0) ?? "unknown",
                Device: CopyText(_handle, 1),
                OffloadedLayers: NativeMethods.GetOffloadedLayers(_handle),
                FallbackReason: CopyText(_handle, 2),
                ContextTokens: NativeMethods.GetContextTokens(_handle),
                ResponseFormat: _guidedJson ? "writing_json_grammar_v1" : "unconstrained");
            return _state;
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task<EngineOutput> GenerateAsync(WritingExercise exercise, string studentText,
        int seed, CancellationToken ct)
    {
        ArgumentNullException.ThrowIfNull(exercise);
        ArgumentNullException.ThrowIfNull(studentText);
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            ObjectDisposedException.ThrowIf(_disposed, this);
            ct.ThrowIfCancellationRequested();
            if (_handle == 0 || _model is null || _state is null)
                throw new InvalidOperationException("Load a model before generating.");

            var model = _model;
            var engine = _handle;
            var systemPrompt = PortablePrompt.For(model);
            var userPrompt = PortablePrompt.BuildUser(exercise, studentText);
            var sampling = model.Sampling;
            if (sampling.MaxTokens is < 1 or > 512)
                throw new InvalidOperationException("Portable models are limited to 512 generated tokens.");

            using var cancelFlag = new NativeCancellationFlag();
            using var registration = ct.Register(() =>
            {
                cancelFlag.RequestCancellation();
                _ = NativeMethods.Cancel(engine);
            });
            var result = await Task.Run(() => GenerateNative(engine, systemPrompt, userPrompt,
                seed, sampling, cancelFlag), CancellationToken.None).ConfigureAwait(false);

            if (ct.IsCancellationRequested || result.Status == NativeStatus.Cancelled)
                throw new OperationCanceledException(ct);
            if (result.Status != NativeStatus.Success)
                throw CreateNativeException("generation", result.Status, result.Error, ct);

            var metrics = ReadMetrics(engine);
            var diagnostics = $"seed={seed}; max_tokens={sampling.MaxTokens}; context={_state.ContextTokens}; thinking_flag_requested=false; response_format={_state.ResponseFormat}; closed_thinking_prefill={metrics?.ClosedThinkingPrefill}; backend={_state.Backend}";
            return new EngineOutput(result.Content, result.FinishReason, result.Seconds, diagnostics, metrics);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async Task UnloadAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            await UnloadCoreAsync().ConfigureAwait(false);
        }
        finally
        {
            _gate.Release();
        }
    }

    public async ValueTask DisposeAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try
        {
            if (_disposed)
                return;
            await UnloadCoreAsync().ConfigureAwait(false);
            _disposed = true;
        }
        finally
        {
            _gate.Release();
        }
    }

    private async Task UnloadCoreAsync()
    {
        var handle = _handle;
        _handle = 0;
        _model = null;
        _state = null;
        if (handle != 0)
            await Task.Run(() => NativeMethods.Unload(handle), CancellationToken.None).ConfigureAwait(false);
    }

    private unsafe NativeLoadResult LoadNative(string modelPath, BackendPreference backend, int context,
        NativeCancellationFlag cancelFlag)
    {
        var pathUtf8 = Utf8Z(modelPath);
        var directoryUtf8 = Utf8Z(_backendDirectory);
        var error = stackalloc byte[NativeTextCapacity];
        new Span<byte>(error, NativeTextCapacity).Clear();
        nint handle = 0;
        int status;
        fixed (byte* path = pathUtf8)
        fixed (byte* directory = directoryUtf8)
            status = NativeMethods.Load(path, (int)backend, context, directory, cancelFlag.Pointer,
                &handle, error, NativeTextCapacity);
        return new NativeLoadResult(status, handle, DecodeZ(error, NativeTextCapacity));
    }

    private unsafe NativeGenerationResult GenerateNative(nint handle, string systemPrompt, string userPrompt,
        int seed, SamplingOptions sampling, NativeCancellationFlag cancelFlag)
    {
        var systemUtf8 = Utf8Z(systemPrompt);
        var userUtf8 = Utf8Z(userPrompt);
        var error = stackalloc byte[NativeTextCapacity];
        new Span<byte>(error, NativeTextCapacity).Clear();
        byte* output = null;
        uint outputLength = 0;
        int finishReason = NativeFinishReason.Error;
        double seconds = 0;
        int status;
        try
        {
            fixed (byte* system = systemUtf8)
            fixed (byte* user = userUtf8)
                status = NativeMethods.Generate(handle, system, user, seed, sampling.MaxTokens, _guidedJson ? 1 : 0,
                    (float)sampling.Temperature, (float)sampling.TopP, sampling.TopK, (float)sampling.MinP,
                    (float)sampling.RepeatPenalty, (float)sampling.PresencePenalty,
                    (float)sampling.FrequencyPenalty, cancelFlag.Pointer, &output, &outputLength,
                    &finishReason, &seconds, error, NativeTextCapacity);

            var content = output == null ? string.Empty : Encoding.UTF8.GetString(new ReadOnlySpan<byte>(output, checked((int)outputLength)));
            var reason = finishReason switch
            {
                NativeFinishReason.Stop => "stop",
                NativeFinishReason.Length => "length",
                NativeFinishReason.Cancelled => "cancelled",
                _ => "error"
            };
            return new NativeGenerationResult(status, content, reason, seconds, DecodeZ(error, NativeTextCapacity));
        }
        finally
        {
            if (output != null)
                NativeMethods.FreeText(output);
        }
    }

    private static unsafe InferenceMetrics? ReadMetrics(nint handle)
    {
        int prompt=0, output=0, decoded=0, closed=0;
        double prefill=0, decode=0;
        return NativeMethods.GetLastMetrics(handle,&prompt,&output,&decoded,&prefill,&decode,&closed)==0
            ? new(prompt,output,decoded,prefill,decode,closed!=0) : null;
    }

    private static unsafe string? CopyText(nint handle, int textKind)
    {
        if (handle == 0)
            return null;
        var bytes = stackalloc byte[NativeTextCapacity];
        new Span<byte>(bytes, NativeTextCapacity).Clear();
        var status = textKind switch
        {
            0 => NativeMethods.CopyBackend(handle, bytes, NativeTextCapacity),
            1 => NativeMethods.CopyDevice(handle, bytes, NativeTextCapacity),
            2 => NativeMethods.CopyFallbackReason(handle, bytes, NativeTextCapacity),
            _ => -1
        };
        if (status != NativeStatus.Success)
            return null;
        return DecodeZ(bytes, NativeTextCapacity);
    }

    private static byte[] Utf8Z(string value)
    {
        var data = Encoding.UTF8.GetBytes(value);
        Array.Resize(ref data, data.Length + 1);
        return data;
    }

    private static unsafe string DecodeZ(byte* value, int capacity)
    {
        if (value == null)
            return string.Empty;
        var length = 0;
        while (length < capacity && value[length] != 0)
            length++;
        return Encoding.UTF8.GetString(new ReadOnlySpan<byte>(value, length));
    }

    private static Exception CreateNativeException(string operation, int status, string error, CancellationToken ct)
    {
        if (status == NativeStatus.Cancelled || ct.IsCancellationRequested)
            return new OperationCanceledException(ct);
        return new InvalidOperationException($"Native {operation} failed (status {status}): {error}");
    }

    private readonly record struct NativeLoadResult(int Status, nint Handle, string Error);
    private readonly record struct NativeGenerationResult(int Status, string Content, string FinishReason,
        double Seconds, string Error);

    private static class NativeStatus
    {
        public const int Success = 0;
        public const int Cancelled = 1;
    }

    private static class NativeFinishReason
    {
        public const int Stop = 0;
        public const int Length = 1;
        public const int Cancelled = 2;
        public const int Error = -1;
    }
}
