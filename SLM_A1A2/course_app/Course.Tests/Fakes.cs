using System.Security.Cryptography;
using Course.Core;
using WritingApp.Shared;
using WritingDemo.Core;

namespace Course.Tests;

public sealed class FakeEngine : IPlacementEngine
{
    public const string CorrectRaw = "{\"is_correct\":true,\"corrected_text\":\"I am a student.\",\"errors\":[],\"feedback\":\"Nice work!\"}";
    public const string IncorrectRaw = "{\"is_correct\":false,\"corrected_text\":\"I am a student.\",\"errors\":[{\"original\":\"are\",\"correction\":\"am\",\"type\":\"grammar\",\"explanation\":\"Use am with I.\"}],\"feedback\":\"Nice try!\"}";
    public int Generations { get; private set; }
    public int Loads { get; private set; }
    public int[] Seeds => _seeds.ToArray();
    private readonly List<int> _seeds = [];
    public Queue<string> Outputs { get; } = new([CorrectRaw]);
    public int FailOnGeneration { get; set; } = -1;
    public bool CancelGeneration { get; set; }
    public bool FailLoad { get; set; }
    public HashSet<string> FailLoadIds { get; } = [];
    public List<string> LoadedIds { get; } = [];
    public Task? LoadGate { get; set; }
    public Task? GenerationGate { get; set; }
    public WritingExercise? ExerciseReceived { get; private set; }
    public string? TextReceived { get; private set; }
    public RuntimePlacement? Placement { get; private set; }
    public TimeSpan GenerationTimeout { get; set; }
    public async Task<EngineState> LoadAsync(ModelEntry model, string path, BackendPreference backend, int context, CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested(); Loads++; LoadedIds.Add(model.Id);
        if (FailLoad || FailLoadIds.Contains(model.Id)) throw new IOException("Synthetic allocation/load failure");
        if (LoadGate is not null) await LoadGate.WaitAsync(ct);
        return new EngineState(backend, backend == BackendPreference.Cpu ? "CPU" : "Vulkan", "synthetic", backend == BackendPreference.Cpu ? 0 : 14, null, context, TotalLayers: 33, AdapterId: "gpu-1");
    }
    public Task<EngineState> LoadPlacementAsync(ModelEntry model, string path, RuntimePlacement placement, int context, CancellationToken ct)
    { Placement = placement; return LoadAsync(model, path, placement.GpuLayers == 0 ? BackendPreference.Cpu : BackendPreference.Vulkan, context, ct).ContinueWith(t => t.GetAwaiter().GetResult() with { OffloadedLayers = placement.GpuLayers }, ct); }
    public Task<RuntimeInventory> InspectAsync(string path, int context, CancellationToken ct) => Task.FromResult(new RuntimeInventory("test", "driver", 33,
        [new(0, "gpu-1", "Synthetic GPU", 4L << 30, 4L << 30, 14, 33, 1500L << 20, 256L << 20, null)]));
    public async Task<EngineOutput> GenerateAsync(WritingExercise exercise, string studentText, int seed, CancellationToken ct)
    {
        Generations++; _seeds.Add(seed); ExerciseReceived = exercise; TextReceived = studentText;
        if (CancelGeneration) throw new OperationCanceledException(ct);
        if (Generations == FailOnGeneration) throw new IOException("Synthetic Vulkan failure");
        if (GenerationGate is not null) await GenerationGate.WaitAsync(ct);
        return new EngineOutput(Outputs.Count > 0 ? Outputs.Dequeue() : CorrectRaw, "stop", 0.5, "synthetic", new(100, 40, 40, .1, .4, false));
    }
    public Task UnloadAsync() => Task.CompletedTask;
    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}
public sealed class Fixture : IAsyncDisposable
{
    public string Root { get; } = Path.Combine(Path.GetTempPath(), "writing-course-test-" + Guid.NewGuid().ToString("N"));
    public FakeEngine Engine { get; } = new();
    public ModelStore Models { get; }
    public CourseStore Store { get; }
    public CourseRuntime Runtime { get; }
    public AppServices Services { get; }
    public ModelEntry Model { get; }
    public Fixture()
    {
        Directory.CreateDirectory(Root);
        var bytes = "GGUFsynthetic-fixture-not-an-inference-model"u8.ToArray();
        File.WriteAllBytes(Path.Combine(Root, "fixture.gguf"), bytes);
        var template = PortableCatalog.All.First(m => m.Id == BalancedModelAdvisor.GemmaId);
        Model = template with { Id = "fixture", RelativePath = "fixture.gguf", SizeBytes = bytes.Length, Sha256 = Convert.ToHexStringLower(SHA256.HashData(bytes)), DownloadUrl = null };
        Models = new(Root);
        Store = new(Path.Combine(Root, "course.db"));
        Services = new(new("Windows", "X64", 64L << 30, 48L << 30, 100L << 30), Models, Engine, new(Path.Combine(Root, "sessions")));
        Runtime = new(Services, () => Engine, () => Services.Device, _ => Task.FromResult(new HardwareCapabilities(false, "synthetic", "test")), Path.Combine(Root, "profiles", "advice.json"));
    }
    public Task PrepareAsync() => Runtime.PrepareAsync(Model, new(Model.Id, false, BackendPreference.Cpu), false, null, CancellationToken.None);
    public async ValueTask DisposeAsync()
    {
        await Runtime.DisposeAsync(); Store.Dispose(); Models.Dispose();
        if (Path.GetFullPath(Root).StartsWith(Path.GetTempPath(), StringComparison.OrdinalIgnoreCase)) Directory.Delete(Root, true);
    }
}
