using System.Text.Json;
using WritingDemo.Core;

var paths = DemoPaths.Locate();
var catalog = ModelCatalog.Load(paths);
var assets = new ModelAssets(paths);
var selectedIds = args.Length > 0 ? args : ["11-qwen35-4b-q4-k-m", "06-minicpm5-2b-q4-k-m", "13-gemma4-e2b-ud-q4-k-xl", "09-lfm25-12b-q4-k-m", "16-lfm25-26b-q4-k-m"];
var records = new List<object>();
using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };
var token = cts.Token;
await using var runtime = new LlamaRuntime(paths);
foreach (var id in selectedIds)
{
    var model = catalog.Single(m => m.Id == id);
    var path = assets.ResolvePath(model, paths.DefaultModelDirectory);
    Console.WriteLine($"VERIFY {id}");
    if (!await assets.VerifyAsync(model, path, null, token)) throw new InvalidDataException("The demonstration model did not pass verification.");
    await runtime.LoadAsync(model, path, paths.DefaultServerPath, token);
    var exercise = ExerciseCatalog.All[0];
    foreach (var (kind, text) in new[] { ("demo_example_correct", exercise.CorrectExample), ("demo_example_incorrect", exercise.IncorrectExample) })
    {
        var generated = await runtime.GenerateAsync(exercise, text, token);
        var parsed = FeedbackParser.Parse(generated.Content, text);
        records.Add(new { schema_version = "writing_local_demo.smoke/1.0", purpose = "TECHNICAL_DEMO_NOT_BENCHMARK_OR_HUMAN_REVIEW", model = model.Id, model.ExpectedSha256, exercise.Id, exercise.Level, exercise.Task, input_kind = kind, student_text = text, generated, parsed, date_utc = DateTimeOffset.UtcNow });
        Console.WriteLine($"RESULT {id} {kind} {parsed.Status} flag={parsed.Value?.IsCorrect} seconds={generated.ElapsedSeconds:F2}");
        Directory.CreateDirectory(paths.SessionDirectory);
        await File.WriteAllTextAsync(Path.Combine(paths.SessionDirectory, "smoke_current.json"), JsonSerializer.Serialize(records, new JsonSerializerOptions { WriteIndented = true }), token);
    }
    await runtime.StopAsync();
}
Console.WriteLine($"DONE {records.Count} demonstration generations. No benchmark cases were used.");
