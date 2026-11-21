using System.Security.Cryptography;
using System.Text.Json;
using Course.Core;
using WritingApp.Shared;

namespace Course.Tests;

internal static class MemoryPlanningTests
{
    public static IEnumerable<(string Id, Func<Task> Check)> Cases => new (string, Func<Task>)[]
    {
        ("M09-android-capacity-and-current-headroom-are-separate", Capacity),
        ("M10-android-context-and-pressure-reduce-the-proposal", Pressure),
        ("M11-smaller-phones-keep-minicpm-and-lfm-fallbacks", SmallerPhones),
        ("M12-download-staging-space-is-reserved-without-penalizing-local-files", Storage),
        ("M13-automatic-load-failure-retains-evidence-and-prepares-local-smaller-model", AutomaticRecovery),
        ("M14-missing-fallback-requires-an-explicit-download-action", NoImplicitDownload),
        ("M15-manual-choice-does-not-switch-model-on-failure", ManualFailure),
        ("M16-cancelled-automatic-preparation-does-not-load-another-model", Cancelled),
        ("M17-automatic-fallback-is-bounded-and-keeps-all-model-files", AllFail)
    };
    private static ModelEntry Gemma => CourseModelCatalog.All.First(m => m.Id == BalancedModelAdvisor.GemmaId);
    private static DeviceProfile Phone => new("Android", "arm64-v8a", 7886557184, 2117615616, 12L << 30);
    private static void Check(bool value, string message) { if (!value) throw new Exception(message); }
    private static Task Capacity()
    {
        var plan = ModelMemoryPlanner.Plan(Gemma, Phone, 2048, true);
        Check(plan.Fits && plan.UsesMappedWeights, "8 GiB class capacity must not be ruled out by a 45% cap");
        Check(plan.WorkingSetBytes > 4L << 30 && plan.RequiredAvailableBytes > 1800L << 20, "do not make the model magically smaller to fit");
        Check(plan.SystemReserveBytes >= 1280L << 20, "system headroom retained");
        var advice = new BalancedModelAdvisor().Recommend(CourseModelCatalog.All, Phone, new(true, "GPU", "generic"), new(), _ => true);
        Check(advice.Model.Id == Gemma.Id && advice.FitsEstimate && advice.Reason.Contains("ajustado"), "conditional memory margin must be explained");
        var desktop = ModelMemoryPlanner.Plan(Gemma, Phone with { Platform = "Windows" }, 2048, true);
        Check(!desktop.Fits && !desktop.UsesMappedWeights, "Android reclaim allowance must not silently relax desktop free-RAM checks");
        return Task.CompletedTask;
    }
    private static Task Pressure()
    {
        var at19 = Phone with { AvailableMemoryBytes = (long)(1.9 * (1L << 30)) };
        Check(ModelMemoryPlanner.Plan(Gemma, at19, 2048, true).Fits && !ModelMemoryPlanner.Plan(Gemma, at19, 4096, true).Fits, "context changes immediate buffer headroom");
        Check(!ModelMemoryPlanner.Plan(Gemma, Phone, 2048, true, lowMemory: true).Fits, "honor OS low-memory flag");
        Check(!ModelMemoryPlanner.Plan(Gemma, Phone with { AvailableMemoryBytes = 0 }, 2048, true).Fits, "unknown/zero free memory must not be invented");
        var manual = new BalancedModelAdvisor().Recommend(CourseModelCatalog.All, Phone with { AvailableMemoryBytes = 100 }, new(true, "GPU", "host", true), new(Gemma.Id, false), _ => true);
        Check(manual.Model.Id == Gemma.Id && !manual.FitsEstimate, "advanced override remains explicit");
        return Task.CompletedTask;
    }
    private static Task SmallerPhones()
    {
        var advisor = new BalancedModelAdvisor(); var hw = new HardwareCapabilities(false, "CPU", "generic");
        var six = Phone with { TotalMemoryBytes = (long)(5.5 * (1L << 30)), AvailableMemoryBytes = 2L << 30 };
        Check(advisor.Recommend(CourseModelCatalog.All, six, hw, new(), _ => true).Model.Id == BalancedModelAdvisor.MiniId, "6 GiB class should retain smaller fallback");
        var four = Phone with { TotalMemoryBytes = (long)(3.5 * (1L << 30)), AvailableMemoryBytes = (long)(1.5 * (1L << 30)) };
        Check(advisor.Recommend(CourseModelCatalog.All, four, hw, new(), _ => true).Model.Id == BalancedModelAdvisor.LfmId, "4 GiB class should retain extreme fallback");
        Check(!advisor.Recommend(CourseModelCatalog.All, four with { AvailableMemoryBytes = 100 }, hw, new(), _ => true).FitsEstimate, "do not promise a fit under critical pressure");
        return Task.CompletedTask;
    }
    private static Task Storage()
    {
        var disk = Phone with { FreeStorageBytes = Gemma.SizeBytes + (512L << 20) };
        Check(!ModelMemoryPlanner.Plan(Gemma, disk, 2048, false).Fits, "Android publication needs staging plus permanent copy");
        Check(ModelMemoryPlanner.Plan(Gemma, disk, 2048, true).Fits, "a local pinned model needs no second download-sized reservation");
        return Task.CompletedTask;
    }
    private sealed class RecoveryFixture : IAsyncDisposable
    {
        public Fixture Data { get; } = new();
        public CourseRuntime Runtime { get; }
        public ModelEntry[] Models { get; }
        public RecoveryFixture(bool miniPresent = true)
        {
            string[] ids = [BalancedModelAdvisor.GemmaId, BalancedModelAdvisor.MiniId, BalancedModelAdvisor.LfmId];
            var bytes = "GGUFsynthetic-recovery-fixture"u8.ToArray();
            Models = ids.Select((id, i) => CourseModelCatalog.All.First(m => m.Id == id) with
                { RelativePath = $"fallback-{i}.gguf", SizeBytes = bytes.Length, Sha256 = Convert.ToHexStringLower(SHA256.HashData(bytes)) }).ToArray();
            for (var i = 0; i < Models.Length; i++) if (miniPresent || i != 1) File.WriteAllBytes(Path.Combine(Data.Root, Models[i].RelativePath), bytes);
            Data.Engine.FailLoadIds.Add(Models[0].Id);
            Runtime = new(Data.Services, () => Data.Engine, () => Data.Services.Device,
                _ => Task.FromResult(new HardwareCapabilities(false, "CPU", "host")), Path.Combine(Data.Root, "recovery", "advice.json"), models: Models);
        }
        public Task<PrepareResult> Prepare(bool automatic = true, CancellationToken ct = default) => Runtime.PrepareAsync(Models[0], new(Models[0].Id, automatic, BackendPreference.Cpu), false, null, ct);
        public async ValueTask DisposeAsync() { await Runtime.DisposeAsync(); await Data.DisposeAsync(); }
    }
    private static async Task AutomaticRecovery()
    {
        await using var f = new RecoveryFixture(); var result = await f.Prepare();
        Check(result.Model.Id == BalancedModelAdvisor.MiniId && result.Engine?.Backend == "CPU", "prepare the local alternative after failed allocation");
        Check(f.Data.Engine.LoadedIds.SequenceEqual(f.Models.Take(2).Select(m => m.Id)), "one attempt per model");
        var trace = Directory.GetFiles(Path.Combine(f.Data.Root, "recovery"), "preparation-failure-*.json").Single();
        var data = JsonSerializer.Deserialize(await File.ReadAllTextAsync(trace), CourseJsonContext.Default.PreparationFailureTrace)!;
        Check(data.ModelId == Gemma.Id && data.Error.Contains("Synthetic"), "retain original failure evidence");
    }
    private static async Task NoImplicitDownload()
    {
        await using var f = new RecoveryFixture(miniPresent: false); var result = await f.Prepare();
        Check(result.NeedsDownload && result.Model.Id == BalancedModelAdvisor.MiniId && result.Engine is null, "ask through the existing Prepare button, not an automatic HTTP request");
        Check(f.Data.Engine.Loads == 1, "do not load a missing fallback or skip its reviewable download step");
    }
    private static async Task ManualFailure()
    {
        await using var f = new RecoveryFixture();
        try { await f.Prepare(automatic: false); throw new Exception("manual failure hidden"); } catch (IOException) { }
        Check(f.Data.Engine.Loads == 1 && f.Runtime.LoadedModel is null, "manual model must not change silently");
    }
    private static async Task Cancelled()
    {
        await using var f = new RecoveryFixture(); f.Data.Engine.FailLoadIds.Clear();
        var gate = new TaskCompletionSource(); f.Data.Engine.LoadGate = gate.Task; using var cts = new CancellationTokenSource();
        var preparing = f.Prepare(ct: cts.Token); cts.Cancel();
        try { await preparing; throw new Exception("cancellation hidden"); } catch (OperationCanceledException) { }
        finally { gate.TrySetResult(); }
        Check(f.Data.Engine.Loads <= 1 && f.Runtime.LoadedModel is null, "cancellation must never choose a different model");
    }
    private static async Task AllFail()
    {
        await using var f = new RecoveryFixture(); foreach (var m in f.Models) f.Data.Engine.FailLoadIds.Add(m.Id);
        var result = await f.Prepare();
        Check(result.Engine is null && f.Data.Engine.Loads == 3 && Directory.GetFiles(Path.Combine(f.Data.Root, "recovery"), "preparation-failure-*.json").Length == 3, "bounded three-model recovery with one trace per failure");
        Check(f.Models.All(m => File.Exists(Path.Combine(f.Data.Root, m.RelativePath))), "failed loading must preserve every GGUF");
    }
}
