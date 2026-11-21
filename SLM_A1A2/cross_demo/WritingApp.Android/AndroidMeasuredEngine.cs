using Android.OS;
using WritingApp.Shared;
using WritingDemo.Core;

namespace WritingApp.Android;

internal sealed class AndroidMeasuredEngine : IInferenceEngine, IRuntimeProgress
{
    private const string DriverVersion = "termux-mesa26.2.7-loader1.4.368-v1";
    private readonly string nativeDirectory;
    private readonly string root;
    private readonly PowerManager power;
    private readonly AdaptiveInferenceEngine _adaptive;
    private readonly SemaphoreSlim _gate = new(1,1);
    private bool _candidateTurnip;
    internal string DriverDirectory => Path.Combine(root,DriverVersion);
    internal AdaptiveProfile? LastCalibration => _adaptive.LastProfile;
    public event Action<string>? StatusChanged
    {
        add => _adaptive.StatusChanged += value;
        remove => _adaptive.StatusChanged -= value;
    }
    internal AndroidMeasuredEngine(string nativeDirectory,string root,PowerManager power)
    {
        this.nativeDirectory=nativeDirectory;this.root=root;this.power=power;
        _adaptive=new(vulkan=>new AndroidWorkerEngine(nativeDirectory,DriverDirectory,Path.Combine(root,"driver-cache"),vulkan&&_candidateTurnip),
            Path.Combine(root,"adaptive-profiles"), () =>
            {
                using var battery=global::Android.App.Application.Context.RegisterReceiver(null,
                    new global::Android.Content.IntentFilter(global::Android.Content.Intent.ActionBatteryChanged));
                return $"{Build.Fingerprint}|{DriverVersion}|saver={power.IsPowerSaveMode}|plugged={battery?.GetIntExtra("plugged",-1)}";
            }, CalibrationAllowed);
    }
    private bool CalibrationAllowed()
    {
        if (!power.IsInteractive) return false;
        using var state = new global::Android.App.ActivityManager.RunningAppProcessInfo();
        global::Android.App.ActivityManager.GetMyMemoryState(state);
        return (int)state.Importance == 100; // Android IMPORTANCE_FOREGROUND, not foreground-service importance.
    }
    internal async Task PrepareDriverAsync(CancellationToken ct)
    {
        var marker = Path.Combine(DriverDirectory, "freedreno_icd.json");
        if (File.Exists(marker)) return;
        Directory.CreateDirectory(DriverDirectory);
        await using var asset = global::Android.App.Application.Context.Assets!.Open("turnip-runtime.zip");
        using var zip = new System.IO.Compression.ZipArchive(asset, System.IO.Compression.ZipArchiveMode.Read);
        // The driver is bundled with the signed APK. Extract only flat library names.
        foreach (var entry in zip.Entries)
        {
            if (entry.Name != entry.FullName || entry.Name.Length == 0)
                throw new InvalidDataException("Unexpected packaged driver path.");
            await using var source = entry.Open();
            await using var target = new FileStream(Path.Combine(DriverDirectory, entry.Name), FileMode.Create, FileAccess.Write);
            await source.CopyToAsync(target, ct).ConfigureAwait(false);
        }
        var manifest = "{\"ICD\":{\"api_version\":\"1.3.0\",\"library_path\":\"./libvulkan_freedreno.so\"},\"file_format_version\":\"1.0.0\"}";
        await File.WriteAllTextAsync(marker, manifest, ct).ConfigureAwait(false);
    }


    public async Task<EngineState> LoadAsync(ModelEntry model,string path,BackendPreference backend,int context,CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        using var wake=power.NewWakeLock(WakeLockFlags.Partial,"WritingLab:Calibration");
        wake?.Acquire(1_800_000);
        try
        {
            _candidateTurnip=File.Exists("/dev/kgsl-3d0");
            if(backend!=BackendPreference.Cpu && _candidateTurnip)
            {
                try {await PrepareDriverAsync(ct).ConfigureAwait(false);}
                catch(Exception e) when(e is not System.OperationCanceledException && backend==BackendPreference.AutoVulkanCpu)
                {
                    var cpu=await _adaptive.LoadAsync(model,path,BackendPreference.Cpu,context,ct).ConfigureAwait(false);
                    return cpu with {Requested=backend,FallbackReason="CPU: no se pudo preparar el controlador. "+e.Message};
                }
            }
            return await _adaptive.LoadAsync(model,path,backend,context,ct).ConfigureAwait(false);
        }
        finally {if(wake?.IsHeld==true)wake.Release();_gate.Release();}
    }
    public async Task<EngineOutput> GenerateAsync(WritingExercise exercise,string text,int seed,CancellationToken ct)
    {
        await _gate.WaitAsync(ct).ConfigureAwait(false);
        using var wake=power.NewWakeLock(WakeLockFlags.Partial,"WritingLab:Inference");
        wake?.Acquire(300_000);
        try {return await _adaptive.GenerateAsync(exercise,text,seed,ct).ConfigureAwait(false);}
        finally {if(wake?.IsHeld==true)wake.Release();_gate.Release();}
    }
    public async Task UnloadAsync()
    {
        await _gate.WaitAsync().ConfigureAwait(false);
        try {await _adaptive.UnloadAsync().ConfigureAwait(false);}
        finally {_gate.Release();}
    }
    public async ValueTask DisposeAsync()=>await UnloadAsync().ConfigureAwait(false);
}
