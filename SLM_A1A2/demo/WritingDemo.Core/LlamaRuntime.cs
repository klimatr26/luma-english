using System.Diagnostics;
using System.Net;
using System.Net.Sockets;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

[assembly: System.Runtime.CompilerServices.InternalsVisibleTo("WritingDemo.RuntimeTests")]

namespace WritingDemo.Core;

/// <summary>
/// Owns one llama.cpp b11457 server process and sends writing exercises to its
/// local OpenAI-compatible API. The process is always stopped through the
/// Process instance started by this runtime; no foreign process is ever killed.
/// The listener PID lookup is read-only and only confirms that the chosen port
/// belongs to our child process.
/// </summary>
public sealed class LlamaRuntime : IAsyncDisposable
{
    public const int DedicatedPortStart = 18400;
    public const int DedicatedPortEnd = 18499;
    public const string ExpectedServerSha256 = "c10548343e140c28ce63191a79f888e9d49640e3d19e7e4222344f29ea1ddae1";
    public const string UserPromptTemplate = "Level: {level}\nTask: {task}\nStudent text: {student_text}";

    private static readonly TimeSpan HealthRequestTimeout = TimeSpan.FromSeconds(5);
    private static readonly TimeSpan HealthPollInterval = TimeSpan.FromMilliseconds(500);
    private static readonly Regex ThinkTagRegex = new(
        @"<think>([\s\S]*?)(?:</think>|$)", RegexOptions.IgnoreCase | RegexOptions.CultureInvariant | RegexOptions.Compiled);
    private static readonly object PortLock = new();
    private static readonly HashSet<int> ClaimedPorts = [];

    private readonly DemoPaths _paths;
    private readonly HttpClient _httpClient;
    private readonly SemaphoreSlim _lifecycleGate = new(1, 1);
    private readonly SemaphoreSlim _logGate = new(1, 1);
    private Process? _serverProcess;
    private Task? _stdoutPump;
    private Task? _stderrPump;
    private CancellationTokenSource? _serverLifetime;
    private Uri? _baseAddress;
    private string? _runtimeLogPath;
    private string? _serverLogPath;
    private int? _claimedPort;
    private int? _lastOffloadedLayers;
    private int _requestSequence;
    private bool _isLoaded;
    private bool _disposed;
    private ModelSpec? _loadedModel;
    private RuntimeSelection? _activeBackend;

    public LlamaRuntime(DemoPaths paths)
    {
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));
        _httpClient = new HttpClient(new SocketsHttpHandler
        {
            AllowAutoRedirect = false,
            ConnectTimeout = TimeSpan.FromSeconds(10),
            PooledConnectionLifetime = TimeSpan.FromMinutes(2)
        })
        {
            Timeout = Timeout.InfiniteTimeSpan
        };
    }

    /// <summary>Maximum time to wait for this process's strict /health response.</summary>
    public TimeSpan StartupTimeout { get; set; } = TimeSpan.FromSeconds(120);

    /// <summary>Maximum time allowed for one generation request.</summary>
    public TimeSpan GenerationTimeout { get; set; } = TimeSpan.FromSeconds(90);

    /// <summary>
    /// Diagnostic-only switch used by the smoke harness to hide Vulkan devices
    /// from child processes. It does not alter installed packages or drivers.
    /// </summary>
    public bool HideVulkanDevicesForDiagnostics { get; set; }

    public bool IsLoaded
    {
        get
        {
            if (!Volatile.Read(ref _isLoaded)) return false;
            var process = Volatile.Read(ref _serverProcess);
            if (process is null) return false;
            try { return !process.HasExited; }
            catch (InvalidOperationException) { return false; }
        }
    }

    public ModelSpec? LoadedModel => IsLoaded ? Volatile.Read(ref _loadedModel) : null;

    public RuntimeSelection? ActiveBackend => IsLoaded ? Volatile.Read(ref _activeBackend) : null;

    public event Action<string>? Log;

    public async Task LoadAsync(
        ModelSpec spec,
        string modelPath,
        string serverPath,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(spec);
        ThrowIfDisposed();
        if (StartupTimeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(StartupTimeout));
        cancellationToken.ThrowIfCancellationRequested();

        await _lifecycleGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ThrowIfDisposed();
            if (!OperatingSystem.IsWindows())
                throw new PlatformNotSupportedException("El runtime llama.cpp de esta demo requiere Windows.");

            var fullModelPath = Path.GetFullPath(modelPath, _paths.LabDirectory);
            var fullServerPath = Path.GetFullPath(serverPath, _paths.LabDirectory);
            await VerifyModelAsync(spec, fullModelPath, cancellationToken).ConfigureAwait(false);
            await VerifyServerAsync(fullServerPath, cancellationToken).ConfigureAwait(false);

            await StopCoreAsync().ConfigureAwait(false);
            Directory.CreateDirectory(_paths.SessionDirectory);
            _runtimeLogPath = Path.Combine(_paths.SessionDirectory, "runtime.log");
            var stamp = DateTimeOffset.UtcNow.ToString("yyyyMMddTHHmmssfffZ", System.Globalization.CultureInfo.InvariantCulture);
            var safeId = SanitizeFilePart(spec.Id);
            _serverLogPath = Path.Combine(_paths.SessionDirectory, $"server-{safeId}-{stamp}.log");
            var port = AcquireDedicatedPort();
            _claimedPort = port;

            var startInfo = CreateServerStartInfo(
                fullServerPath,
                fullModelPath,
                _serverLogPath,
                port,
                spec.TemplateThinkingToggle,
                Path.GetDirectoryName(fullServerPath)!);
            var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
            try
            {
                if (!process.Start()) throw new InvalidOperationException("No se pudo iniciar llama-server.");
            }
            catch
            {
                process.Dispose();
                ReleaseClaimedPort();
                throw;
            }

            Volatile.Write(ref _serverProcess, process);
            Volatile.Write(ref _serverLifetime, new CancellationTokenSource());
            Volatile.Write(ref _baseAddress, new Uri($"http://127.0.0.1:{port}/", UriKind.Absolute));
            _stdoutPump = PumpOutputAsync(process.StandardOutput, "stdout");
            _stderrPump = PumpOutputAsync(process.StandardError, "stderr");
            await WriteLogAsync($"Iniciado llama-server PID {process.Id}, modelo {spec.Id}, puerto {port}.")
                .ConfigureAwait(false);

            try
            {
                await WaitUntilHealthyAsync(process, port, StartupTimeout, cancellationToken).ConfigureAwait(false);
                Volatile.Write(ref _loadedModel, spec);
                Volatile.Write(ref _isLoaded, true);
                Volatile.Write(ref _activeBackend, new RuntimeSelection(
                    RuntimePreference.ExistingCuda,
                    "CUDA",
                    null,
                    null,
                    RuntimePackageVerifier.ExpectedBuild,
                    RuntimePackageVerifier.ExpectedCommit,
                    fullServerPath));
                await WriteLogAsync($"Servidor listo para el modelo {spec.Id} en {BaseAddress}.").ConfigureAwait(false);
            }
            catch
            {
                await StopCoreAsync().ConfigureAwait(false);
                throw;
            }
        }
        finally
        {
            _lifecycleGate.Release();
        }
    }

    public async Task LoadAsync(
        ModelSpec spec,
        string modelPath,
        string serverPath,
        CancellationToken cancellationToken,
        RuntimePreference preference)
    {
        if (preference == RuntimePreference.ExistingCuda)
        {
            await LoadAsync(spec, modelPath, serverPath, cancellationToken).ConfigureAwait(false);
            return;
        }

        ArgumentNullException.ThrowIfNull(spec);
        ThrowIfDisposed();
        if (StartupTimeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(StartupTimeout));
        if (preference is not (RuntimePreference.AutoVulkanCpu or RuntimePreference.Vulkan or RuntimePreference.Cpu))
            throw new ArgumentOutOfRangeException(nameof(preference));
        cancellationToken.ThrowIfCancellationRequested();

        await _lifecycleGate.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            ThrowIfDisposed();
            if (!OperatingSystem.IsWindows())
                throw new PlatformNotSupportedException("El runtime llama.cpp de esta demo requiere Windows.");

            var fullModelPath = Path.GetFullPath(modelPath, _paths.LabDirectory);
            await VerifyModelAsync(spec, fullModelPath, cancellationToken).ConfigureAwait(false);
            var fullServerPath = await RuntimePackageVerifier.VerifyVulkanPackageAsync(_paths, cancellationToken)
                .ConfigureAwait(false);

            await StopCoreAsync().ConfigureAwait(false);
            Directory.CreateDirectory(_paths.SessionDirectory);
            _runtimeLogPath = Path.Combine(_paths.SessionDirectory, "runtime.log");

            var decision = await BackendSelectionPolicy.StartAsync(
                preference,
                token => ProbeVulkanDevicesAsync(fullServerPath, token),
                (device, token) => StartVulkanServerAttemptAsync(spec, fullModelPath, fullServerPath, device, token),
                token => StartBackendServerAsync(spec, fullModelPath, fullServerPath, RuntimePreference.Cpu, null, token),
                cancellationToken).ConfigureAwait(false);

            if (HideVulkanDevicesForDiagnostics && decision.ActualBackend == "CPU" && decision.FallbackReason is not null)
                decision = decision with { FallbackReason = decision.FallbackReason + " " + DiagnosticVulkanHideReason };

            Volatile.Write(ref _loadedModel, spec);
            Volatile.Write(ref _isLoaded, true);
            var selection = new RuntimeSelection(
                preference,
                decision.ActualBackend,
                decision.Device,
                decision.FallbackReason,
                RuntimePackageVerifier.ExpectedBuild,
                RuntimePackageVerifier.ExpectedCommit,
                fullServerPath,
                decision.ActualBackend == "CPU" ? 0 : _lastOffloadedLayers);
            Volatile.Write(ref _activeBackend, selection);

            if (selection.FallbackReason is { Length: > 0 } fallbackReason)
            {
                await WriteLogAsync(
                    $"Modelo {spec.Id}: fallback de {preference} a CPU. Motivo: {fallbackReason}. " +
                    "La inferencia en CPU suele ser más lenta y los resultados pueden diferir del backend GPU.")
                    .ConfigureAwait(false);
            }
            else
            {
                await WriteLogAsync(
                    $"Modelo {spec.Id}: backend {selection.ActualBackend}" +
                    (selection.Device is null ? string.Empty : $" ({selection.Device})") +
                    (selection.OffloadedLayers is int layers ? $", capas GPU descargadas: {layers}" : string.Empty) +
                    $", runtime {selection.RuntimeBuild}, commit {selection.RuntimeCommit}.")
                    .ConfigureAwait(false);
            }
            await WriteLogAsync($"Servidor listo para el modelo {spec.Id} en {BaseAddress}.").ConfigureAwait(false);
        }
        catch
        {
            await StopCoreAsync().ConfigureAwait(false);
            throw;
        }
        finally
        {
            _lifecycleGate.Release();
        }
    }

    public async Task<GenerationResult> GenerateAsync(
        WritingExercise exercise,
        string studentText,
        CancellationToken cancellationToken,
        string? promptProfileId = null)
    {
        ArgumentNullException.ThrowIfNull(exercise);
        ArgumentNullException.ThrowIfNull(studentText);
        ThrowIfDisposed();
        var baseAddress = Volatile.Read(ref _baseAddress);
        var serverLifetime = Volatile.Read(ref _serverLifetime);
        var model = Volatile.Read(ref _loadedModel);
        if (!IsLoaded || baseAddress is null || serverLifetime is null || model is null)
            throw new InvalidOperationException("Carga un modelo antes de generar comentarios.");
        if (GenerationTimeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(GenerationTimeout));

        cancellationToken.ThrowIfCancellationRequested();
        var profileId = promptProfileId ?? "benchmark-base";
        var profile = PromptCatalog.Load(_paths, model).SingleOrDefault(p => p.Id == profileId)
            ?? throw new ArgumentException("El perfil de instrucciones no está disponible para este modelo.", nameof(promptProfileId));
        var systemPrompt = profile.SystemPrompt;
        var timer = Stopwatch.StartNew();

        try
        {
            var result = await SendGenerationRequestAsync(
                _httpClient,
                baseAddress,
                model.Generation,
                systemPrompt,
                exercise,
                studentText,
                GenerationTimeout,
                cancellationToken,
                serverLifetime.Token,
                CaptureExchangeAsync).ConfigureAwait(false);
            return result with { ElapsedSeconds = timer.Elapsed.TotalSeconds, PromptProfileId = profile.Id, SystemPromptSha256 = profile.Sha256 };
        }
        catch (LlamaRateLimitException)
        {
            // A rate limit is terminal for this session. Preserve the exchange,
            // stop only the process this instance started, and let the caller save
            // the handoff state. There is deliberately no retry path.
            await StopAsync().ConfigureAwait(false);
            throw;
        }
    }

    public async Task StopAsync()
    {
        if (_disposed) return;
        await _lifecycleGate.WaitAsync().ConfigureAwait(false);
        try { await StopCoreAsync().ConfigureAwait(false); }
        finally { _lifecycleGate.Release(); }
    }

    public async ValueTask DisposeAsync()
    {
        if (_disposed) return;
        await StopAsync().ConfigureAwait(false);
        _disposed = true;
        _httpClient.Dispose();
        _lifecycleGate.Dispose();
        _logGate.Dispose();
    }

    /// <summary>
    /// Creates the exact argument vector used to launch llama.cpp. ArgumentList
    /// keeps paths with spaces as single arguments and avoids shell parsing.
    /// </summary>
    public static ProcessStartInfo CreateServerStartInfo(
        string serverPath,
        string modelPath,
        string serverLogPath,
        int port,
        bool templateThinkingToggle,
        string workingDirectory)
    {
        if (port is < DedicatedPortStart or > DedicatedPortEnd)
            throw new ArgumentOutOfRangeException(nameof(port), $"El puerto debe estar en {DedicatedPortStart}-{DedicatedPortEnd}.");

        var startInfo = new ProcessStartInfo
        {
            FileName = Path.GetFullPath(serverPath),
            WorkingDirectory = Path.GetFullPath(workingDirectory),
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };

        Add("-m", Path.GetFullPath(modelPath));
        Add("--host", "127.0.0.1");
        Add("--port", port.ToString(System.Globalization.CultureInfo.InvariantCulture));
        Add("-c", "4096");
        Add("--parallel", "1");
        Add("-lv", "4");
        Add("-ngl", "999");
        Add("-s", "42");
        Add("--reasoning", "off");
        Add("--reasoning-budget", "0");
        Add("--log-file", Path.GetFullPath(serverLogPath));
        if (templateThinkingToggle)
            Add("--chat-template-kwargs", "{\"enable_thinking\":false}");
        return startInfo;

        void Add(string name, string value)
        {
            startInfo.ArgumentList.Add(name);
            startInfo.ArgumentList.Add(value);
        }
    }

    internal static ProcessStartInfo CreateBackendServerStartInfo(
        string serverPath,
        string modelPath,
        string serverLogPath,
        int port,
        bool templateThinkingToggle,
        string workingDirectory,
        RuntimePreference backend,
        string? device)
    {
        if (backend is not (RuntimePreference.Vulkan or RuntimePreference.Cpu))
            throw new ArgumentOutOfRangeException(nameof(backend));
        if (backend == RuntimePreference.Vulkan
            && (device is null || !Regex.IsMatch(device, @"^Vulkan[0-9]+$", RegexOptions.CultureInvariant)))
            throw new ArgumentException("Vulkan requiere el nombre exacto de un dispositivo detectado.", nameof(device));

        var startInfo = CreateServerStartInfo(serverPath, modelPath, serverLogPath, port,
            templateThinkingToggle, workingDirectory);
        var args = startInfo.ArgumentList;
        var nglIndex = args.IndexOf("-ngl");
        if (nglIndex < 0 || nglIndex + 1 >= args.Count)
            throw new InvalidOperationException("No se encontró el argumento -ngl esperado.");

        var layers = backend == RuntimePreference.Vulkan ? "999" : "0";
        args[nglIndex + 1] = layers;
        args.Insert(nglIndex, "--device");
        args.Insert(nglIndex + 1, backend == RuntimePreference.Vulkan ? device! : "none");
        if (backend == RuntimePreference.Cpu)
        {
            args.Add("--no-kv-offload");
            args.Add("--no-op-offload");
        }
        return startInfo;
    }

    /// <summary>Builds the user message without reading examples or gold data.</summary>
    public static string BuildUserPrompt(WritingExercise exercise, string studentText)
    {
        ArgumentNullException.ThrowIfNull(exercise);
        ArgumentNullException.ThrowIfNull(studentText);
        return UserPromptTemplate
            .Replace("{level}", exercise.Level, StringComparison.Ordinal)
            .Replace("{task}", exercise.Task, StringComparison.Ordinal)
            .Replace("{student_text}", studentText, StringComparison.Ordinal);
    }

    /// <summary>
    /// Serializes the exact manifest generation settings with only the fixed
    /// non-streaming chat-completions envelope and the two required messages.
    /// </summary>
    public static string BuildRequestJson(
        JsonElement generation,
        string systemPrompt,
        WritingExercise exercise,
        string studentText)
    {
        if (generation.ValueKind != JsonValueKind.Object)
            throw new ArgumentException("Generation debe ser un objeto JSON.", nameof(generation));
        ArgumentNullException.ThrowIfNull(systemPrompt);

        var root = new JsonObject
        {
            ["messages"] = new JsonArray
            {
                new JsonObject { ["role"] = "system", ["content"] = systemPrompt },
                new JsonObject { ["role"] = "user", ["content"] = BuildUserPrompt(exercise, studentText) }
            },
            ["stream"] = false
        };

        foreach (var property in generation.EnumerateObject())
        {
            if (property.NameEquals("messages") || property.NameEquals("stream"))
                throw new ArgumentException($"Generation no puede redefinir '{property.Name}'.", nameof(generation));
            root[property.Name] = JsonNode.Parse(property.Value.GetRawText());
        }

        return root.ToJsonString(new JsonSerializerOptions { WriteIndented = false });
    }

    internal static async Task<GenerationResult> SendGenerationRequestAsync(
        HttpClient client,
        Uri baseAddress,
        JsonElement generation,
        string systemPrompt,
        WritingExercise exercise,
        string studentText,
        TimeSpan timeout,
        CancellationToken cancellationToken,
        CancellationToken serverLifetimeToken,
        Func<string, HttpStatusCode, string, Task>? captureExchange = null)
    {
        ArgumentNullException.ThrowIfNull(client);
        ArgumentNullException.ThrowIfNull(baseAddress);
        if (timeout <= TimeSpan.Zero) throw new ArgumentOutOfRangeException(nameof(timeout));

        var stopwatch = Stopwatch.StartNew();
        var requestJson = BuildRequestJson(generation, systemPrompt, exercise, studentText);
        using var timeoutSource = new CancellationTokenSource(timeout);
        using var linkedSource = CancellationTokenSource.CreateLinkedTokenSource(
            cancellationToken, serverLifetimeToken, timeoutSource.Token);
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri(baseAddress, "v1/chat/completions"))
        {
            Content = new StringContent(requestJson, Encoding.UTF8, "application/json")
        };

        HttpResponseMessage response;
        string apiJson;
        try
        {
            response = await client.SendAsync(request, HttpCompletionOption.ResponseContentRead, linkedSource.Token)
                .ConfigureAwait(false);
            using (response)
                apiJson = await response.Content.ReadAsStringAsync(linkedSource.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested && !serverLifetimeToken.IsCancellationRequested && timeoutSource.IsCancellationRequested)
        {
            throw new TimeoutException($"La generación excedió el límite de {timeout.TotalSeconds:0} segundos.");
        }

        if (captureExchange is not null)
            await captureExchange(requestJson, response.StatusCode, apiJson).ConfigureAwait(false);

        if (response.StatusCode == HttpStatusCode.TooManyRequests)
            throw new LlamaRateLimitException(apiJson);
        if (!response.IsSuccessStatusCode)
            throw new HttpRequestException(
                $"llama-server respondió HTTP {(int)response.StatusCode} ({response.StatusCode}): {apiJson}",
                null,
                response.StatusCode);

        using var document = JsonDocument.Parse(apiJson);
        var root = document.RootElement;
        if (!root.TryGetProperty("choices", out var choices) || choices.ValueKind != JsonValueKind.Array || choices.GetArrayLength() == 0)
            throw new InvalidDataException("La respuesta de llama-server no contiene choices[0].");
        var choice = choices[0];
        if (!choice.TryGetProperty("message", out var message) || message.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException("La respuesta de llama-server no contiene choices[0].message.");
        if (!message.TryGetProperty("content", out var contentElement) || contentElement.ValueKind != JsonValueKind.String)
            throw new InvalidDataException("La respuesta de llama-server no contiene contenido de texto.");
        if (!choice.TryGetProperty("finish_reason", out var finishReasonElement) || finishReasonElement.ValueKind != JsonValueKind.String)
            throw new InvalidDataException("La respuesta de llama-server no contiene finish_reason.");

        var content = contentElement.GetString()!;
        var finishReason = finishReasonElement.GetString()!;
        string? reasoningContent = null;
        if (message.TryGetProperty("reasoning_content", out var reasoningElement))
        {
            if (reasoningElement.ValueKind != JsonValueKind.String && reasoningElement.ValueKind != JsonValueKind.Null)
                throw new InvalidDataException("reasoning_content tiene un tipo inesperado.");
            reasoningContent = reasoningElement.ValueKind == JsonValueKind.String ? reasoningElement.GetString() : null;
        }

        if (!string.IsNullOrEmpty(reasoningContent))
            throw new InvalidDataException("El servidor devolvió reasoning_content no vacío aunque el razonamiento está desactivado.");
        if (ThinkTagRegex.Matches(content).Any(match => match.Groups[1].Value.Length > 0))
            throw new InvalidDataException("La respuesta contiene contenido no vacío dentro de etiquetas <think>.");

        return new GenerationResult(content, apiJson, finishReason, stopwatch.Elapsed.TotalSeconds, reasoningContent);
    }

    private Uri BaseAddress => _baseAddress ?? throw new InvalidOperationException("El servidor no está iniciado.");

    private async Task StartVulkanServerAttemptAsync(
        ModelSpec spec,
        string fullModelPath,
        string fullServerPath,
        string device,
        CancellationToken cancellationToken)
    {
        try
        {
            await StartBackendServerAsync(spec, fullModelPath, fullServerPath,
                RuntimePreference.Vulkan, device, cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (LlamaRateLimitException)
        {
            throw;
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (Exception ex)
        {
            throw new VulkanStartupFailureException(ex.Message, ex);
        }
    }

    private async Task StartBackendServerAsync(
        ModelSpec spec,
        string fullModelPath,
        string fullServerPath,
        RuntimePreference backend,
        string? device,
        CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        _lastOffloadedLayers = null;
        Directory.CreateDirectory(_paths.SessionDirectory);
        _runtimeLogPath = Path.Combine(_paths.SessionDirectory, "runtime.log");
        var stamp = DateTimeOffset.UtcNow.ToString("yyyyMMddTHHmmssfffZ", System.Globalization.CultureInfo.InvariantCulture);
        var safeId = SanitizeFilePart(spec.Id);
        _serverLogPath = Path.Combine(_paths.SessionDirectory, $"server-{safeId}-{backend.ToString().ToLowerInvariant()}-{stamp}.log");
        var port = AcquireDedicatedPort();
        _claimedPort = port;

        var packageDirectory = Path.GetDirectoryName(fullServerPath)!;
        var startInfo = CreateBackendServerStartInfo(
            fullServerPath,
            fullModelPath,
            _serverLogPath,
            port,
            spec.TemplateThinkingToggle,
            packageDirectory,
            backend,
            device);
        ConfigureVerifiedPackageEnvironment(startInfo, packageDirectory);
        var diagnosticNote = ConfigureDiagnosticEnvironment(startInfo);
        if (diagnosticNote.Length > 0) await WriteLogAsync(diagnosticNote).ConfigureAwait(false);

        var process = new Process { StartInfo = startInfo, EnableRaisingEvents = true };
        try
        {
            if (!process.Start()) throw new InvalidOperationException("No se pudo iniciar llama-server.");
        }
        catch
        {
            process.Dispose();
            ReleaseClaimedPort();
            throw;
        }

        Volatile.Write(ref _serverProcess, process);
        Volatile.Write(ref _serverLifetime, new CancellationTokenSource());
        Volatile.Write(ref _baseAddress, new Uri($"http://127.0.0.1:{port}/", UriKind.Absolute));
        _stdoutPump = PumpOutputAsync(process.StandardOutput, "stdout");
        _stderrPump = PumpOutputAsync(process.StandardError, "stderr");
        await WriteLogAsync($"Iniciado llama-server {backend}, PID {process.Id}, modelo {spec.Id}, puerto {port}.")
            .ConfigureAwait(false);

        try
        {
            await WaitUntilHealthyAsync(process, port, StartupTimeout, cancellationToken).ConfigureAwait(false);
            if (backend == RuntimePreference.Vulkan)
            {
                var offloadedLayers = await ReadServerOffloadedLayersAsync(cancellationToken).ConfigureAwait(false);
                _lastOffloadedLayers = offloadedLayers;
                if (offloadedLayers <= 0)
                    throw new InvalidOperationException("El log del proceso Vulkan propio no confirma ninguna capa offload a GPU.");
                await WriteLogAsync($"Modelo {spec.Id}: el log del proceso Vulkan propio confirma {offloadedLayers} capas offload a GPU.")
                    .ConfigureAwait(false);
            }
            else
            {
                _lastOffloadedLayers = 0;
                await WriteLogAsync($"Modelo {spec.Id}: CPU forzada con --device none, -ngl 0 y offload desactivado.")
                    .ConfigureAwait(false);
            }
        }
        catch
        {
            await StopCoreAsync().ConfigureAwait(false);
            throw;
        }
    }

    private async Task<string> ProbeVulkanDevicesAsync(string fullServerPath, CancellationToken cancellationToken)
    {
        var packageDirectory = Path.GetDirectoryName(fullServerPath)!;
        using var process = new Process
        {
            StartInfo = VulkanProbeProcess.CreateStartInfo(fullServerPath, packageDirectory),
            EnableRaisingEvents = true
        };
        ConfigureVerifiedPackageEnvironment(process.StartInfo, packageDirectory);
        var diagnosticNote = ConfigureDiagnosticEnvironment(process.StartInfo);
        if (diagnosticNote.Length > 0) await WriteLogAsync($"Sondeo --list-devices: {diagnosticNote}").ConfigureAwait(false);

        try
        {
            if (!process.Start()) throw new VulkanProbeFailureException("llama-server no inició el sondeo de dispositivos.");
        }
        catch (VulkanProbeFailureException) { throw; }
        catch (Exception ex) { throw new VulkanProbeFailureException($"No se pudo ejecutar --list-devices: {ex.Message}", ex); }

        var stdoutTask = process.StandardOutput.ReadToEndAsync();
        var stderrTask = process.StandardError.ReadToEndAsync();
        using var probeTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        probeTimeout.CancelAfter(VulkanProbeProcess.ProbeTimeout);
        try
        {
            await process.WaitForExitAsync(probeTimeout.Token).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            await KillProbeProcessAsync(process).ConfigureAwait(false);
            throw;
        }
        catch (OperationCanceledException ex)
        {
            await KillProbeProcessAsync(process).ConfigureAwait(false);
            throw new VulkanProbeFailureException($"El sondeo --list-devices superó {VulkanProbeProcess.ProbeTimeout.TotalSeconds:0} segundos.", ex);
        }
        catch (Exception ex)
        {
            await KillProbeProcessAsync(process).ConfigureAwait(false);
            throw new VulkanProbeFailureException($"Falló el sondeo --list-devices: {ex.Message}", ex);
        }

        var stdout = await stdoutTask.ConfigureAwait(false);
        var stderr = await stderrTask.ConfigureAwait(false);
        if (process.ExitCode != 0)
            throw new VulkanProbeFailureException(
                $"--list-devices terminó con código {process.ExitCode}: {TruncateProbeOutput(stderr + Environment.NewLine + stdout)}");
        return stdout + Environment.NewLine + stderr;
    }

    private static async Task KillProbeProcessAsync(Process process)
    {
        try
        {
            if (!process.HasExited)
            {
                process.Kill(entireProcessTree: true);
                await process.WaitForExitAsync().ConfigureAwait(false);
            }
        }
        catch (InvalidOperationException) { }
        catch (System.ComponentModel.Win32Exception) { }
    }

    internal static void ConfigureVerifiedPackageEnvironment(ProcessStartInfo startInfo, string packageDirectory)
    {
        var fullPackageDirectory = Path.GetFullPath(packageDirectory);
        startInfo.Environment.Remove("GGML_BACKEND_PATH");
        var systemDirectory = Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.Windows), "System32");
        startInfo.Environment["PATH"] = fullPackageDirectory + Path.PathSeparator + systemDirectory;
        startInfo.Environment.Remove("LLAMA_ARG_DEVICE");
        startInfo.Environment.Remove("LLAMA_ARG_N_GPU_LAYERS");
        startInfo.Environment.Remove("LLAMA_ARG_DEVICE_DRAFT");
        startInfo.Environment.Remove("LLAMA_ARG_N_GPU_LAYERS_DRAFT");
    }

    private string ConfigureDiagnosticEnvironment(ProcessStartInfo startInfo)
    {
        if (!HideVulkanDevicesForDiagnostics) return string.Empty;
        startInfo.Environment["GGML_VK_VISIBLE_DEVICES"] = string.Empty;
        return DiagnosticVulkanHideReason;
    }

    private const string DiagnosticVulkanHideReason = "GGML_VK_VISIBLE_DEVICES vacío por la simulación diagnóstica (no representa ausencia de bibliotecas ni cambios del sistema).";

    private async Task<int> ReadServerOffloadedLayersAsync(CancellationToken cancellationToken)
    {
        var path = _serverLogPath;
        if (path is null) return 0;
        var wait = Stopwatch.StartNew();
        while (wait.Elapsed < TimeSpan.FromSeconds(5))
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (File.Exists(path))
            {
                var log = await ReadSharedLogFileAsync(path, cancellationToken).ConfigureAwait(false);
                if (HasOffloadSummary(log)) return ParseOffloadedLayers(log);
            }
            await Task.Delay(TimeSpan.FromMilliseconds(250), cancellationToken).ConfigureAwait(false);
        }
        return 0;
    }

    internal static async Task<string> ReadSharedLogFileAsync(string path, CancellationToken cancellationToken)
    {
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read,
            FileShare.ReadWrite | FileShare.Delete, 16 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
        using var reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true, bufferSize: 1024, leaveOpen: false);
        return await reader.ReadToEndAsync(cancellationToken).ConfigureAwait(false);
    }

    private static bool HasOffloadSummary(string serverLog) => Regex.IsMatch(serverLog,
        @"\boffloaded\s+[0-9]+(?:\s*/\s*[0-9]+)?\s+layers?\s+to\s+GPU\b",
        RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);

    internal static int ParseOffloadedLayers(string serverLog)
    {
        ArgumentNullException.ThrowIfNull(serverLog);
        var matches = Regex.Matches(serverLog,
            @"\boffloaded\s+(?<layers>[0-9]+)(?:\s*/\s*[0-9]+)?\s+layers?\s+to\s+GPU\b",
            RegexOptions.IgnoreCase | RegexOptions.CultureInvariant);
        var highest = 0;
        foreach (Match match in matches)
            if (int.TryParse(match.Groups["layers"].Value, out var layers)) highest = Math.Max(highest, layers);
        return highest;
    }

    private static string TruncateProbeOutput(string output)
    {
        const int maxLength = 1200;
        var trimmed = output.Trim();
        return trimmed.Length <= maxLength ? trimmed : trimmed[..maxLength] + "…";
    }

    private async Task WaitUntilHealthyAsync(Process process, int port, TimeSpan timeout, CancellationToken cancellationToken)
    {
        var stopwatch = Stopwatch.StartNew();
        string lastFailure = "sin respuesta";
        while (stopwatch.Elapsed < timeout)
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (process.HasExited)
                throw new InvalidOperationException($"llama-server terminó durante el inicio (código {process.ExitCode}); {lastFailure}.");

            if (TryGetListeningProcessId(port, out var listeningPid) && listeningPid == process.Id)
            {
                using var healthTimeout = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
                healthTimeout.CancelAfter(HealthRequestTimeout);
                try
                {
                    using var response = await _httpClient.GetAsync(new Uri(BaseAddress, "health"), healthTimeout.Token)
                        .ConfigureAwait(false);
                    var body = await response.Content.ReadAsStringAsync(healthTimeout.Token).ConfigureAwait(false);
                    if (response.StatusCode == HttpStatusCode.TooManyRequests)
                        throw new LlamaRateLimitException(body);
                    if (response.StatusCode == HttpStatusCode.OK && IsStrictHealthyJson(body)) return;
                    lastFailure = $"HTTP {(int)response.StatusCode}, body={body}";
                }
                catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
                {
                    lastFailure = "timeout al consultar /health";
                }
                catch (HttpRequestException ex)
                {
                    lastFailure = ex.Message;
                }
            }
            else
            {
                lastFailure = "el puerto todavía no pertenece al proceso llama-server iniciado por esta demo";
            }

            await Task.Delay(HealthPollInterval, cancellationToken).ConfigureAwait(false);
        }
        throw new TimeoutException($"llama-server no pasó la comprobación estricta de /health en {timeout.TotalSeconds:0} segundos; último estado: {lastFailure}.");
    }

    internal static bool IsStrictHealthyJson(string body)
    {
        try
        {
            using var document = JsonDocument.Parse(body);
            return document.RootElement.ValueKind == JsonValueKind.Object
                && document.RootElement.TryGetProperty("status", out var status)
                && status.ValueKind == JsonValueKind.String
                && string.Equals(status.GetString(), "ok", StringComparison.Ordinal);
        }
        catch (JsonException) { return false; }
    }

    private async Task VerifyModelAsync(ModelSpec spec, string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path)) throw new FileNotFoundException("No se encontró el modelo local.", path);
        if (spec.ExpectedSize <= 0 || spec.ExpectedSha256.Length != 64 || !spec.ExpectedSha256.All(Uri.IsHexDigit))
            throw new InvalidDataException("El modelo no tiene tamaño o SHA-256 esperado válido en su perfil.");
        var info = new FileInfo(path);
        if (info.Length != spec.ExpectedSize)
            throw new InvalidDataException($"El tamaño del modelo {spec.Id} no coincide con el manifiesto ({info.Length} != {spec.ExpectedSize}).");
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 1024 * 1024,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        var hash = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken).ConfigureAwait(false)).ToLowerInvariant();
        if (!string.Equals(hash, spec.ExpectedSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"El SHA-256 del modelo {spec.Id} no coincide con su perfil.");
    }

    private async Task VerifyServerAsync(string path, CancellationToken cancellationToken)
    {
        if (!File.Exists(path)) throw new FileNotFoundException("No se encontró llama-server b11457.", path);
        var manifestPath = Path.Combine(_paths.LabDirectory, "manifests", "runtime_asset_hashes_120.json");
        if (!File.Exists(manifestPath)) throw new FileNotFoundException("No se encontró el manifiesto de integridad del runtime.", manifestPath);

        using var manifest = JsonDocument.Parse(await File.ReadAllTextAsync(manifestPath, cancellationToken).ConfigureAwait(false));
        if (!manifest.RootElement.TryGetProperty("files", out var files) || files.ValueKind != JsonValueKind.Array)
            throw new InvalidDataException("El manifiesto de runtime no contiene la lista files.");
        JsonElement serverRecord = default;
        foreach (var file in files.EnumerateArray())
        {
            if (!file.TryGetProperty("path", out var pathElement) || pathElement.ValueKind != JsonValueKind.String) continue;
            var relative = pathElement.GetString()!.Replace('\\', '/');
            if (relative.EndsWith("tools/llama.cpp/b11457/llama-server.exe", StringComparison.OrdinalIgnoreCase))
            {
                serverRecord = file;
                break;
            }
        }

        if (serverRecord.ValueKind != JsonValueKind.Object
            || !serverRecord.TryGetProperty("sha256", out var shaElement)
            || shaElement.ValueKind != JsonValueKind.String
            || !string.Equals(shaElement.GetString(), ExpectedServerSha256, StringComparison.OrdinalIgnoreCase)
            || !serverRecord.TryGetProperty("size_bytes", out var sizeElement)
            || !sizeElement.TryGetInt64(out var expectedSize))
            throw new InvalidDataException("El registro llama-server de b11457 no coincide con la huella fijada.");

        var info = new FileInfo(path);
        if (info.Length != expectedSize) throw new InvalidDataException("El tamaño de llama-server no coincide con el manifiesto.");
        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read, 64 * 1024,
            FileOptions.Asynchronous | FileOptions.SequentialScan);
        var actualHash = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken).ConfigureAwait(false)).ToLowerInvariant();
        if (!string.Equals(actualHash, ExpectedServerSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("El SHA-256 de llama-server no coincide con b11457 verificado.");
    }

    private async Task<string> ReadCanonicalSystemPromptAsync(CancellationToken cancellationToken)
    {
        var benchmarkPath = Path.Combine(_paths.LabDirectory, "benchmark_smoke_test_v2.json");
        if (!File.Exists(benchmarkPath)) throw new FileNotFoundException("No se encontró benchmark_smoke_test_v2.json.", benchmarkPath);
        using var document = JsonDocument.Parse(await File.ReadAllTextAsync(benchmarkPath, cancellationToken).ConfigureAwait(false));
        if (document.RootElement.ValueKind != JsonValueKind.Object
            || !document.RootElement.TryGetProperty("system_prompt", out var prompt)
            || prompt.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(prompt.GetString()))
            throw new InvalidDataException("benchmark_smoke_test_v2.json no contiene un system_prompt literal válido.");
        return prompt.GetString()!;
    }

    private async Task CaptureExchangeAsync(string requestJson, HttpStatusCode statusCode, string responseJson)
    {
        var sequence = Interlocked.Increment(ref _requestSequence);
        var stamp = DateTimeOffset.UtcNow.ToString("yyyyMMddTHHmmssfffZ", System.Globalization.CultureInfo.InvariantCulture);
        var stem = Path.Combine(_paths.SessionDirectory, $"generation-{stamp}-{sequence:D4}");
        try
        {
            await File.WriteAllTextAsync(stem + ".request.json", requestJson, new UTF8Encoding(false)).ConfigureAwait(false);
            await File.WriteAllTextAsync(stem + ".response.json", responseJson, new UTF8Encoding(false)).ConfigureAwait(false);
            await WriteLogAsync($"HTTP {(int)statusCode}; intercambio guardado como {Path.GetFileName(stem)}.").ConfigureAwait(false);
        }
        catch (IOException ex)
        {
            await WriteLogAsync($"No se pudo guardar el intercambio HTTP crudo: {ex.Message}").ConfigureAwait(false);
        }
        catch (UnauthorizedAccessException ex)
        {
            await WriteLogAsync($"No se pudo guardar el intercambio HTTP crudo: {ex.Message}").ConfigureAwait(false);
        }
    }

    private async Task PumpOutputAsync(StreamReader reader, string streamName)
    {
        try
        {
            while (await reader.ReadLineAsync().ConfigureAwait(false) is { } line)
                await WriteLogAsync($"[{streamName}] {line}").ConfigureAwait(false);
        }
        catch (ObjectDisposedException) { }
        catch (IOException ex) { await WriteLogAsync($"[{streamName}] error leyendo salida: {ex.Message}").ConfigureAwait(false); }
    }

    private async Task WriteLogAsync(string message)
    {
        var line = $"{DateTimeOffset.UtcNow:O} {message}";
        try
        {
            if (_runtimeLogPath is not null)
            {
                await _logGate.WaitAsync().ConfigureAwait(false);
                try { await File.AppendAllTextAsync(_runtimeLogPath, line + Environment.NewLine, new UTF8Encoding(false)).ConfigureAwait(false); }
                finally { _logGate.Release(); }
            }
        }
        catch (IOException) { }
        catch (UnauthorizedAccessException) { }

        var listeners = Log;
        if (listeners is null) return;
        foreach (Action<string> listener in listeners.GetInvocationList())
        {
            try { listener(message); }
            catch { /* Observers cannot interrupt process ownership or cleanup. */ }
        }
    }

    private async Task StopCoreAsync()
    {
        Volatile.Write(ref _isLoaded, false);
        Volatile.Write(ref _loadedModel, null);
        Volatile.Write(ref _activeBackend, null);
        Volatile.Write(ref _baseAddress, null);
        _lastOffloadedLayers = null;
        var serverLifetime = Interlocked.Exchange(ref _serverLifetime, null);
        serverLifetime?.Cancel();
        serverLifetime?.Dispose();

        var process = Interlocked.Exchange(ref _serverProcess, null);
        if (process is not null)
        {
            try
            {
                if (!process.HasExited)
                {
                    await WriteLogAsync($"Deteniendo únicamente el proceso llama-server PID {process.Id} iniciado por esta demo.")
                        .ConfigureAwait(false);
                    process.Kill(entireProcessTree: true);
                    using var wait = new CancellationTokenSource(TimeSpan.FromSeconds(15));
                    try { await process.WaitForExitAsync(wait.Token).ConfigureAwait(false); }
                    catch (OperationCanceledException)
                    {
                        if (!process.HasExited) process.Kill(entireProcessTree: true);
                        await process.WaitForExitAsync().ConfigureAwait(false);
                    }
                }
            }
            catch (InvalidOperationException) { }
            catch (System.ComponentModel.Win32Exception ex)
            {
                await WriteLogAsync($"No se pudo terminar el proceso propio: {ex.Message}").ConfigureAwait(false);
            }

            try { if (_stdoutPump is not null) await _stdoutPump.ConfigureAwait(false); }
            catch (IOException) { }
            try { if (_stderrPump is not null) await _stderrPump.ConfigureAwait(false); }
            catch (IOException) { }
            process.Dispose();
        }
        _stdoutPump = null;
        _stderrPump = null;
        ReleaseClaimedPort();
    }

    private int AcquireDedicatedPort()
    {
        lock (PortLock)
        {
            for (var port = DedicatedPortStart; port <= DedicatedPortEnd; port++)
            {
                if (ClaimedPorts.Contains(port)) continue;
                try
                {
                    using var listener = new TcpListener(IPAddress.Loopback, port);
                    listener.Start();
                    listener.Stop();
                    ClaimedPorts.Add(port);
                    return port;
                }
                catch (SocketException) { }
            }
        }
        throw new InvalidOperationException($"No hay puertos libres en el rango dedicado {DedicatedPortStart}-{DedicatedPortEnd}.");
    }

    private void ReleaseClaimedPort()
    {
        if (_claimedPort is not int port) return;
        lock (PortLock) ClaimedPorts.Remove(port);
        _claimedPort = null;
    }

    private static bool TryGetListeningProcessId(int port, out int processId)
    {
        processId = 0;
        const int afInet = 2;
        const int tcpTableOwnerPidListener = 3;
        const uint errorInsufficientBuffer = 122;
        var size = 0;
        var result = GetExtendedTcpTable(IntPtr.Zero, ref size, false, afInet, tcpTableOwnerPidListener, 0);
        if (result != errorInsufficientBuffer || size <= sizeof(uint)) return false;
        var table = Marshal.AllocHGlobal(size);
        try
        {
            result = GetExtendedTcpTable(table, ref size, false, afInet, tcpTableOwnerPidListener, 0);
            if (result != 0) return false;
            var count = Marshal.ReadInt32(table);
            var rowSize = Marshal.SizeOf<MibTcpRowOwnerPid>();
            var rowAddress = IntPtr.Add(table, sizeof(uint));
            for (var i = 0; i < count; i++)
            {
                var row = Marshal.PtrToStructure<MibTcpRowOwnerPid>(IntPtr.Add(rowAddress, i * rowSize));
                if (DecodePort(row.LocalPort) == port)
                {
                    processId = checked((int)row.OwningProcessId);
                    return true;
                }
            }
            return false;
        }
        finally { Marshal.FreeHGlobal(table); }
    }

    private static int DecodePort(uint networkOrderPort) =>
        (ushort)IPAddress.NetworkToHostOrder(unchecked((short)(networkOrderPort & 0xffff)));

    [DllImport("iphlpapi.dll", SetLastError = true)]
    private static extern uint GetExtendedTcpTable(
        IntPtr tcpTable,
        ref int outBufferLength,
        [MarshalAs(UnmanagedType.Bool)] bool sort,
        int ipVersion,
        int tableClass,
        uint reserved);

    [StructLayout(LayoutKind.Sequential)]
    private struct MibTcpRowOwnerPid
    {
        public uint State;
        public uint LocalAddress;
        public uint LocalPort;
        public uint RemoteAddress;
        public uint RemotePort;
        public uint OwningProcessId;
    }

    private static string SanitizeFilePart(string input)
    {
        var invalid = Path.GetInvalidFileNameChars();
        var result = new string(input.Select(ch => invalid.Contains(ch) ? '_' : ch).ToArray());
        return string.IsNullOrWhiteSpace(result) ? "model" : result;
    }

    private void ThrowIfDisposed()
    {
        if (_disposed) throw new ObjectDisposedException(nameof(LlamaRuntime));
    }
}

public sealed class LlamaRateLimitException(string responseBody)
    : Exception("llama-server devolvió HTTP 429. La ejecución se detuvo y no se reintentó.")
{
    public string ResponseBody { get; } = responseBody;
}
