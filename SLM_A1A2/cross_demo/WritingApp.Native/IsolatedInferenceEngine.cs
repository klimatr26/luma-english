using System.Diagnostics;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using WritingApp.Shared;
using WritingDemo.Core;

namespace WritingApp.Native;

/// <summary>A crashed or timed-out native candidate never shares a process with its successor.</summary>
public sealed class IsolatedInferenceEngine(string nativeDirectory, string logDirectory,
    IReadOnlyDictionary<string, string>? environment = null) : IPlacementEngine
{
    private readonly SemaphoreSlim _gate = new(1, 1);
    private Process? _process;
    private ModelEntry? _model;
    private EngineState? _state;
    private FileStream? _responses;
    private string? _logPath;
    public TimeSpan GenerationTimeout { get; set; } = TimeSpan.FromSeconds(180);
    public int? WorkerProcessId
    {
        get { try { return _process is { HasExited: false } process ? process.Id : null; } catch (InvalidOperationException) { return null; } }
    }

    private void Start(CancellationToken ct)
    {
        if (_process is not null) return;
        ct.ThrowIfCancellationRequested();
        Directory.CreateDirectory(logDirectory);
        var stem = Path.Combine(logDirectory, "worker-" + Guid.NewGuid().ToString("N"));
        _logPath = stem + ".log";
        var executable = Path.Combine(nativeDirectory, OperatingSystem.IsWindows() ? "writing_worker.exe" : "libwriting_worker.so");
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false, CreateNoWindow = true,
            RedirectStandardInput = true, RedirectStandardOutput = true, RedirectStandardError = true,
            StandardInputEncoding = new UTF8Encoding(false), StandardOutputEncoding = Encoding.UTF8,
            StandardErrorEncoding = Encoding.UTF8, WorkingDirectory = nativeDirectory,
        };
        start.ArgumentList.Add(nativeDirectory);
        // A shell's diagnostic offload settings must not silently affect the app.
        foreach (var key in start.Environment.Keys.Where(k => k.StartsWith("GGML_VK_", StringComparison.Ordinal) ||
                     k == "WG_HYBRID_GPU_LAYERS").ToArray()) start.Environment.Remove(key);
        if (environment is not null) foreach (var item in environment) start.Environment[item.Key] = item.Value;
        _process = Process.Start(start) ?? throw new IOException("No se pudo iniciar el motor aislado.");
        _responses = new FileStream(stem + ".responses.jsonl", FileMode.CreateNew, FileAccess.Write, FileShare.Read);
        var process = _process;
        var logPath = _logPath;
        _ = Task.Run(async () =>
        {
            try
            {
                await using var file = new StreamWriter(logPath, false, new UTF8Encoding(false)) { AutoFlush = true };
                while (await process.StandardError.ReadLineAsync().ConfigureAwait(false) is { } line)
                    await file.WriteLineAsync(line).ConfigureAwait(false);
            }
            catch (IOException) { }
            catch (ObjectDisposedException) { }
        });
    }

    private async Task<JsonElement> SendAsync(JsonObject request, TimeSpan timeout, CancellationToken ct)
    {
        Start(ct);
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(timeout);
        try
        {
            await _process!.StandardInput.WriteLineAsync(request.ToJsonString().AsMemory(), deadline.Token).ConfigureAwait(false);
            await _process.StandardInput.FlushAsync(deadline.Token).ConfigureAwait(false);
            var line = await _process.StandardOutput.ReadLineAsync(deadline.Token).ConfigureAwait(false)
                ?? throw new IOException($"El motor terminó sin respuesta. Registro: {_logPath}");
            // Preserve even a malformed envelope or failed native generation before interpretation.
            await _responses!.WriteAsync(Encoding.UTF8.GetBytes(line + "\n"), CancellationToken.None).ConfigureAwait(false);
            _responses.Flush(flushToDisk: true);
            using var json = JsonDocument.Parse(line);
            var result = json.RootElement.Clone();
            if (result.GetProperty("status").GetInt32() != 0)
                throw new InvalidOperationException(result.GetProperty("error").GetString() + $" Registro: {_logPath}");
            return result;
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            Stop();
            throw new TimeoutException($"El motor superó {timeout.TotalSeconds:F0} s. Registro: {_logPath}");
        }
        catch { Stop(); throw; }
    }

    public async Task<string> DriverAsync(CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try { return (await SendAsync(new JsonObject { ["op"] = "driver" }, TimeSpan.FromSeconds(15), ct).ConfigureAwait(false)).GetRawText(); }
        finally { _gate.Release(); }
    }

    public async Task<RuntimeInventory> InspectAsync(string modelPath, int context, CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var result = await SendAsync(new JsonObject { ["op"] = "inspect", ["model_path"] = modelPath, ["context"] = context },
                TimeSpan.FromSeconds(120), ct).ConfigureAwait(false);
            var inventory = JsonSerializer.Deserialize(result.GetProperty("inventory").GetRawText(), AppJsonContext.Default.RuntimeInventory)
                ?? throw new InvalidDataException("Inventario nativo vacío.");
            using var fingerprint = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            foreach (var path in Directory.EnumerateFiles(nativeDirectory).Where(p =>
                         p.EndsWith(".dll", StringComparison.OrdinalIgnoreCase) || p.EndsWith(".so", StringComparison.OrdinalIgnoreCase) ||
                         p.EndsWith("writing_worker.exe", StringComparison.OrdinalIgnoreCase)).Order(StringComparer.Ordinal))
            {
                fingerprint.AppendData(Encoding.UTF8.GetBytes(Path.GetFileName(path)));
                await using var file = File.OpenRead(path);
                fingerprint.AppendData(await SHA256.HashDataAsync(file, ct).ConfigureAwait(false));
            }
            return inventory with { Runtime = inventory.Runtime + "/" + Convert.ToHexStringLower(fingerprint.GetHashAndReset()) };
        }
        finally { _gate.Release(); }
    }

    public Task<EngineState> LoadAsync(ModelEntry model, string modelPath, BackendPreference backend, int context, CancellationToken ct)
    {
        if (backend != BackendPreference.Cpu)
            throw new InvalidOperationException("Usa el selector adaptativo para elegir GPU y distribución.");
        return LoadPlacementAsync(model, modelPath, RuntimePlacement.Cpu, context, ct);
    }

    public async Task<EngineState> LoadPlacementAsync(ModelEntry model, string path, RuntimePlacement placement, int context, CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            Stop();
            if (context <= 0 || placement.GpuLayers < 0) throw new ArgumentOutOfRangeException(nameof(context));
            if (!File.Exists(path)) throw new FileNotFoundException("Modelo no disponible.", path);
            var result = await SendAsync(new JsonObject
            {
                ["op"] = "load", ["model_path"] = Path.GetFullPath(path), ["context"] = context,
                ["adapter_index"] = placement.DeviceIndex, ["adapter_id"] = placement.DeviceId ?? "",
                ["gpu_layers"] = placement.GpuLayers,
            }, TimeSpan.FromSeconds(180), ct).ConfigureAwait(false);
            _model = model;
            return _state = new(placement.GpuLayers == 0 ? BackendPreference.Cpu : BackendPreference.Vulkan,
                result.GetProperty("backend").GetString()!, result.GetProperty("device").GetString(),
                result.GetProperty("gpu_layers").GetInt32(), result.GetProperty("fallback").GetString(),
                context, "writing_json_grammar_v1", result.GetProperty("full_layers").GetInt32(),
                result.GetProperty("adapter_id").GetString());
        }
        catch { Stop(); throw; }
        finally { _gate.Release(); }
    }

    public async Task<EngineOutput> GenerateAsync(WritingExercise exercise, string text, int seed, CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            var model = _model ?? throw new InvalidOperationException("Carga un modelo primero.");
            var s = model.Sampling;
            var result = await SendAsync(new JsonObject
            {
                ["op"] = "generate", ["system"] = PortablePrompt.For(model), ["user"] = PortablePrompt.BuildUser(exercise, text),
                ["seed"] = seed, ["sampling"] = new JsonObject
                {
                    ["max_tokens"] = s.MaxTokens, ["temperature"] = s.Temperature, ["top_p"] = s.TopP,
                    ["top_k"] = s.TopK, ["min_p"] = s.MinP, ["repeat_penalty"] = s.RepeatPenalty,
                    ["presence_penalty"] = s.PresencePenalty, ["frequency_penalty"] = s.FrequencyPenalty,
                },
            }, GenerationTimeout, ct).ConfigureAwait(false);
            var metrics = new InferenceMetrics(result.GetProperty("prompt_tokens").GetInt32(), result.GetProperty("output_tokens").GetInt32(),
                result.GetProperty("decoded_tokens").GetInt32(), result.GetProperty("prompt_seconds").GetDouble(),
                result.GetProperty("decode_seconds").GetDouble(), result.GetProperty("closed_thinking").GetBoolean());
            return new(result.GetProperty("content").GetString()!, result.GetProperty("finish").GetInt32() switch
                { 0 => "stop", 1 => "length", 2 => "cancelled", _ => "error" }, result.GetProperty("seconds").GetDouble(),
                $"isolated=true; adapter={_state?.AdapterId}; gpu_layers={_state?.OffloadedLayers}/{_state?.TotalLayers}; thinking_requested=false; log={_logPath}", metrics);
        }
        finally { _gate.Release(); }
    }

    private void Stop()
    {
        var process = _process; _process = null; _model = null; _state = null;
        _responses?.Dispose(); _responses = null;
        if (process is null) return;
        try
        {
            if (!process.HasExited)
            {
                if (OperatingSystem.IsWindows()) process.Kill(entireProcessTree: true);
                else process.Kill();
            }
            process.WaitForExit(5000);
        }
        finally { process.Dispose(); }
    }
    public async Task UnloadAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try { Stop(); } finally { _gate.Release(); }
    }
    public async ValueTask DisposeAsync() => await UnloadAsync().ConfigureAwait(false);
}
