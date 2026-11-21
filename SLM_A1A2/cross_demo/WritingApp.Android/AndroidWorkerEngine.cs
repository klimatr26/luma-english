using System.Text.Json;
using WritingApp.Native;
using WritingApp.Shared;
using WritingDemo.Core;

namespace WritingApp.Android;

internal sealed class AndroidWorkerEngine : IPlacementEngine
{
    private readonly IsolatedInferenceEngine _inner;
    private readonly bool _turnip;
    internal AndroidWorkerEngine(string nativeDirectory, string driverDirectory, string cacheDirectory, bool turnip)
    {
        _turnip = turnip;
        Directory.CreateDirectory(cacheDirectory);
        var environment = new Dictionary<string,string>
        {
            ["LD_LIBRARY_PATH"] = turnip ? driverDirectory + ":" + nativeDirectory : nativeDirectory,
        };
        if (turnip)
        {
            environment["VK_DRIVER_FILES"] = Path.Combine(driverDirectory, "freedreno_icd.json");
            environment["MESA_SHADER_CACHE_DIR"] = cacheDirectory;
            environment["XDG_CACHE_HOME"] = cacheDirectory;
            environment["XDG_RUNTIME_DIR"] = cacheDirectory;
        }
        _inner = new(nativeDirectory, Path.Combine(cacheDirectory, "logs"), environment);
    }
    public TimeSpan GenerationTimeout { get => _inner.GenerationTimeout; set => _inner.GenerationTimeout = value; }
    internal async Task<string> DriverAsync(CancellationToken ct)
    {
        using var json = JsonDocument.Parse(await _inner.DriverAsync(ct).ConfigureAwait(false));
        var d = json.RootElement;
        if (_turnip && d.GetProperty("driver_id").GetInt32() != 18)
            throw new InvalidOperationException("La sonda no confirmó Mesa Turnip.");
        return d.GetProperty("fingerprint").GetString()!;
    }
    public async Task<RuntimeInventory> InspectAsync(string modelPath, int context, CancellationToken ct)
    {
        if (_turnip) await DriverAsync(ct).ConfigureAwait(false);
        return await _inner.InspectAsync(modelPath, context, ct).ConfigureAwait(false);
    }
    public Task<EngineState> LoadPlacementAsync(ModelEntry model,string path,RuntimePlacement placement,int context,CancellationToken ct)
        => _inner.LoadPlacementAsync(model,path,placement,context,ct);
    public Task<EngineState> LoadAsync(ModelEntry model,string path,BackendPreference backend,int context,CancellationToken ct)
        => _inner.LoadAsync(model,path,backend,context,ct);
    public Task<EngineOutput> GenerateAsync(WritingExercise exercise,string text,int seed,CancellationToken ct)
        => _inner.GenerateAsync(exercise,text,seed,ct);
    public Task UnloadAsync() => _inner.UnloadAsync();
    public ValueTask DisposeAsync() => _inner.DisposeAsync();
}
