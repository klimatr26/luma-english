using Android.App;
using Android.Content;
using Android.OS;
using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using Course.Core;
using WritingApp.Android;
using WritingApp.Native;
using WritingApp.Shared;
using WritingDemo.Core;

namespace Luma.AndroidApp;

internal sealed class AndroidPlatform
{
    private readonly Context _context;
    private readonly string _root, _native;
    private readonly PowerManager _power;
    private readonly AndroidMeasuredEngine? _measured;
    private readonly Lazy<Task<string>> _nativeHash;
    public AppServices Services { get; }
    public BackgroundModelDownloads Downloads { get; }
    public CourseRuntime Runtime { get; }
    internal AdaptiveProfile? LastCalibration => _measured?.LastCalibration;
    internal AndroidPlatform(Context context)
    {
        _context = context; _root = context.FilesDir!.AbsolutePath;
        _native = context.ApplicationInfo!.NativeLibraryDir!;
        _power = (PowerManager)context.GetSystemService(Context.PowerService)!;
        _nativeHash = new(() => Task.Run(async () =>
        {
            using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            foreach (var file in Directory.EnumerateFiles(_native, "*.so").Order(StringComparer.Ordinal))
            { await using var input = File.OpenRead(file); hash.AppendData(await SHA256.HashDataAsync(input)); }
            return Convert.ToHexStringLower(hash.GetHashAndReset());
        }));
        var models = new ModelStore(Path.Combine(_root, "models"));
        Downloads = new(models, new AndroidDownloadTransport(context, CourseModelCatalog.All, "Luma English"), CourseModelCatalog.All);
        IInferenceEngine engine;
        if (Build.VERSION.SdkInt >= BuildVersionCodes.P)
            engine = _measured = new(_native, _root, _power);
        else engine = new NativeInferenceEngine(_native);
        Services = new(Device(), models, engine, new SessionStore(Path.Combine(_root, "sessions")), Downloads);
        Runtime = new(Services, Worker, Device, ProbeAsync, Path.Combine(_root, "adaptive-profiles", "course-auto-advice.json"),
            () => _measured?.LastCalibration);
    }
    internal DeviceProfile Device()
    {
        using var memory = new ActivityManager.MemoryInfo();
        ((ActivityManager)_context.GetSystemService(Context.ActivityService)!).GetMemoryInfo(memory);
        using var disk = new StatFs(_root);
        var emulator = (Build.Hardware ?? "").Contains("ranchu") || (Build.Fingerprint ?? "").Contains("generic")
            || (Build.Product ?? "").Contains("sdk");
        return new("Android", Build.SupportedAbis?.FirstOrDefault() ?? RuntimeInformation.ProcessArchitecture.ToString(),
            memory.TotalMem, memory.AvailMem, disk.AvailableBytes, emulator, null);
    }
    internal async Task<HardwareCapabilities> ProbeAsync(CancellationToken ct)
    {
        using var memory = new ActivityManager.MemoryInfo();
        ((ActivityManager)_context.GetSystemService(Context.ActivityService)!).GetMemoryInfo(memory);
        using var battery = _context.RegisterReceiver(null, new IntentFilter(Intent.ActionBatteryChanged));
        var catalog = string.Join('|', CourseModelCatalog.All.Select(m => $"{m.Id}/{m.Sha256}/{PortablePrompt.Hash(m)}/{JsonSerializer.Serialize(m.Sampling, AppJsonContext.Default.SamplingOptions)}"));
        var host = $"{BalancedModelAdvisor.Version}|{Build.Fingerprint}|{_power.IsPowerSaveMode}|{battery?.GetIntExtra("plugged", -1)}|{await _nativeHash.Value.ConfigureAwait(false)}|{catalog}";
        if (!File.Exists(Path.Combine(_native, "libggml-vulkan.so")))
            return new(false, "Este paquete usa inferencia en CPU; no incluye un backend Vulkan para esta arquitectura.",
                BalancedModelAdvisor.ProfileKey(host + "|cpu-package"), memory.LowMemory);
        try
        {
            await using var worker = CreateWorker();
            await EnsureDriverAsync(ct).ConfigureAwait(false);
            var driver = await worker.DriverAsync(ct).ConfigureAwait(false);
            return new(true, "Vulkan detectado. La calibración compara CPU, GPU y carga parcial antes de elegir.",
                BalancedModelAdvisor.ProfileKey(host + "|" + driver), memory.LowMemory);
        }
        catch (Exception e) when (e is not System.OperationCanceledException)
        { return new(false, "CPU disponible. Vulkan no se confirmó: " + e.Message, BalancedModelAdvisor.ProfileKey(host + "|no-vulkan"), memory.LowMemory); }
    }
    private bool UseTurnip => File.Exists("/dev/kgsl-3d0") && RuntimeInformation.ProcessArchitecture == Architecture.Arm64;
    private Task EnsureDriverAsync(CancellationToken ct) => UseTurnip && _measured is not null ? _measured.PrepareDriverAsync(ct) : Task.CompletedTask;
    private AndroidWorkerEngine CreateWorker() => new(_native, _measured?.DriverDirectory ?? "", Path.Combine(_root, "driver-cache"), UseTurnip);
    private IPlacementEngine Worker() => new AwakePlacement(CreateWorker(), EnsureDriverAsync, _power);

    private sealed class AwakePlacement(AndroidWorkerEngine inner, Func<CancellationToken, Task> ensure, PowerManager power) : IPlacementEngine
    {
        public TimeSpan GenerationTimeout { get => inner.GenerationTimeout; set => inner.GenerationTimeout = value; }
        private async Task<T> Run<T>(Func<Task<T>> work)
        {
            using var wake = power.NewWakeLock(WakeLockFlags.Partial, "LumaEnglish:Runtime"); wake?.Acquire(1_800_000);
            try { return await work().ConfigureAwait(false); }
            finally { if (wake?.IsHeld == true) wake.Release(); }
        }
        public Task<RuntimeInventory> InspectAsync(string path, int context, CancellationToken ct) => Run(async () =>
        { await ensure(ct).ConfigureAwait(false); return await inner.InspectAsync(path, context, ct).ConfigureAwait(false); });
        public Task<EngineState> LoadPlacementAsync(ModelEntry model, string path, RuntimePlacement placement, int context, CancellationToken ct) => Run(async () =>
        { if (placement.GpuLayers > 0) await ensure(ct).ConfigureAwait(false); return await inner.LoadPlacementAsync(model, path, placement, context, ct).ConfigureAwait(false); });
        public Task<EngineState> LoadAsync(ModelEntry model, string path, BackendPreference backend, int context, CancellationToken ct) => Run(async () =>
        { if (backend != BackendPreference.Cpu) await ensure(ct).ConfigureAwait(false); return await inner.LoadAsync(model, path, backend, context, ct).ConfigureAwait(false); });
        public Task<EngineOutput> GenerateAsync(WritingExercise exercise, string text, int seed, CancellationToken ct) => Run(() => inner.GenerateAsync(exercise, text, seed, ct));
        public Task UnloadAsync() => inner.UnloadAsync();
        public ValueTask DisposeAsync() => inner.DisposeAsync();
    }
}
