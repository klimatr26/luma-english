using System.Security.Cryptography;
using System.Text.Json;
using WritingDemo.Core;

if (!args.Contains("--execute", StringComparer.Ordinal))
{
    Console.WriteLine("Technical demonstration only, outside all benchmarks. Requires --execute --backend Vulkan|Cpu|AutoVulkanCpu|ExistingCuda --models ID[,ID] [--output FILE]. One NEW exercise generation per model; --load-only checks startup without generation.");
    return 0;
}
string Option(string name, string fallback)
{
    var index = Array.IndexOf(args, name);
    return index >= 0 && index+1 < args.Length ? args[index+1] : fallback;
}
var preference = Enum.Parse<RuntimePreference>(Option("--backend", "AutoVulkanCpu"), ignoreCase: true);
var ids = Option("--models", "09-lfm25-12b-q4-k-m").Split(',', StringSplitOptions.RemoveEmptyEntries);
var paths = DemoPaths.Locate();
var models = ModelCatalog.Load(paths);
if (ids.Length == 0 || ids.Distinct(StringComparer.Ordinal).Count() != ids.Length
    || ids.Any(id => models.Count(m => m.Id == id) != 1))
    throw new ArgumentException("Model IDs must exist and occur exactly once.");
var output = Path.GetFullPath(Option("--output", Path.Combine(paths.SessionDirectory, $"backend-smoke-{preference}-{DateTime.UtcNow:yyyyMMddTHHmmssfffZ}.json")));
if (File.Exists(output)) throw new IOException("Refusing to overwrite previous backend evidence.");
Directory.CreateDirectory(Path.GetDirectoryName(output)!);
var evidence = new List<object>();
using var cancellation = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cancellation.Cancel(); };
await using var runtime = new LlamaRuntime(paths);
runtime.HideVulkanDevicesForDiagnostics = args.Contains("--hide-vulkan-devices", StringComparer.Ordinal);
using var assets = new ModelAssets(paths);
var exercise = ExerciseCatalog.All[0];
var overallSuccess = true;
foreach (var id in ids)
{
    var model = models.Single(m => m.Id == id);
    var modelPath = assets.ResolvePath(model, paths.DefaultModelDirectory);
    Console.WriteLine($"LOAD {preference} {id}");
    try
    {
        // LoadAsync verifies the model hash itself; do not hash every weight twice.
        await runtime.LoadAsync(model, modelPath, paths.DefaultServerPath, cancellation.Token, preference);
        var actual = runtime.ActiveBackend ?? throw new InvalidDataException("Missing actual backend report.");
        Console.WriteLine($"BACKEND requested={actual.Requested} actual={actual.ActualBackend} device={actual.Device} layers={actual.OffloadedLayers} fallback={actual.FallbackReason}");
        if (args.Contains("--load-only", StringComparer.Ordinal))
        {
            evidence.Add(new { purpose = "TECHNICAL_BACKEND_LOAD_ONLY_NOT_BENCHMARK", model_id = id, model.ExpectedSha256,
                requested = actual.Requested.ToString(), actual.ActualBackend, actual.Device, actual.FallbackReason,
                actual.OffloadedLayers, simulated_vulkan_devices_hidden = runtime.HideVulkanDevicesForDiagnostics,
                actual.RuntimeBuild, actual.RuntimeCommit, actual.ServerPath,
                chat_generation_performed = false, standard_model_warmup_may_execute = true,
                date_utc = DateTimeOffset.UtcNow, technical_success = true });
        }
        else
        {
            var result = await runtime.GenerateAsync(exercise, exercise.IncorrectExample, cancellation.Token, "benchmark-base");
            var parsed = FeedbackParser.Parse(result.Content, exercise.IncorrectExample);
            evidence.Add(new { purpose = "TECHNICAL_BACKEND_SMOKE_NOT_BENCHMARK", model_id = id, model.ExpectedSha256,
                requested = actual.Requested.ToString(), actual.ActualBackend, actual.Device, actual.FallbackReason,
                actual.OffloadedLayers, simulated_vulkan_devices_hidden = runtime.HideVulkanDevicesForDiagnostics,
                actual.RuntimeBuild, actual.RuntimeCommit, actual.ServerPath, exercise.Id, exercise.Level, exercise.Task,
                student_text = exercise.IncorrectExample, prompt_profile = result.PromptProfileId,
                system_prompt_sha256 = result.SystemPromptSha256, generation = model.Generation,
                result, parsed, response_sha256 = Convert.ToHexString(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(result.Content))).ToLowerInvariant(),
                date_utc = DateTimeOffset.UtcNow, technical_success = true });
            Console.WriteLine($"RESULT {id} {actual.ActualBackend} parser={parsed.Status} seconds={result.ElapsedSeconds:F3}");
        }
    }
    catch (OperationCanceledException)
    {
        evidence.Add(new { purpose = "TECHNICAL_BACKEND_SMOKE_NOT_BENCHMARK", model_id = id,
            requested = preference.ToString(), error_type = "OperationCanceledException",
            error = "Caller cancelled; no retry or next model.", date_utc = DateTimeOffset.UtcNow, technical_success = false });
        await File.WriteAllTextAsync(output, JsonSerializer.Serialize(evidence, new JsonSerializerOptions { WriteIndented = true }), CancellationToken.None);
        Console.WriteLine($"CANCELLED: evidence preserved at {output}");
        return 130;
    }
    catch (Exception exception)
    {
        overallSuccess = false;
        evidence.Add(new { purpose = "TECHNICAL_BACKEND_SMOKE_NOT_BENCHMARK", model_id = id,
            requested = preference.ToString(), error_type = exception.GetType().Name,
            error = exception.Message, date_utc = DateTimeOffset.UtcNow, technical_success = false });
        Console.WriteLine($"FAIL {id} {exception.GetType().Name}: {exception.Message}");
        // Preserve the failure. No retry of this input and no quality-driven fallback.
        if (exception is LlamaRateLimitException)
        {
            await File.WriteAllTextAsync(output, JsonSerializer.Serialize(evidence, new JsonSerializerOptions { WriteIndented = true }), cancellation.Token);
            Console.WriteLine("STOP: HTTP 429. Evidence preserved; no further model will be loaded.");
            return 1;
        }
    }
    finally { await runtime.StopAsync(); }
    await File.WriteAllTextAsync(output, JsonSerializer.Serialize(evidence, new JsonSerializerOptions { WriteIndented = true }), cancellation.Token);
}
Console.WriteLine($"EVIDENCE {output}");
return overallSuccess ? 0 : 1;
