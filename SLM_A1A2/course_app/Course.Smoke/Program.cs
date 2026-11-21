using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.Json.Serialization;
using Course.Core;
using Course.Desktop;
using WritingApp.Native;
using WritingApp.Shared;

if (!args.Contains("--execute"))
{
    Console.WriteLine("Use --execute --adaptive-readiness for Gemma CPU/Vulkan qualification, two course examples and cache reuse; --matrix for 24 examples; --qwen2-readiness for one CPU example. Never reads a benchmark.");
    return 0;
}
var additionalQwen = args.Contains("--qwen2-readiness");
var adaptiveReadiness = args.Contains("--adaptive-readiness");
if (!args.Contains("--matrix") && !additionalQwen && !adaptiveReadiness) throw new ArgumentException("Select a readiness/matrix mode.");
var outputIndex = Array.IndexOf(args, "--output");
var folder = Path.GetFullPath(outputIndex >= 0 ? args[outputIndex + 1] : "artifacts/verification/real-course-" + DateTime.UtcNow.ToString("yyyyMMddTHHmmssZ"));
Directory.CreateDirectory(folder);
var course = new EmbeddedCourse();
var bootstrap = WindowsHost.CreateServices();
IsolatedInferenceEngine? currentWorker = null;
IsolatedInferenceEngine Worker() => currentWorker = new(AppContext.BaseDirectory, Path.Combine(folder, "worker-logs"));
await using var adaptive = new AdaptiveInferenceEngine(_ => Worker(), Path.Combine(folder, "profiles"), "course-verification");
var services = new AppServices(bootstrap.Device, bootstrap.ModelStore, adaptive, new(Path.Combine(folder, "sessions")));
await using var runtime = new CourseRuntime(services, Worker, () => WindowsHost.RefreshDevice(services), WindowsHost.ProbeAsync, Path.Combine(folder, "profiles", "advice.json"));
using var store = new CourseStore(Path.Combine(folder, "verification.db"));
var practice = new WritingPracticeService(store, runtime);
var results = new List<CaseResult>();
foreach (var id in additionalQwen ? new[] { "portable-unsloth-qwen35-2b-q4-k-m" } : adaptiveReadiness ? new[] { BalancedModelAdvisor.GemmaId } : new[] { BalancedModelAdvisor.GemmaId, "11-qwen35-4b-q4-k-m" })
{
    var model = CourseModelCatalog.All.First(m => m.Id == id);
    var file = await services.ModelStore.FindVerifiedAsync(model, CancellationToken.None);
    if (file is null && additionalQwen)
    {
        Console.WriteLine($"Downloading exact additional catalog entry: {model.Label}");
        file = await services.Downloads.EnsureAsync(model, null, CancellationToken.None);
    }
    if (file is null) throw new FileNotFoundException("Matrix verification requires an already downloaded exact model: " + model.Label);
    foreach (var backend in additionalQwen ? new[] { BackendPreference.Cpu } : adaptiveReadiness ? new[] { BackendPreference.AutoVulkanCpu } : new[] { BackendPreference.Cpu, BackendPreference.Vulkan })
    {
        Console.WriteLine($"Preparing {id} / {backend}");
        string? adapterId = null; int? layers = null;
        if (backend == BackendPreference.Vulkan)
        {
            await using var inspector = Worker();
            var inventory = await inspector.InspectAsync(file, 2048, CancellationToken.None);
            var placement = AdaptiveRuntimePolicy.Candidates(inventory).FirstOrDefault() ?? throw new InvalidOperationException("No GPU placement available for " + id);
            adapterId = placement.DeviceId; layers = placement.GpuLayers;
        }
        var prepared = await runtime.PrepareAsync(model, new(id, false, backend, 2048, 1, adapterId, layers), false, null, CancellationToken.None);
        foreach (var activity in course.Course.Units.SelectMany(u => u.Activities).Where(a => a.IsWriting).Take(additionalQwen || adaptiveReadiness ? 1 : 3))
        foreach (var correct in additionalQwen ? new[] { false } : new[] { true, false })
        {
            var example = correct ? activity.CorrectExample! : activity.IncorrectExample!;
            var caseId = $"{id}/{backend}/{activity.Id}/{(correct ? "correct" : "incorrect")}";
            var clock = Stopwatch.StartNew();
            await using var memory = new MemorySampler(() => currentWorker?.WorkerProcessId);
            memory.Start();
            try
            {
                var session = await practice.EvaluateAsync(activity.ToExercise(), example, true, 1, null, CancellationToken.None);
                await memory.StopAsync();
                var last = session.Attempts.Last();
                var path = Path.Combine(folder, $"session-{results.Count + 1:00}.json");
                await File.WriteAllTextAsync(path, SessionStore.Serialize(session));
                results.Add(new(caseId, id, model.Sha256, PortablePrompt.Hash(model), backend.ToString(), prepared.Engine!.Backend,
                    prepared.Engine.OffloadedLayers, prepared.Engine.TotalLayers, correct, session.Usable,
                    session.Usable ? last.Parsed.Value?.IsCorrect : null, last.Parsed.Status, last.Output.FinishReason,
                    last.Output.Seconds, clock.Elapsed.TotalSeconds, memory.PeakRss, memory.LifetimePeakRss, memory.PeakVramMiB,
                    session.Attempts.Length, last.Output.Metrics, null));
                Console.WriteLine($"{caseId}: {last.Parsed.Status}, model says {last.Parsed.Value?.IsCorrect}, {last.Output.Seconds:F2}s, RSS {memory.PeakRss / 1048576d:F0} MiB");
            }
            catch (Exception e)
            {
                await memory.StopAsync();
                results.Add(new(caseId, id, model.Sha256, PortablePrompt.Hash(model), backend.ToString(), prepared.Engine!.Backend,
                    prepared.Engine.OffloadedLayers, prepared.Engine.TotalLayers, correct, false, null, "TECHNICAL_ERROR", "error", 0,
                    clock.Elapsed.TotalSeconds, memory.PeakRss, memory.LifetimePeakRss, memory.PeakVramMiB, 0, null, e.ToString()));
                Console.WriteLine($"FAIL {caseId}: {e.Message}");
                throw; // Do not continue with an engine that has failed, or silently retry.
            }
            finally { await SaveAsync(); }
        }
        await runtime.UnloadAsync();
        if (adaptiveReadiness)
        {
            var profile = adaptive.LastProfile ?? throw new InvalidOperationException("Missing measured profile.");
            var traceCount = Directory.GetFiles(Path.Combine(folder, "profiles"), "trace-*.json").Length;
            var clock = Stopwatch.StartNew();
            await runtime.PrepareAsync(model, new(id, false, backend, 2048), false, null, CancellationToken.None);
            var reused = adaptive.LastProfile?.Key == profile.Key && adaptive.LastProfile?.DateUtc == profile.DateUtc
                && Directory.GetFiles(Path.Combine(folder, "profiles"), "trace-*.json").Length == traceCount;
            await File.WriteAllTextAsync(Path.Combine(folder, "adaptive-profile.json"), JsonSerializer.Serialize(profile, AppJsonContext.Default.AdaptiveProfile));
            using var evidence = File.Create(Path.Combine(folder, "cache-check.json")); using var writer = new Utf8JsonWriter(evidence, new() { Indented = true });
            writer.WriteStartObject(); writer.WriteBoolean("same_key_date_and_trace_count", reused); writer.WriteNumber("prepare_seconds", clock.Elapsed.TotalSeconds); writer.WriteEndObject();
            if (!reused) throw new InvalidOperationException("Unexpected recalibration on unchanged hardware.");
            await runtime.UnloadAsync();
        }
    }
}
await using (var export = File.Create(Path.Combine(folder, "history.json"))) await store.ExportHistoryAsync(export);
services.ModelStore.Dispose();
Console.WriteLine($"{results.Count(r => r.Usable)}/{results.Count} usable. This is app integration evidence, not an accuracy benchmark. {folder}");
return results.Count == (additionalQwen ? 1 : adaptiveReadiness ? 2 : 24) && results.All(r => r.Usable) ? 0 : 1;

async Task SaveAsync()
{
    var hashes = new Dictionary<string, string>();
    foreach (var name in new[] { "writing_worker.exe", "writing_llama_bridge.dll", "ggml-vulkan.dll", "llama.dll", "Course.Core.dll", "WritingApp.Native.dll", "WritingApp.Shared.dll" })
    {
        await using var input = File.OpenRead(Path.Combine(AppContext.BaseDirectory, name)); hashes[name] = Convert.ToHexStringLower(await SHA256.HashDataAsync(input));
    }
    var report = new SmokeReport("COURSE_APPLICATION_INTEGRATION_NOT_BENCHMARK", DateTimeOffset.UtcNow, Environment.MachineName, services.Device,
        course.Course.Version, course.Course.SourceSha256, hashes, "Worker RSS sampled every 100 ms; lifetime peak includes load. NVIDIA VRAM is device-wide, maximum reported adapter use, sampled every second; not attributed to this process. Null when unavailable.", results.ToArray());
    var temp = Path.Combine(folder, "report.json.tmp");
    await File.WriteAllTextAsync(temp, JsonSerializer.Serialize(report, SmokeJson.Default.SmokeReport));
    File.Move(temp, Path.Combine(folder, "report.json"), true);
}

internal sealed record CaseResult(string Id, string ModelId, string ModelSha256, string PromptSha256, string RequestedBackend,
    string ActualBackend, int GpuLayers, int? TotalLayers, bool ExampleCorrect, bool Usable, bool? ModelSaysCorrect,
    string ParserStatus, string FinishReason, double GenerationSeconds, double WallSeconds, long WorkerPeakRssBytes,
    long WorkerLifetimePeakRssBytes, long? DeviceWidePeakVramMiB, int Attempts, InferenceMetrics? Metrics, string? Error);
internal sealed record SmokeReport(string Purpose, DateTimeOffset DateUtc, string Host, DeviceProfile Device,
    string CourseVersion, string ProposalSha256, Dictionary<string, string> RuntimeHashes, string MeasurementLimits, CaseResult[] Cases);
[JsonSourceGenerationOptions(WriteIndented = true, UseStringEnumConverter = true)]
[JsonSerializable(typeof(SmokeReport))]
internal partial class SmokeJson : JsonSerializerContext;

internal sealed class MemorySampler(Func<int?> processId) : IAsyncDisposable
{
    private readonly CancellationTokenSource _stop = new();
    private Task? _sampling;
    public long PeakRss { get; private set; }
    public long LifetimePeakRss { get; private set; }
    public long? PeakVramMiB { get; private set; }
    public void Start() => _sampling = Task.Run(async () =>
    {
        int sample = 0;
        while (!_stop.IsCancellationRequested)
        {
            try
            {
                if (processId() is { } pid)
                { using var process = Process.GetProcessById(pid); process.Refresh(); PeakRss = Math.Max(PeakRss, process.WorkingSet64); LifetimePeakRss = Math.Max(LifetimePeakRss, process.PeakWorkingSet64); }
                if (sample++ % 10 == 0)
                {
                    using var gpu = Process.Start(new ProcessStartInfo("nvidia-smi", "--query-gpu=memory.used --format=csv,noheader,nounits") { UseShellExecute = false, CreateNoWindow = true, RedirectStandardOutput = true, RedirectStandardError = true });
                    if (gpu is not null)
                    {
                        var values = await gpu.StandardOutput.ReadToEndAsync(_stop.Token);
                        await gpu.WaitForExitAsync(_stop.Token);
                        foreach (var value in values.Split('\n')) if (long.TryParse(value.Trim(), out var mib)) PeakVramMiB = Math.Max(PeakVramMiB ?? 0, mib);
                    }
                }
            }
            catch (Exception e) when (e is System.ComponentModel.Win32Exception or InvalidOperationException or ArgumentException) { }
            await Task.Delay(100, _stop.Token);
        }
    });
    public async Task StopAsync() { _stop.Cancel(); if (_sampling is not null) try { await _sampling; } catch (OperationCanceledException) { } }
    public async ValueTask DisposeAsync() { await StopAsync(); _stop.Dispose(); }
}
