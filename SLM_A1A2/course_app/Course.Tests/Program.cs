using System.IO.Compression;
using System.Text.Json;
using Course.Core;
using Course.Tests;
using Microsoft.Data.Sqlite;
using WritingApp.Shared;

var content = new EmbeddedCourse();
var activities = content.Course.Units.SelectMany(u => u.Activities).ToArray();
var checks = new List<(string Id, Func<Task> Check)>
{
    ("C01-course-complete", () => Test(() => { Require(activities.Length == 33 && activities.Count(a => a.IsWriting) == 3); Require(content.Course.Units.All(u => u.Lessons.Length >= 30)); })),
    ("C02-all-thirty-answer-keys", () => Test(() => { foreach (var a in activities.Where(a => !a.IsWriting)) Require(ClosedExercise.Check(a, a.Answer!).Correct, a.Id); })),
    ("C03-wrong-answers-and-word-normalization", () => Test(() =>
    {
        foreach (var a in activities.Where(a => a.Type == "one_word")) { Require(ClosedExercise.Check(a, "  " + a.Answer!.ToUpperInvariant() + "  ").Correct); Require(!ClosedExercise.Check(a, a.Answer + ".").Correct); Require(!ClosedExercise.Check(a, "wrong").Correct); }
        foreach (var a in activities.Where(a => a.Type == "single_choice")) foreach (var o in a.Options!.Where(o => o.Id != a.Answer)) Require(!ClosedExercise.Check(a, o.Id).Correct);
    })),
    ("C04-empty-and-unknown-options-rejected", async () => { await Throws<ArgumentException>(() => Task.FromResult(ClosedExercise.Check(activities[0], ""))); await Throws<ArgumentException>(() => Task.FromResult(ClosedExercise.Check(activities[0], "z"))); }),
    ("C05-editorial-ambiguities-removed", () => Test(() => { Require(!content.Activity("u02-opcion-03").Options!.Any(o => o.Text == "I eat always breakfast at home.")); Require(!content.Activity("u03-opcion-03").Options!.Any(o => o.Text == "There is a balcony in your apartment?")); })),
    ("M01-full-catalog-and-qwen2-pins", () => Test(() => { Require(CourseModelCatalog.All.Count == 18 && PortableCatalog.All.Count == 15); var q = CourseModelCatalog.All.Where(m => m.Id.StartsWith("portable-unsloth-qwen35-2b-")).ToArray(); Require(q.Length == 3); Require(q.All(m => m.DownloadUrl!.Contains("f6d5376be1edb4d416d56da11e5397a961aca8ae") && m.Family == "qwen" && m.ThinkingToggle && m.Sha256.Length == 64)); })),
    ("D01-draft-queue-order-and-restart", async () =>
    {
        await using var f = new Fixture();
        await Task.WhenAll(Enumerable.Range(0, 50).Select(i => f.Store.SaveDraftAsync("u01-writing-01", i.ToString())));
        Require((await f.Store.SnapshotAsync()).Drafts["u01-writing-01"] == "49");
        using var reopened = new CourseStore(f.Store.DatabasePath); Require((await reopened.SnapshotAsync()).Drafts["u01-writing-01"] == "49");
    }),
    ("D02-practice-on-wrong-answer-counted-once", async () =>
    {
        await using var f = new Fixture(); var a = activities[0];
        await f.Store.SaveClosedAsync(a, "a", ClosedExercise.Check(a, "a"));
        var s = await f.Store.SnapshotAsync(); Require(s.Practiced.Count == 1 && s.ClosedCorrect == 0);
        await f.Store.SaveClosedAsync(a, a.Answer!, ClosedExercise.Check(a, a.Answer!));
        s = await f.Store.SnapshotAsync(); Require(s.Practiced.Count == 1 && s.ClosedCorrect == 1 && s.History.Length == 2);
    }),
    ("D03-settings-persist-and-validate", async () =>
    {
        await using var f = new Fixture(); var settings = new CourseSettings("portable-unsloth-qwen35-2b-q8-0", false, BackendPreference.Cpu, 4096, 3);
        await f.Store.SaveSettingsAsync(settings); Require(await f.Store.SettingsAsync() == settings);
        await Throws<InvalidDataException>(() => f.Store.SaveSettingsAsync(settings with { Context = 777 }));
    }),
    ("D04-unknown-schema-not-overwritten", async () =>
    {
        await using var f = new Fixture(); await f.Store.SnapshotAsync();
        using (var db = new SqliteConnection($"Data Source={f.Store.DatabasePath};Pooling=False")) { db.Open(); using var cmd = db.CreateCommand(); cmd.CommandText = "PRAGMA user_version=99;"; cmd.ExecuteNonQuery(); }
        using var newer = new CourseStore(f.Store.DatabasePath); await Throws<InvalidDataException>(() => newer.SnapshotAsync());
    }),
    ("D05-running-attempt-recovered-as-interrupted", async () =>
    {
        await using var f = new Fixture(); await f.Store.StartWritingAsync("interrupted", "u01-writing-01", false, "draft"); await f.Store.AppendRawAsync("interrupted", 1, 42, new("{", "length", 1));
        using var reopened = new CourseStore(f.Store.DatabasePath); var s = await reopened.SnapshotAsync(); Require(s.History.Single().Status == "interrupted" && s.Practiced.Count == 0);
        using var output = new MemoryStream(); await reopened.ExportHistoryAsync(output); using var json = JsonDocument.Parse(output.ToArray()); Require(json.RootElement.GetProperty("rawAttempts")[0].GetProperty("raw").GetString() == "{");
    }),
    ("D06-backup-restores-and-preserves-previous-state", async () =>
    {
        await using var f = new Fixture(); await f.Store.SaveDraftAsync("u01-writing-01", "before");
        using var backup = new MemoryStream(); await f.Store.BackupAsync(backup);
        await f.Store.SaveDraftAsync("u01-writing-01", "after"); backup.Position = 0; var previous = await f.Store.RestoreAsync(backup);
        Require(File.Exists(previous)); Require((await f.Store.SnapshotAsync()).Drafts["u01-writing-01"] == "before");
        using var old = new CourseStore(previous); Require((await old.SnapshotAsync()).Drafts["u01-writing-01"] == "after");
    }),
    ("D07-corrupt-backup-does-not-replace-progress", async () =>
    {
        await using var f = new Fixture(); await f.Store.SaveDraftAsync("u01-writing-01", "keep");
        using var backup = new MemoryStream(); await f.Store.BackupAsync(backup); backup.Position = 0;
        using (var zip = new ZipArchive(backup, ZipArchiveMode.Update, true)) { zip.GetEntry("course.db")!.Delete(); using var stream = zip.CreateEntry("course.db").Open(); stream.Write("invalid"u8); }
        backup.Position = 0; await Throws<InvalidDataException>(() => f.Store.RestoreAsync(backup)); Require((await f.Store.SnapshotAsync()).Drafts["u01-writing-01"] == "keep");
    }),
    ("W01-usable-feedback-completes-writing", async () =>
    {
        await using var f = new Fixture(); await f.PrepareAsync(); var s = await new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I am a student.", false, 1, null, CancellationToken.None);
        Require(s.Usable && s.Purpose == "COURSE_PRACTICE_NOT_BENCHMARK"); Require((await f.Store.SnapshotAsync()).Practiced.Contains("u01-writing-01")); Require(f.Engine.TextReceived == "I am a student." && f.Engine.ExerciseReceived!.Task == content.Activity("u01-writing-01").Prompt);
    }),
    ("W02-incorrect-writing-still-counts-as-practice", async () =>
    {
        await using var f = new Fixture(); f.Engine.Outputs.Clear(); f.Engine.Outputs.Enqueue(FakeEngine.IncorrectRaw); await f.PrepareAsync();
        var s = await new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I are a student.", false, 1, null, CancellationToken.None);
        Require(s.Usable && !s.Attempts[0].Parsed.Value!.IsCorrect); Require((await f.Store.SnapshotAsync()).Practiced.Count == 1);
    }),
    ("W03-laboratory-never-completes-course", async () =>
    {
        await using var f = new Fixture(); await f.PrepareAsync(); await new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I am a student.", true, 1, null, CancellationToken.None);
        Require((await f.Store.SnapshotAsync()).Practiced.Count == 0);
    }),
    ("W04-unusable-json-pending-with-raw", async () =>
    {
        await using var f = new Fixture(); f.Engine.Outputs.Clear(); f.Engine.Outputs.Enqueue("{\"is_correct\":"); await f.PrepareAsync();
        var s = await new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I am a student.", false, 1, null, CancellationToken.None);
        Require(!s.Usable && (await f.Store.SnapshotAsync()).Practiced.Count == 0); Require(s.Attempts[0].Output.Content == "{\"is_correct\":");
    }),
    ("W05-format-retry-retains-raw-and-seeds", async () =>
    {
        await using var f = new Fixture(); f.Engine.Outputs.Clear(); f.Engine.Outputs.Enqueue("bad"); f.Engine.Outputs.Enqueue(FakeEngine.CorrectRaw); await f.PrepareAsync();
        var s = await new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I am a student.", false, 3, null, CancellationToken.None);
        Require(s.Usable && f.Engine.Generations == 2 && f.Engine.Seeds.SequenceEqual([42, 43]) && s.Attempts[0].Output.Content == "bad");
    }),
    ("W06-technical-failure-no-retry-keeps-prior-raw", async () =>
    {
        await using var f = new Fixture(); f.Engine.Outputs.Clear(); f.Engine.Outputs.Enqueue("bad"); f.Engine.FailOnGeneration = 2; await f.PrepareAsync();
        await Throws<IOException>(() => new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I am a student.", false, 3, null, CancellationToken.None));
        var s = await f.Store.SnapshotAsync(); Require(s.History.Single().Status == "technical_error" && f.Engine.Generations == 2 && s.Practiced.Count == 0 && f.Runtime.State is null);
        using var output = new MemoryStream(); await f.Store.ExportHistoryAsync(output); using var json = JsonDocument.Parse(output.ToArray()); Require(json.RootElement.GetProperty("rawAttempts").GetArrayLength() == 1);
    }),
    ("W07-cancellation-never-retries", async () =>
    {
        await using var f = new Fixture(); f.Engine.CancelGeneration = true; await f.PrepareAsync();
        await Throws<OperationCanceledException>(() => new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I am a student.", false, 3, null, CancellationToken.None));
        Require(f.Engine.Generations == 1 && (await f.Store.SnapshotAsync()).History.Single().Status == "cancelled");
    }),
    ("W08-empty-feedback-and-recovered-json-usable", async () =>
    {
        await using var f = new Fixture(); f.Engine.Outputs.Clear(); f.Engine.Outputs.Enqueue("```json\n" + FakeEngine.CorrectRaw.Replace("Nice work!", "") + "\n```"); await f.PrepareAsync();
        var s = await new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I am a student.", false, 1, null, CancellationToken.None); Require(s.Usable && s.Attempts[0].Parsed.Status == "RECOVERED");
    }),
    ("W09-contradictory-verdict-cannot-complete-course", async () =>
    {
        await using var f = new Fixture(); f.Engine.Outputs.Clear(); f.Engine.Outputs.Enqueue(FakeEngine.CorrectRaw.Replace("\"is_correct\":true", "\"is_correct\":false")); await f.PrepareAsync();
        var s = await new WritingPracticeService(f.Store, f.Runtime).EvaluateAsync(content.Activity("u01-writing-01").ToExercise(), "I am a student.", false, 1, null, CancellationToken.None);
        Require(!s.Usable && s.Attempts[0].Parsed.Status == "INCONSISTENT" && (await f.Store.SnapshotAsync()).Practiced.Count == 0);
    }),
    ("M02-balanced-gpu-and-cpu-selection", () => Test(() =>
    {
        var advisor = new BalancedModelAdvisor(); var d = new DeviceProfile("Windows", "X64", 64L << 30, 48L << 30, 100L << 30);
        Require(BalancedModelAdvisor.IsQwen4(advisor.Recommend(CourseModelCatalog.All, d, new(true, "GPU", "host"), new(), _ => false).Model));
        Require(advisor.Recommend(CourseModelCatalog.All, d, new(true, "GPU", "host"), new(Backend: BackendPreference.Cpu), _ => false).Model.Id == BalancedModelAdvisor.GemmaId);
        Require(advisor.Recommend(CourseModelCatalog.All, d with { Platform = "Android" }, new(true, "GPU", "host"), new(), _ => false).Model.Id == BalancedModelAdvisor.GemmaId);
    })),
    ("M03-memory-fallback-and-manual-qwen2", () => Test(() =>
    {
        var advisor = new BalancedModelAdvisor(); var d = new DeviceProfile("Windows", "X64", 16L << 30, 1L << 30, 100L << 30);
        var low = advisor.Recommend(CourseModelCatalog.All, d, new(false, "CPU", "host"), new(), _ => false); Require(low.Model.Id == BalancedModelAdvisor.LfmId && !low.FitsEstimate);
        var manual = advisor.Recommend(CourseModelCatalog.All, d, new(false, "CPU", "host"), new("portable-unsloth-qwen35-2b-ud-q4-k-xl", false), _ => false); Require(manual.Model.Quantization == "UD-Q4_K_XL");
    })),
    ("M04-measured-choice-invalidates-on-hardware-context-or-expiry", () => Test(() =>
    {
        var advisor = new BalancedModelAdvisor(); var d = new DeviceProfile("Windows", "X64", 64L << 30, 48L << 30, 100L << 30); var gemma = CourseModelCatalog.All.First(m => m.Id == BalancedModelAdvisor.GemmaId);
        var p = new AutoAdviceProfile("host", 2048, gemma.Id, gemma.Sha256, "measured", DateTimeOffset.UtcNow, true, QwenRejected: true);
        Require(advisor.Recommend(CourseModelCatalog.All, d, new(true, "GPU", "host"), new(), _ => false, p).Model.Id == gemma.Id);
        Require(BalancedModelAdvisor.IsQwen4(advisor.Recommend(CourseModelCatalog.All, d, new(true, "GPU", "new"), new(), _ => false, p).Model));
        Require(BalancedModelAdvisor.IsQwen4(advisor.Recommend(CourseModelCatalog.All, d, new(true, "GPU", "host"), new(Context: 4096), _ => false, p).Model));
        Require(BalancedModelAdvisor.IsQwen4(advisor.Recommend(CourseModelCatalog.All, d, new(true, "GPU", "host"), new(), _ => false, p with { DateUtc = DateTimeOffset.UtcNow.AddMinutes(-6) }).Model));
    })),
    ("M05-partial-gpu-qualification-and-latency-limit", () => Test(() =>
    {
        var place = new RuntimePlacement(0, "gpu", 14); PlacementTrial Trial(double seconds) => new(place, Enumerable.Range(0, 3).Select(_ => new BackendTrial("gpu", seconds, 40, "stop", "STRICT", null)).ToArray(), null);
        var profile = new AdaptiveProfile("key", "model", "runtime", "driver", 2048, place, "partial", [Trial(25)], DateTimeOffset.UtcNow, []);
        var state = new EngineState(BackendPreference.AutoVulkanCpu, "Vulkan", "gpu", 14, null, 2048);
        Require(BalancedModelAdvisor.QwenQualified(state, profile)); Require(!BalancedModelAdvisor.QwenQualified(state, profile with { Trials = [Trial(31)] })); Require(!BalancedModelAdvisor.QwenQualified(state with { Backend = "CPU" }, profile));
    })),
    ("M06-exact-manual-placement-preserved", async () =>
    {
        await using var f = new Fixture(); var result = await f.Runtime.PrepareAsync(f.Model, new(f.Model.Id, false, BackendPreference.Vulkan, AdapterId: "gpu-1", GpuLayers: 14), false, null, CancellationToken.None);
        Require(result.Engine!.OffloadedLayers == 14 && result.Engine.Backend == "Vulkan" && f.Engine.Placement?.GpuLayers == 14);
    }),
    ("M07-selected-adapter-with-estimated-layers-preserved", async () =>
    {
        await using var f = new Fixture(); var result = await f.Runtime.PrepareAsync(f.Model, new(f.Model.Id, false, BackendPreference.Vulkan, AdapterId: "gpu-1"), false, null, CancellationToken.None);
        Require(result.Engine!.OffloadedLayers == 14 && f.Engine.Placement?.DeviceId == "gpu-1");
    }),
    ("M08-memory-recovery-upgrades-a-resource-fallback", () => Test(() =>
    {
        var advisor = new BalancedModelAdvisor(); var d = new DeviceProfile("Windows", "X64", 64L << 30, 48L << 30, 100L << 30);
        var lfm = CourseModelCatalog.All.First(m => m.Id == BalancedModelAdvisor.LfmId);
        var profile = new AutoAdviceProfile("host", 2048, lfm.Id, lfm.Sha256, "low-memory selection", DateTimeOffset.UtcNow, false);
        Require(advisor.Recommend(CourseModelCatalog.All, d, new(false, "CPU", "host"), new(), _ => true, profile).Model.Id == BalancedModelAdvisor.GemmaId);
    }))
};
checks.AddRange(MemoryPlanningTests.Cases);

var failures = 0;
var evidence = new List<(string Id, bool Passed, string? Error)>();
foreach (var (id, check) in checks)
{
    try { await check(); Console.WriteLine("PASS " + id); evidence.Add((id, true, null)); }
    catch (Exception e) { failures++; Console.WriteLine($"FAIL {id}: {e}"); evidence.Add((id, false, e.ToString())); }
}
var reportIndex = Array.IndexOf(args, "--report");
if (reportIndex >= 0 && reportIndex + 1 < args.Length)
{
    var path = Path.GetFullPath(args[reportIndex + 1]); Directory.CreateDirectory(Path.GetDirectoryName(path)!);
    using var file = File.Create(path); using var writer = new Utf8JsonWriter(file, new() { Indented = true });
    writer.WriteStartObject(); writer.WriteString("kind", "SYNTHETIC_TESTS_NO_MODEL_INFERENCE"); writer.WriteString("dateUtc", DateTimeOffset.UtcNow);
    writer.WriteNumber("passed", checks.Count - failures); writer.WriteNumber("total", checks.Count); writer.WritePropertyName("checks"); writer.WriteStartArray();
    foreach (var e in evidence) { writer.WriteStartObject(); writer.WriteString("id", e.Id); writer.WriteBoolean("passed", e.Passed); writer.WriteString("error", e.Error); writer.WriteEndObject(); }
    writer.WriteEndArray(); writer.WriteEndObject();
}
Console.WriteLine($"{checks.Count - failures}/{checks.Count} checks passed."); return failures == 0 ? 0 : 1;

static Task Test(Action test) { test(); return Task.CompletedTask; }
static void Require(bool condition, string? message = null) { if (!condition) throw new Exception(message ?? "Assertion failed"); }
static async Task Throws<T>(Func<Task> action) where T : Exception { try { await action(); } catch (T) { return; } throw new Exception("Expected " + typeof(T).Name); }
