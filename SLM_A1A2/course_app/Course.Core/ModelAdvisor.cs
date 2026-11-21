using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using WritingApp.Shared;

namespace Course.Core;

public sealed record HardwareCapabilities(bool HasVulkan, string Description, string Fingerprint, bool LowMemory = false);
public sealed record ModelAdvice(ModelEntry Model, bool FitsEstimate, string Reason);
public sealed record AutoAdviceProfile(string Fingerprint, int Context, string ModelId, string ModelSha256,
    string Reason, DateTimeOffset DateUtc, bool TechnicalFallback, bool QwenRejected = false);

public interface IModelAdvisor
{
    ModelAdvice Recommend(IReadOnlyList<ModelEntry> models, DeviceProfile device, HardwareCapabilities hardware,
        CourseSettings settings, Func<ModelEntry, bool> available, AutoAdviceProfile? measured = null);
}

public sealed class BalancedModelAdvisor : IModelAdvisor
{
    public const string Version = "balanced-course-v3";
    public const string GemmaId = "13-gemma4-e2b-ud-q4-k-xl";
    public const string MiniId = "06-minicpm5-2b-q4-k-m";
    public const string LfmId = "09-lfm25-12b-q4-k-m";
    public static bool IsQwen4(ModelEntry model) => model.Family == "qwen" && (model.Id.Contains("4b", StringComparison.Ordinal) || model.Name.Contains("4B", StringComparison.Ordinal));
    public static bool Fits(ModelEntry model, DeviceProfile device, int context, bool available, bool lowMemory = false)
        => ModelMemoryPlanner.Plan(model, device, context, available, lowMemory).Fits;
    public ModelAdvice Recommend(IReadOnlyList<ModelEntry> models, DeviceProfile device, HardwareCapabilities hardware,
        CourseSettings settings, Func<ModelEntry, bool> available, AutoAdviceProfile? measured = null)
    {
        bool FitsNow(ModelEntry model) => Fits(model, device, settings.Context, available(model), hardware.LowMemory);
        bool HigherOptionNowFits(ModelEntry cached)
        {
            var resourceIds = new[] { GemmaId, MiniId, LfmId };
            var rank = Array.IndexOf(resourceIds, cached.Id);
            if (rank > 0 && resourceIds.Take(rank).Select(id => models.First(m => m.Id == id)).Any(FitsNow)) return true;
            return rank == 0 && measured?.QwenRejected != true && device.Platform == "Windows" && hardware.HasVulkan && settings.Backend != BackendPreference.Cpu &&
                models.Any(m => IsQwen4(m) && m.Quantization == "Q4_K_M" && FitsNow(m));
        }
        if (!settings.AutomaticModel && models.FirstOrDefault(m => m.Id == settings.ModelId) is { } manual)
            return new(manual, FitsNow(manual), "Elección manual. Se conserva el modelo y la cuantización que elegiste. " + ModelMemoryPlanner.Plan(manual, device, settings.Context, available(manual), hardware.LowMemory).Reason);
        if (measured is not null && measured.Fingerprint == hardware.Fingerprint && measured.Context == settings.Context &&
            (!measured.TechnicalFallback || DateTimeOffset.UtcNow - measured.DateUtc < TimeSpan.FromMinutes(5)) &&
            models.FirstOrDefault(m => m.Id == measured.ModelId && m.Sha256 == measured.ModelSha256) is { } cached &&
            FitsNow(cached) &&
            !HigherOptionNowFits(cached) &&
            (settings.Backend != BackendPreference.Cpu || !IsQwen4(cached)))
            return new(cached, true, "Elección medida en este equipo. " + measured.Reason);
        var resourceOrder = new[] { GemmaId, MiniId, LfmId }.Select(id => models.First(m => m.Id == id));
        var preferred = resourceOrder.ToList();
        // Vulkan presence is a provisional hint, never proof of speed or a device-specific whitelist.
        // Fresh Android installations start with Gemma; measured/manual Qwen remains available.
        if (device.Platform == "Windows" && hardware.HasVulkan && settings.Backend != BackendPreference.Cpu)
        {
            var qwen = models.Where(m => IsQwen4(m) && m.Quantization == "Q4_K_M").OrderByDescending(available).ThenByDescending(m => m.DownloadUrl is not null).First();
            preferred.Insert(0, qwen);
        }
        var selected = preferred.FirstOrDefault(FitsNow) ?? models.First(m => m.Id == LfmId);
        var plan = ModelMemoryPlanner.Plan(selected, device, settings.Context, available(selected), hardware.LowMemory);
        var fits = plan.Fits;
        var reason = IsQwen4(selected)
            ? "Hay Vulkan disponible y margen estimado de memoria. Propondremos Qwen y comprobaremos CPU, GPU y carga parcial antes de confirmar su uso automático."
            : "Se propone Gemma cuando cabe en memoria; MiniCPM o LFM cuando hace falta reducir el consumo. CPU y Vulkan se comparan después de preparar los pesos.";
        reason += " " + plan.Reason;
        if (!fits) reason = "Ninguna opción cumple ahora el margen previsto. Puedes elegir manualmente o liberar memoria antes de cargar. " + reason;
        return new(selected, fits, reason);
    }
    public static bool QwenQualified(EngineState state, AdaptiveProfile? profile)
    {
        if (state.Backend != "Vulkan" || profile is null) return false;
        var selected = profile.Trials.FirstOrDefault(t => t.Placement == profile.Selected);
        return selected is not null && AdaptiveRuntimePolicy.Usable(selected) &&
            BackendCalibrationPolicy.Median(selected.Samples.Select(s => s.Seconds)) <= 30;
    }
    public static string ProfileKey(string identity) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(identity)));
}

public sealed record PrepareResult(ModelEntry Model, EngineState? Engine, string Message, bool NeedsDownload);
public sealed record PreparationFailureTrace(DateTimeOffset DateUtc, string ModelId, string ModelSha256, int Context, string Error);

/// <summary>Application coordination; all CPU/Vulkan fitting remains in the shared, isolated engine.</summary>
public sealed class CourseRuntime : IAsyncDisposable
{
    private readonly AppServices _services;
    private readonly Func<IPlacementEngine> _placementFactory;
    private readonly Func<DeviceProfile> _device;
    private readonly Func<CancellationToken, Task<HardwareCapabilities>> _probe;
    private readonly IModelAdvisor _advisor = new BalancedModelAdvisor();
    private readonly string _adviceFile;
    private readonly Func<AdaptiveProfile?> _calibration;
    private readonly IReadOnlyList<ModelEntry> _models;
    private readonly SemaphoreSlim _gate = new(1, 1);
    private IInferenceEngine? _active;
    private string? _configurationKey;
    public event Action<string>? StatusChanged;
    public event Action? EngineStarting;
    public HardwareCapabilities Hardware { get; private set; } = new(false, "Consultando capacidades del equipo…", "unknown");
    public DeviceProfile Device => _device();
    public AppServices Services => _services;
    public IReadOnlyList<ModelEntry> Models => _models;
    public EngineState? State { get; private set; }
    public ModelEntry? LoadedModel { get; private set; }
    public CourseRuntime(AppServices services, Func<IPlacementEngine> placementFactory, Func<DeviceProfile> device,
        Func<CancellationToken, Task<HardwareCapabilities>> probe, string adviceFile, Func<AdaptiveProfile?>? calibration = null,
        IReadOnlyList<ModelEntry>? models = null)
    {
        _services = services; _placementFactory = placementFactory; _device = device; _probe = probe; _adviceFile = adviceFile;
        _calibration = calibration ?? (() => (services.Engine as AdaptiveInferenceEngine)?.LastProfile);
        _models = models ?? CourseModelCatalog.All;
        if (services.Engine is IRuntimeProgress progress) progress.StatusChanged += Forward;
    }
    private void Forward(string message) => StatusChanged?.Invoke(message);
    public async Task<ModelAdvice> RecommendAsync(CourseSettings settings, CancellationToken ct)
    {
        Hardware = await _probe(ct).ConfigureAwait(false);
        AutoAdviceProfile? profile = null;
        if (File.Exists(_adviceFile))
        {
            try { profile = JsonSerializer.Deserialize(await File.ReadAllTextAsync(_adviceFile, ct).ConfigureAwait(false), CourseJsonContext.Default.AutoAdviceProfile); }
            catch (JsonException) { }
        }
        return _advisor.Recommend(Models, Device, Hardware, settings, m => _services.ModelStore.FindExisting(m) is not null, profile);
    }
    public Task<RuntimeInventory> InspectAsync(ModelEntry model, int context, CancellationToken ct) => InspectCoreAsync(model, context, ct);
    private async Task<RuntimeInventory> InspectCoreAsync(ModelEntry model, int context, CancellationToken ct)
    {
        var path = await _services.ModelStore.FindVerifiedAsync(model, ct).ConfigureAwait(false) ?? throw new FileNotFoundException("Prepara o importa este modelo antes de consultar las capas.");
        await using var inspector = _placementFactory();
        return await inspector.InspectAsync(path, context, ct).ConfigureAwait(false);
    }
    public async Task<PrepareResult> PrepareAsync(ModelEntry model, CourseSettings settings, bool download,
        IProgress<DownloadProgress>? progress, CancellationToken ct)
    {
        settings.Validated();
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            Hardware = await _probe(ct).ConfigureAwait(false);
            var key = $"{model.Sha256}|{settings.Backend}|{settings.Context}|{settings.AdapterId}|{settings.GpuLayers}|{Hardware.Fingerprint}";
            if (State is not null && LoadedModel?.Id == model.Id && _configurationKey == key)
                return new(model, State, "El modelo ya está preparado con esta configuración.", false);
            await UnloadCoreAsync().ConfigureAwait(false);
            var path = await _services.ModelStore.FindVerifiedAsync(model, ct).ConfigureAwait(false);
            if (settings.AutomaticModel && !BalancedModelAdvisor.Fits(model, Device, settings.Context, path is not null, Hardware.LowMemory))
                return new(model, null, "No hay margen estimado de RAM o espacio para la preparación automática. Libera recursos o elige manualmente un modelo menor en Ajustes.", false);
            if (path is null && !download) return new(model, null, "Descarga o importa este modelo para empezar el Writing.", true);
            if (path is null) path = await _services.Downloads.EnsureAsync(model, progress, ct).ConfigureAwait(false);
            try { State = await LoadCoreAsync(model, path, settings, ct).ConfigureAwait(false); }
            catch (Exception e) when (settings.AutomaticModel && e is not OperationCanceledException)
            { return await RecoverPreparationAsync(model, settings, e, ct).ConfigureAwait(false); }
            if (settings.AutomaticModel && BalancedModelAdvisor.IsQwen4(model) && settings.Backend == BackendPreference.AutoVulkanCpu &&
                !BalancedModelAdvisor.QwenQualified(State, _calibration()))
            {
                var next = Models.First(m => m.Id == BalancedModelAdvisor.GemmaId);
                var reason = "Qwen no cumplió el objetivo automático de Vulkan estable y mediana de hasta 30 s. Se propone Gemma; Qwen sigue disponible en la selección avanzada.";
                await UnloadCoreAsync().ConfigureAwait(false);
                await SaveAdviceAsync(next, settings.Context, reason, technical: true, ct, qwenRejected: true).ConfigureAwait(false);
                var alternativePath = await _services.ModelStore.FindVerifiedAsync(next, ct).ConfigureAwait(false);
                if (alternativePath is null) return new(next, null, reason + " Pulsa Preparar para descargar Gemma.", true);
                StatusChanged?.Invoke(reason);
                if (!BalancedModelAdvisor.Fits(next, Device, settings.Context, true, Hardware.LowMemory))
                    return new(next, null, reason + " No hay margen estimado de RAM ahora; libera memoria o elige un modelo menor.", false);
                State = await LoadCoreAsync(next, alternativePath, settings, ct).ConfigureAwait(false);
                LoadedModel = next; _configurationKey = null;
                return new(next, State, reason + " Se ha preparado la copia local de Gemma.", false);
            }
            LoadedModel = model; _configurationKey = key;
            var message = State.FallbackReason ?? "Modelo preparado.";
            if (settings.AutomaticModel) await SaveAdviceAsync(model, settings.Context, message, technical: State.Backend == "CPU" && Hardware.HasVulkan, ct).ConfigureAwait(false);
            return new(model, State, message, false);
        }
        catch { await UnloadCoreAsync().ConfigureAwait(false); throw; }
        finally { _gate.Release(); }
    }
    private async Task<EngineState> LoadCoreAsync(ModelEntry model, string path, CourseSettings settings, CancellationToken ct)
    {
        EngineStarting?.Invoke();
        if (settings.Backend == BackendPreference.Vulkan && settings.AdapterId is not null)
        {
            var worker = _placementFactory(); _active = worker;
            var inventory = await worker.InspectAsync(path, settings.Context, ct).ConfigureAwait(false);
            var adapter = inventory.Devices.FirstOrDefault(d => d.Id == settings.AdapterId) ?? throw new InvalidOperationException("El adaptador seleccionado ya no está disponible.");
            var layers = settings.GpuLayers ?? adapter.EstimatedLayers;
            if (layers <= 0 || layers > inventory.FullLayers) throw new ArgumentException("El número de capas no pertenece a este modelo.");
            var state = await worker.LoadPlacementAsync(model, path, new(adapter.Index, adapter.Id, layers), settings.Context, ct).ConfigureAwait(false);
            if (state.AdapterId != adapter.Id || state.OffloadedLayers != layers || state.Backend != "Vulkan") throw new InvalidDataException("No se confirmó la distribución manual solicitada.");
            return state with { Requested = BackendPreference.Vulkan, FallbackReason = "Adaptador y capas fijados manualmente; sin sustitución automática." };
        }
        _active = _services.Engine;
        return await _active.LoadAsync(model, path, settings.Backend, settings.Context, ct).ConfigureAwait(false);
    }
    private async Task<PrepareResult> RecoverPreparationAsync(ModelEntry failed, CourseSettings settings, Exception error, CancellationToken ct)
    {
        string[] order = [BalancedModelAdvisor.GemmaId, BalancedModelAdvisor.MiniId, BalancedModelAdvisor.LfmId];
        var index = Array.IndexOf(order, failed.Id);
        var choices = order.Skip(index < 0 ? 0 : index + 1).Select(id => Models.First(m => m.Id == id)).ToArray();
        var current = failed;
        await RetainPreparationFailureAsync(current, settings.Context, error, ct).ConfigureAwait(false);
        foreach (var next in choices)
        {
            await UnloadCoreAsync().ConfigureAwait(false);
            var path = await _services.ModelStore.FindVerifiedAsync(next, ct).ConfigureAwait(false);
            if (!BalancedModelAdvisor.Fits(next, Device, settings.Context, path is not null, Hardware.LowMemory)) continue;
            var message = $"No se pudo preparar {failed.Name}. Se propone {next.Name} para reducir los recursos necesarios.";
            await SaveAdviceAsync(next, settings.Context, message, true, ct, BalancedModelAdvisor.IsQwen4(failed)).ConfigureAwait(false);
            if (path is null) return new(next, null, message + " Pulsa Preparar para autorizar su descarga.", true);
            StatusChanged?.Invoke(message);
            try
            {
                State = await LoadCoreAsync(next, path, settings, ct).ConfigureAwait(false);
                LoadedModel = next; _configurationKey = null;
                return new(next, State, message + " Se ha preparado la copia local.", false);
            }
            catch (Exception e) when (e is not OperationCanceledException)
            { current = next; error = e; await RetainPreparationFailureAsync(current, settings.Context, error, ct).ConfigureAwait(false); }
        }
        await UnloadCoreAsync().ConfigureAwait(false);
        return new(current, null, "No se pudo preparar un modelo dentro del margen actual. Libera memoria o revisa las opciones avanzadas. Tus archivos se conservan.", false);
    }
    private async Task RetainPreparationFailureAsync(ModelEntry model, int context, Exception error, CancellationToken ct)
    {
        var directory = Path.GetDirectoryName(_adviceFile)!; Directory.CreateDirectory(directory);
        var trace = new PreparationFailureTrace(DateTimeOffset.UtcNow, model.Id, model.Sha256, context, error.ToString());
        await File.WriteAllTextAsync(Path.Combine(directory, "preparation-failure-" + Guid.NewGuid().ToString("N") + ".json"),
            JsonSerializer.Serialize(trace, CourseJsonContext.Default.PreparationFailureTrace), ct).ConfigureAwait(false);
    }
    private async Task SaveAdviceAsync(ModelEntry model, int context, string reason, bool technical, CancellationToken ct, bool qwenRejected = false)
    {
        Directory.CreateDirectory(Path.GetDirectoryName(_adviceFile)!);
        var profile = new AutoAdviceProfile(Hardware.Fingerprint, context, model.Id, model.Sha256, reason, DateTimeOffset.UtcNow, technical, qwenRejected);
        var temp = _adviceFile + ".tmp-" + Guid.NewGuid().ToString("N");
        await File.WriteAllTextAsync(temp, JsonSerializer.Serialize(profile, CourseJsonContext.Default.AutoAdviceProfile), ct).ConfigureAwait(false);
        File.Move(temp, _adviceFile, true);
    }
    public async Task<EngineOutput> GenerateAsync(WritingDemo.Core.WritingExercise exercise, string text, int seed, CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try { return await (_active ?? throw new InvalidOperationException("Prepara el modelo antes de evaluar.")).GenerateAsync(exercise, text, seed, ct).ConfigureAwait(false); }
        catch { await UnloadCoreAsync().ConfigureAwait(false); throw; }
        finally { _gate.Release(); }
    }
    public async Task RecalibrateAsync(ModelEntry model, int context, CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            await UnloadCoreAsync().ConfigureAwait(false);
            var directory = Path.GetDirectoryName(_adviceFile)!;
            // Archive, never discard, prior technical evidence. Do not touch benchmark artifacts.
            foreach (var file in Directory.Exists(directory) ? Directory.EnumerateFiles(directory, "*.json") : [])
            {
                ct.ThrowIfCancellationRequested();
                if (Path.GetFileName(file).StartsWith("trace-", StringComparison.Ordinal) || Path.GetFileName(file).StartsWith("preparation-failure-", StringComparison.Ordinal)) continue;
                if (file == _adviceFile) { File.Move(file, file + ".superseded-" + Guid.NewGuid().ToString("N")); continue; }
                try
                {
                    var profile = JsonSerializer.Deserialize(await File.ReadAllTextAsync(file, ct).ConfigureAwait(false), AppJsonContext.Default.AdaptiveProfile);
                    if (profile?.ModelId == model.Id && profile.Context == context) File.Move(file, file + ".superseded-" + Guid.NewGuid().ToString("N"));
                }
                catch (JsonException) { }
            }
        }
        finally { _gate.Release(); }
    }
    private async Task UnloadCoreAsync()
    {
        if (_active is not null)
        {
            if (ReferenceEquals(_active, _services.Engine)) await _active.UnloadAsync().ConfigureAwait(false);
            else await _active.DisposeAsync().ConfigureAwait(false);
        }
        _active = null; State = null; LoadedModel = null; _configurationKey = null;
    }
    public async Task UnloadAsync() { await _gate.WaitAsync().ConfigureAwait(false); try { await UnloadCoreAsync().ConfigureAwait(false); } finally { _gate.Release(); } }
    public async ValueTask DisposeAsync() { await UnloadAsync().ConfigureAwait(false); if (_services.Engine is IRuntimeProgress progress) progress.StatusChanged -= Forward; }
}
