using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using WritingDemo.Core;

namespace WritingApp.Shared;

public sealed record GpuPlan(int Index, string Id, string Name, long FreeBytes, long TotalBytes,
    int EstimatedLayers, int FullLayers, long EstimatedBytes, long MarginBytes, string? EstimateError, bool IsIntegrated = false);
public sealed record RuntimeInventory(string Runtime, string DriverFingerprint, int FullLayers, GpuPlan[] Devices);
public sealed record RuntimePlacement(int DeviceIndex, string? DeviceId, int GpuLayers)
{
    public static RuntimePlacement Cpu { get; } = new(-1, null, 0);
    public string Key => GpuLayers == 0 ? "CPU" : $"Vulkan/{DeviceId}/{GpuLayers}";
}
public interface IPlacementEngine : IInferenceEngine
{
    TimeSpan GenerationTimeout { get; set; }
    Task<RuntimeInventory> InspectAsync(string modelPath, int context, CancellationToken ct);
    Task<EngineState> LoadPlacementAsync(ModelEntry model, string path, RuntimePlacement placement, int context, CancellationToken ct);
}
public interface IRuntimeProgress
{
    event Action<string>? StatusChanged;
}
public sealed record PlacementTrial(RuntimePlacement Placement, BackendTrial[] Samples, string? Failure, string? FailureStage = null);
public sealed record AdaptiveProfile(string Key, string ModelId, string Runtime, string Driver,
    int Context, RuntimePlacement Selected, string Reason, PlacementTrial[] Trials, DateTimeOffset DateUtc, GpuPlan[] Estimates);

public static class AdaptiveRuntimePolicy
{
    public const string Version = "paired-placement-v2";
    public const int MaximumGpuTrials = 3;
    public static readonly TimeSpan CalibrationBudget = TimeSpan.FromMinutes(10);
    public static readonly TimeSpan FailedGpuRetention = TimeSpan.FromHours(24);

    public static bool CpuComplete(PlacementTrial? trial) => trial is not null && trial.Failure is null &&
        trial.Samples.Length == BackendCalibrationPolicy.Samples && trial.Samples.All(s =>
            s.Failure is null && s.FinishReason == "stop" && s.Tokens > 0 && double.IsFinite(s.Seconds) && s.Seconds > 0);

    public static TimeSpan GpuGenerationTimeout(PlacementTrial cpu) => TimeSpan.FromSeconds(CpuComplete(cpu)
        ? Math.Clamp(BackendCalibrationPolicy.Median(cpu.Samples.Select(s => s.Seconds)) * 3, 20, 120) : 120);

    // A smaller placement can fix allocation failures. Repeating nearly the same graph
    // after a generation hang/device loss only prolongs the wait on the same adapter.
    public static bool CanReduce(PlacementTrial trial) => trial.Failure is not null && trial.FailureStage is "load" or "memory";

    public static RuntimePlacement[] Candidates(RuntimeInventory inventory) => inventory.Devices
        .Where(d => d.EstimatedLayers > 0 && d.EstimatedLayers <= d.FullLayers && d.EstimatedBytes > 0 &&
                    d.FreeBytes >= d.EstimatedBytes + d.MarginBytes)
        .OrderBy(d => d.IsIntegrated)
        .ThenByDescending(d => (double)d.EstimatedLayers / d.FullLayers)
        .ThenByDescending(d => d.FreeBytes)
        .Select(d => new RuntimePlacement(d.Index, d.Id, d.EstimatedLayers)).ToArray();

    public static RuntimePlacement? Smaller(RuntimePlacement placement) => placement.GpuLayers > 1
        ? placement with { GpuLayers = placement.GpuLayers - 1 } : null;

    public static bool Usable(PlacementTrial trial) => trial.Failure is null &&
        trial.Samples.Length == BackendCalibrationPolicy.Samples && trial.Samples.All(s =>
            s.Failure is null && s.FinishReason == "stop" && s.Tokens > 0 &&
            double.IsFinite(s.Seconds) && s.Seconds > 0 && s.ParserStatus is "STRICT" or "RECOVERED");

    public static (RuntimePlacement Placement, string Reason) Choose(IReadOnlyList<PlacementTrial> trials)
    {
        var cpu = trials.FirstOrDefault(t => t.Placement.GpuLayers == 0);
        var cpuComplete = CpuComplete(cpu);
        var gpu = trials.Where(t => t.Placement.GpuLayers > 0 && Usable(t))
            .OrderBy(t => BackendCalibrationPolicy.Median(t.Samples.Select(s => s.Seconds))).FirstOrDefault();
        if (gpu is not null && (!cpuComplete || BackendCalibrationPolicy.Median(cpu!.Samples.Select(s => s.Seconds)) >=
            BackendCalibrationPolicy.Median(gpu.Samples.Select(s => s.Seconds)) * BackendCalibrationPolicy.RequiredSpeedup))
            return (gpu.Placement, $"Vulkan medido: {gpu.Placement.GpuLayers} capas en GPU; " +
                $"mediana {BackendCalibrationPolicy.Median(gpu.Samples.Select(s => s.Seconds)):F1} s. " +
                (cpuComplete ? $"CPU: {BackendCalibrationPolicy.Median(cpu!.Samples.Select(s => s.Seconds)):F1} s." : "CPU no completó la calibración."));
        return (RuntimePlacement.Cpu, "CPU seleccionada: Vulkan no demostró tres respuestas utilizables con una mejora mínima del 15 %.");
    }
}

/// <summary>One model, fresh isolated workers per candidate, bounded technical calibration.</summary>
public sealed class AdaptiveInferenceEngine(Func<bool, IPlacementEngine> factory, string profileDirectory,
    Func<string> hostIdentity, Func<bool>? calibrationAllowed = null) : IInferenceEngine, IRuntimeProgress
{
    public AdaptiveInferenceEngine(Func<bool, IPlacementEngine> factory, string profileDirectory, string hostIdentity, Func<bool>? calibrationAllowed = null)
        : this(factory, profileDirectory, () => hostIdentity, calibrationAllowed) { }
    private readonly SemaphoreSlim _gate = new(1, 1);
    private IPlacementEngine? _active;
    private EngineState? _state;
    private RuntimeInventory? _inventory;
    private string? _profilePath;
    public event Action<string>? StatusChanged;
    public AdaptiveProfile? LastProfile { get; private set; }

    private static bool Reusable(AdaptiveProfile? p, RuntimeInventory inventory, string key, string modelId)
    {
        if (p?.Key != key || p.ModelId != modelId || p.Selected is null || p.Estimates is null || p.Trials is null ||
            p.Trials.Length == 0 || p.Trials.Any(t => t is null || t.Placement is null || t.Samples is null || t.Samples.Any(s => s is null)))
            return false;
        if (AdaptiveRuntimePolicy.Choose(p.Trials).Placement != p.Selected) return false;
        if (p.DateUtc > DateTimeOffset.UtcNow.AddMinutes(5)) return false;
        if (p.Selected.GpuLayers == 0 && p.Trials.Any(t => t.Failure is not null) &&
            DateTimeOffset.UtcNow - p.DateUtc > (AdaptiveRuntimePolicy.CpuComplete(p.Trials.FirstOrDefault(t => t.Placement.GpuLayers == 0))
                ? AdaptiveRuntimePolicy.FailedGpuRetention : TimeSpan.FromMinutes(5))) return false;
        if (p.Selected.GpuLayers > 0 && !inventory.Devices.Any(d => d.Id == p.Selected.DeviceId &&
                d.Index == p.Selected.DeviceIndex && d.EstimatedLayers >= p.Selected.GpuLayers)) return false;
        // Retry calibration after a substantial budget improvement, not after every freed byte.
        return !inventory.Devices.Any(d => p.Estimates.Any(old => old.Id == d.Id &&
            d.EstimatedLayers >= old.EstimatedLayers + Math.Max(2, old.EstimatedLayers / 4)));
    }

    public async Task<EngineState> LoadAsync(ModelEntry model, string modelPath, BackendPreference backend,
        int context, CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            await UnloadCoreAsync().ConfigureAwait(false);
            LastProfile = null; _profilePath = null; _inventory = null;
            if (backend == BackendPreference.Cpu)
                return await LoadSelectedAsync(model, modelPath, RuntimePlacement.Cpu, backend, context, null, ct).ConfigureAwait(false);
            RuntimeInventory inventory;
            try
            {
                StatusChanged?.Invoke("Consultando GPU y estimando memoria para el contexto elegido…");
                await using var inspector = factory(true);
                inventory = await inspector.InspectAsync(modelPath, context, ct).ConfigureAwait(false);
                if (inventory.Devices is null || inventory.FullLayers <= 0) throw new InvalidDataException("Inventario de GPU inválido.");
                _inventory = inventory;
            }
            catch (Exception e) when (e is not OperationCanceledException && backend == BackendPreference.AutoVulkanCpu)
            {
                return await LoadSelectedAsync(model, modelPath, RuntimePlacement.Cpu, backend, context,
                    "CPU tras fallo de la sonda Vulkan. " + e.Message, ct).ConfigureAwait(false);
            }
            var candidates = AdaptiveRuntimePolicy.Candidates(inventory).ToList();
            if (candidates.Count == 0 && backend == BackendPreference.AutoVulkanCpu)
                return await LoadSelectedAsync(model, modelPath, RuntimePlacement.Cpu, backend, context,
                    "CPU seleccionada: no hay una distribución Vulkan estimada dentro del presupuesto actual.", ct).ConfigureAwait(false);
            if (backend == BackendPreference.Vulkan)
            {
                Exception? last = null;
                var reduced = new HashSet<string>();
                for (var i = 0; i < AdaptiveRuntimePolicy.MaximumGpuTrials && candidates.Count > 0; i++)
                {
                    var candidate = candidates[0]; candidates.RemoveAt(0);
                    try
                    {
                        return await LoadSelectedAsync(model, modelPath, candidate, backend, context,
                            "Vulkan elegido manualmente; distribución estimada según memoria disponible.", ct).ConfigureAwait(false);
                    }
                    catch (Exception e) when (e is not OperationCanceledException)
                    {
                        last = e;
                        if (reduced.Add(candidate.DeviceId!) && AdaptiveRuntimePolicy.Smaller(candidate) is { } smaller)
                            candidates.Insert(0, smaller);
                    }
                }
                throw new InvalidOperationException("Vulkan no pudo cargar una distribución segura. Puedes elegir CPU o Gemma E2B. " + last?.Message, last);
            }

            var initialHost = hostIdentity();
            var identity = $"{AdaptiveRuntimePolicy.Version}|{initialHost}|{inventory.Runtime}|{inventory.DriverFingerprint}|" +
                $"{model.Sha256}|{PortablePrompt.Hash(model)}|{context}|{Environment.ProcessorCount}|" +
                JsonSerializer.Serialize(model.Sampling, AppJsonContext.Default.SamplingOptions);
            var key = Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(identity)));
            Directory.CreateDirectory(profileDirectory);
            _profilePath = Path.Combine(profileDirectory, key + ".json");
            AdaptiveProfile? profile = null;
            if (File.Exists(_profilePath))
            {
                try
                {
                    profile = JsonSerializer.Deserialize(await File.ReadAllTextAsync(_profilePath, ct).ConfigureAwait(false), AppJsonContext.Default.AdaptiveProfile);
                    if (!Reusable(profile, inventory, key, model.Id)) profile = null;
                }
                catch (JsonException) { profile = null; }
            }
            if (profile is null)
            {
                var trials = new List<PlacementTrial>();
                var reduced = new HashSet<string>();
                await using var calibration = new CalibrationGuard(ct, AdaptiveRuntimePolicy.CalibrationBudget, calibrationAllowed);
                try
                {
                    trials.Add(await MeasureAsync(model, modelPath, RuntimePlacement.Cpu, context, TimeSpan.FromSeconds(180), calibration).ConfigureAwait(false));
                }
                catch (OperationCanceledException) when (!ct.IsCancellationRequested)
                {
                    calibration.ThrowIfInterrupted();
                    trials.Add(new(RuntimePlacement.Cpu, [], "Se agotó el plazo total de calibración."));
                }
                var gpuTimeout = AdaptiveRuntimePolicy.GpuGenerationTimeout(trials[0]);
                var cpuMedian = AdaptiveRuntimePolicy.CpuComplete(trials[0]) ? BackendCalibrationPolicy.Median(trials[0].Samples.Select(s => s.Seconds)) : (double?)null;
                for (var i = 0; i < AdaptiveRuntimePolicy.MaximumGpuTrials && candidates.Count > 0 && !calibration.Token.IsCancellationRequested; i++)
                {
                    var candidate = candidates[0]; candidates.RemoveAt(0);
                    PlacementTrial trial;
                    try { trial = await MeasureAsync(model, modelPath, candidate, context, gpuTimeout, calibration, cpuMedian).ConfigureAwait(false); }
                    catch (OperationCanceledException) when (!ct.IsCancellationRequested)
                    {
                        calibration.ThrowIfInterrupted();
                        trials.Add(new(candidate, [], "Se agotó el plazo total de calibración."));
                        break;
                    }
                    trials.Add(trial);
                    if (AdaptiveRuntimePolicy.CanReduce(trial) && reduced.Add(candidate.DeviceId!) && AdaptiveRuntimePolicy.Smaller(candidate) is { } smaller)
                        candidates.Insert(0, smaller);
                }
                calibration.ThrowIfInterrupted();
                var choice = AdaptiveRuntimePolicy.Choose(trials);
                if (calibration.Token.IsCancellationRequested)
                    choice.Reason += " Se alcanzó el límite de diez minutos; se conserva la mejor distribución comprobada.";
                profile = new(key, model.Id, inventory.Runtime, inventory.DriverFingerprint, context,
                    choice.Placement, choice.Reason, trials.ToArray(), DateTimeOffset.UtcNow, inventory.Devices);
                if (hostIdentity() != initialHost)
                {
                    profile = profile with { Selected = RuntimePlacement.Cpu,
                        Reason = "Cambió la alimentación o el modo de energía durante la comparación. CPU para esta sesión; la calibración no se guardó." };
                    _profilePath = null;
                }
                else await SaveAsync(profile, ct).ConfigureAwait(false);
            }
            LastProfile = profile;
            try
            {
                return await LoadSelectedAsync(model, modelPath, profile.Selected, backend, context, profile.Reason, ct).ConfigureAwait(false);
            }
            catch (Exception e) when (e is not OperationCanceledException && profile.Selected.GpuLayers > 0)
            {
                InvalidateProfile();
                return await LoadSelectedAsync(model, modelPath, RuntimePlacement.Cpu, backend, context,
                    "El presupuesto o la carga Vulkan cambiaron; CPU para esta sesión. " + e.Message, ct).ConfigureAwait(false);
            }
        }
        finally { _gate.Release(); }
    }

    private async Task<PlacementTrial> MeasureAsync(ModelEntry model, string path, RuntimePlacement placement,
        int context, TimeSpan generationTimeout, CalibrationGuard calibration, double? cpuMedian = null)
    {
        var ct = calibration.Token;
        var samples = new List<BackendTrial>();
        await using var worker = factory(placement.GpuLayers > 0);
        worker.GenerationTimeout = generationTimeout;
        var label = placement.Key;
        var stage = "load";
        try
        {
            calibration.Check();
            StatusChanged?.Invoke($"Calibrando {label}: carga y calentamiento. Puedes cancelar.");
            EngineState state;
            using (var loadDeadline = CancellationTokenSource.CreateLinkedTokenSource(ct))
            {
                if (placement.GpuLayers > 0) loadDeadline.CancelAfter(generationTimeout < TimeSpan.FromSeconds(30) ? TimeSpan.FromSeconds(30) : generationTimeout);
                try { state = await worker.LoadPlacementAsync(model, path, placement, context, loadDeadline.Token).ConfigureAwait(false); }
                catch (OperationCanceledException) when (loadDeadline.IsCancellationRequested && !ct.IsCancellationRequested)
                { stage = "load-timeout"; throw new TimeoutException("La carga Vulkan agotó el plazo de la comparación."); }
            }
            VerifyPlacement(state, placement);
            var exercise = BackendCalibrationPolicy.Exercise;
            for (var i = 0; i <= BackendCalibrationPolicy.Samples; i++)
            {
                calibration.Check(); stage = "generation";
                StatusChanged?.Invoke($"Calibrando {label}: " + (i == 0 ? "calentamiento" : $"muestra {i}/{BackendCalibrationPolicy.Samples}"));
                var output = await worker.GenerateAsync(exercise, exercise.IncorrectExample, 42, ct).ConfigureAwait(false);
                var parsed = FeedbackParser.Parse(output.Content, exercise.IncorrectExample);
                Directory.CreateDirectory(profileDirectory);
                var validForeground = calibration.IsAllowed;
                var trace = new CalibrationTrace(model.Sha256, placement, i == 0, output, parsed.Status, DateTimeOffset.UtcNow, validForeground);
                var tracePath = Path.Combine(profileDirectory, "trace-" + Guid.NewGuid().ToString("N") + ".json");
                // A completed RAW is retained even when cancellation follows its return.
                await File.WriteAllTextAsync(tracePath, JsonSerializer.Serialize(trace, AppJsonContext.Default.CalibrationTrace), CancellationToken.None).ConfigureAwait(false);
                calibration.Check();
                if (i > 0) samples.Add(new(label, output.Seconds, output.Metrics?.OutputTokens ?? 0, output.FinishReason, parsed.Status, null));
                if (placement.GpuLayers > 0 && i > 0)
                {
                    if (output.FinishReason != "stop" || output.Metrics?.OutputTokens is not > 0 || parsed.Status is not ("STRICT" or "RECOVERED"))
                        return new(placement, samples.ToArray(), "Vulkan no completó una muestra utilizable; no puede cumplir las tres requeridas.", "unusable");
                    if (samples.Count == 2 && cpuMedian is { } baseline && samples.All(s => s.Seconds > baseline / BackendCalibrationPolicy.RequiredSpeedup))
                        return new(placement, samples.ToArray(), "Las dos muestras Vulkan superan el límite de mejora; una tercera no cambiaría la mediana.", "slower");
                }
            }
            return new(placement, samples.ToArray(), null);
        }
        catch (Exception e) when (e is not OperationCanceledException)
        {
            var allocation = e.Message.Contains("out of memory", StringComparison.OrdinalIgnoreCase) ||
                e.Message.Contains("out_of_device_memory", StringComparison.OrdinalIgnoreCase) ||
                e.Message.Contains("ErrorOutOfDeviceMemory", StringComparison.OrdinalIgnoreCase) ||
                e.Message.Contains("ENOMEM", StringComparison.OrdinalIgnoreCase);
            return new(placement, samples.ToArray(), e.Message, stage is "load" or "load-timeout" ? stage : e is TimeoutException ? "timeout" : allocation ? "memory" : "generation");
        }
    }

    private async Task<EngineState> LoadSelectedAsync(ModelEntry model, string path, RuntimePlacement placement,
        BackendPreference requested, int context, string? reason, CancellationToken ct)
    {
        await UnloadCoreAsync().ConfigureAwait(false);
        _active = factory(placement.GpuLayers > 0);
        try
        {
            StatusChanged?.Invoke($"Cargando {placement.Key}…");
            var state = await _active.LoadPlacementAsync(model, path, placement, context, ct).ConfigureAwait(false);
            VerifyPlacement(state, placement);
            if (placement.GpuLayers > 0 && _inventory?.Devices.FirstOrDefault(d => d.Id == placement.DeviceId) is { } gpu)
                state = state with { Device = $"{gpu.Name} ({state.Device})" };
            if (placement.GpuLayers == 0 && model.Family == "qwen")
                reason = (reason is null ? "" : reason + " ") + "Gemma E2B puede reducir la espera en CPU; puedes elegirlo sin borrar Qwen.";
            return _state = state with { Requested = requested, FallbackReason = reason };
        }
        catch { await UnloadCoreAsync().ConfigureAwait(false); throw; }
    }

    private static void VerifyPlacement(EngineState state, RuntimePlacement placement)
    {
        if (placement.GpuLayers == 0 ? state.Backend != "CPU" || state.OffloadedLayers != 0 :
            state.Backend != "Vulkan" || state.OffloadedLayers != placement.GpuLayers || state.AdapterId != placement.DeviceId)
            throw new InvalidDataException("El motor no confirmó el adaptador y las capas solicitados.");
    }

    private async Task SaveAsync(AdaptiveProfile profile, CancellationToken ct)
    {
        var temporary = _profilePath + ".tmp-" + Guid.NewGuid().ToString("N");
        await File.WriteAllTextAsync(temporary, JsonSerializer.Serialize(profile, AppJsonContext.Default.AdaptiveProfile), ct).ConfigureAwait(false);
        if (File.Exists(_profilePath)) File.Copy(_profilePath, _profilePath + ".previous-" + Guid.NewGuid().ToString("N"));
        File.Move(temporary, _profilePath!, true);
    }
    private void InvalidateProfile()
    {
        if (_profilePath is not null && File.Exists(_profilePath))
            File.Move(_profilePath, _profilePath + ".failed-" + Guid.NewGuid().ToString("N"));
    }
    public async Task<EngineOutput> GenerateAsync(WritingExercise exercise, string text, int seed, CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try { return await (_active ?? throw new InvalidOperationException("Carga un modelo primero.")).GenerateAsync(exercise, text, seed, ct).ConfigureAwait(false); }
        catch (Exception e) when (e is not OperationCanceledException && _state?.Backend == "Vulkan")
        {
            InvalidateProfile();
            await UnloadCoreAsync().ConfigureAwait(false);
            throw new IOException("Vulkan falló. Se liberó el motor; vuelve a cargar para recalibrar o elige CPU. La respuesta no se reintentó.", e);
        }
        finally { _gate.Release(); }
    }
    private async Task UnloadCoreAsync()
    {
        if (_active is not null) await _active.DisposeAsync().ConfigureAwait(false);
        _active = null; _state = null;
    }
    public async Task UnloadAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try { await UnloadCoreAsync().ConfigureAwait(false); }
        finally { _gate.Release(); }
    }
    public async ValueTask DisposeAsync() => await UnloadAsync().ConfigureAwait(false);
}

public sealed record CalibrationTrace(string ModelSha256, RuntimePlacement Placement, bool Warmup,
    EngineOutput Output, string ParserStatus, DateTimeOffset DateUtc, bool ForegroundValid = true);
