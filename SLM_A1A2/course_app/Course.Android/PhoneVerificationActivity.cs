#if COURSE_AUTOMATION
using Android.App;
using Android.Content;
using Android.OS;
using Android.Views;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Course.Core;
using Course.UI;
using Stopwatch = System.Diagnostics.Stopwatch;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Windows.Input;
using WritingApp.Android;
using WritingApp.Shared;
using App = Course.UI.App;

namespace Luma.AndroidApp;

/// <summary>Physical-device integration harness, excluded from normal APKs. User course data is never used.</summary>
[Activity(Name = "org.kevinlima.writinglab.PhoneVerificationActivity", Exported = true, Label = "Luma phone verification")]
public sealed class PhoneVerificationActivity : Activity
{
    private string _folder = "", _run = "", _mode = "";
    private readonly object _io = new();
    private readonly JsonArray _checks = [];
    private CourseViewModel _vm = null!;
    private MainView? _view;
    private AndroidApplication _app = null!;
    private CourseStore _store = null!;
    private MainActivity? _main;
    private static PhoneVerificationActivity? Running;
    internal static bool KeepScreenAwake { get; private set; }
    internal static void MainResumed(MainActivity activity)
    {
        if (Running is not { } test) return;
        test._main = activity; activity.Window?.AddFlags(WindowManagerFlags.KeepScreenOn); test.Status("Main activity resumed");
    }
    internal static void MainPaused() => Running?.Status("Main activity paused");
    private static Task Ui(Func<Task> work)
    {
        var done = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Dispatcher.UIThread.Post(async () => { try { await work(); done.SetResult(); } catch (Exception e) { done.SetException(e); } });
        return done.Task.WaitAsync(TimeSpan.FromSeconds(90));
    }
    private static Task Ui(Action work) => Ui(() => { work(); return Task.CompletedTask; });
    protected override void OnCreate(Bundle? state)
    {
        base.OnCreate(state);
        _run = Intent?.GetStringExtra("run") ?? "";
        _mode = Intent?.GetStringExtra("mode") ?? "";
        if (_run.Length is < 1 or > 60 || _run.Any(c => !char.IsAsciiLetterOrDigit(c) && c != '-') ||
            _mode is not ("inventory" or "selection" or "background-guard" or "automatic" or "ui" or "gemma" or "minicpm" or "qwen" or "gemma-memory" or "download-start" or "download-resume")) { Finish(); return; }
        _folder = Path.Combine(FilesDir!.AbsolutePath, "phone-verification", _run);
        Directory.CreateDirectory(_folder);
        _app = (AndroidApplication)Application!;
        KeepScreenAwake = true;
        Running = this;
        _ = Task.Run(RunAsync);
    }
    private void Status(string text)
    {
        lock (_io)
            File.AppendAllText(Path.Combine(_folder, "status.jsonl"), new JsonObject { ["utc"] = DateTimeOffset.UtcNow.ToString("O"),
                ["ticks"] = Stopwatch.GetTimestamp(), ["frequency"] = Stopwatch.Frequency, ["mode"] = _mode, ["message"] = text }.ToJsonString() + "\n");
    }
    private void Check(string id, bool pass, string? detail = null)
    {
        _checks.Add(new JsonObject { ["id"] = id, ["passed"] = pass, ["detail"] = detail }); Status(id + ": " + pass);
        if (!pass) throw new InvalidOperationException(id + ": " + detail);
    }
    private async Task Wait(Func<bool> ready, int seconds = 900)
    {
        var end = DateTime.UtcNow.AddSeconds(seconds);
        while (DateTime.UtcNow < end)
        {
            var result = false; await Ui(() => result = ready());
            if (result) return;
            await Task.Delay(150);
        }
        throw new TimeoutException(_vm.Status);
    }
    private async Task Command(ICommand command, Func<bool>? completed = null)
    {
        await Ui(() => { if (!command.CanExecute(null)) throw new InvalidOperationException("Command unavailable: " + _vm.Status); command.Execute(null); });
        // Unload intentionally disables its button; it must use the resulting state.
        await Wait(() => !_vm.IsBusy && (completed?.Invoke() ?? command.CanExecute(null)));
    }
    private async Task StartViewAsync()
    {
        _store = new(Path.Combine(_folder, "course-test.db"));
        await Ui(() =>
        {
            _vm = new(new EmbeddedCourse(), _store, _app.Platform.Runtime); App.ViewModel = _vm;
            var lifetime = (IActivityApplicationLifetime)Avalonia.Application.Current!.ApplicationLifetime!;
            lifetime.MainViewFactory = () => _view = new MainView(_vm);
            StartActivity(new Intent(this, typeof(MainActivity)));
        });
        await Wait(() => _view is not null && _main is not null, 90);
        await Ui(() => _vm.InitializeAsync());
        await Ui(() => _main!.Window?.AddFlags(WindowManagerFlags.KeepScreenOn));
        Check("sandbox-database", !_store.DatabasePath.Equals(_app.Store.DatabasePath, StringComparison.Ordinal));
    }
    private async Task RunAsync()
    {
        var report = new JsonObject { ["purpose"] = "PHONE_INTEGRATION_NOT_BENCHMARK", ["run"] = _run, ["mode"] = _mode,
            ["utc"] = DateTimeOffset.UtcNow.ToString("O"), ["firmware"] = Build.Fingerprint, ["api"] = (int)Build.VERSION.SdkInt,
            ["checks"] = _checks, ["stopwatch_frequency"] = Stopwatch.Frequency };
        _app.Platform.Runtime.StatusChanged += Status;
        try
        {
            Status("Starting " + _mode);
            if (_mode.StartsWith("download-", StringComparison.Ordinal)) { await StartViewAsync(); await DownloadAsync(report); }
            else
            {
                await StartViewAsync();
                report["device"] = JsonNode.Parse(JsonSerializer.Serialize(_app.Platform.Device(), AppJsonContext.Default.DeviceProfile));
                report["hardware"] = new JsonObject { ["has_vulkan"] = _app.Platform.Runtime.Hardware.HasVulkan,
                    ["description"] = _app.Platform.Runtime.Hardware.Description, ["fingerprint"] = _app.Platform.Runtime.Hardware.Fingerprint,
                    ["low_memory"] = _app.Platform.Runtime.Hardware.LowMemory };
                var initial = _vm.SelectedModel!;
                var memoryPlan = ModelMemoryPlanner.Plan(initial, _app.Platform.Device(), 2048,
                    _app.Platform.Services.ModelStore.FindExisting(initial) is not null, _app.Platform.Runtime.Hardware.LowMemory);
                report["initial_selection"] = new JsonObject { ["model_id"] = initial.Id, ["automatic"] = _vm.AutomaticModel,
                    ["reason"] = _vm.Recommendation, ["fits"] = memoryPlan.Fits, ["mapped_weight_allowance"] = memoryPlan.UsesMappedWeights,
                    ["working_bytes"] = memoryPlan.WorkingSetBytes, ["required_available_bytes"] = memoryPlan.RequiredAvailableBytes,
                    ["system_reserve_bytes"] = memoryPlan.SystemReserveBytes };
                if (_mode == "inventory")
                {
                    if (Intent?.GetStringExtra("import-model") is { } importId)
                    {
                        var model = _vm.Models.Single(m => m.Id == importId);
                        var source = Path.Combine(GetExternalFilesDir(null)!.AbsolutePath, "technical-imports", Path.GetFileName(model.RelativePath));
                        Status("Importing local staging GGUF through the application store: " + model.Id);
                        await Ui(() => _vm.SelectedModel = model);
                        await using (var input = File.OpenRead(source)) await Ui(() => _vm.ImportAsync(input));
                        var imported = await _app.Platform.Services.ModelStore.FindVerifiedAsync(model, CancellationToken.None);
                        Check("local-staging-import-verified", imported is not null, model.Id);
                        File.Delete(source); report["imported_model"] = model.Id; report["import_staging_removed"] = true;
                    }
                    var files = new JsonArray();
                    foreach (var path in Directory.EnumerateFiles(_app.Platform.Services.ModelStore.CacheDirectory, "*.gguf", SearchOption.AllDirectories))
                    {
                        var info = new FileInfo(path); files.Add(new JsonObject { ["path"] = Path.GetRelativePath(FilesDir!.AbsolutePath, path),
                            ["bytes"] = info.Length, ["mtime_utc"] = info.LastWriteTimeUtc.ToString("O") });
                    }
                    report["models"] = files;
                    report["old_sessions"] = Directory.EnumerateFiles(Path.Combine(FilesDir!.AbsolutePath, "sessions")).Count();
                    Check("complete-catalogue", _vm.Models.Count == 18);
                }
                else if (_mode == "selection") { Check("automatic-selection", _vm.AutomaticModel); Check("catalogue-proposal", _vm.Models.Any(m => m.Id == initial.Id)); }
                else if (_mode == "background-guard") await BackgroundGuardAsync(report);
                else if (_mode == "automatic") await ModelAsync(report, initial.Id, automatic: true);
                else if (_mode == "ui") await CourseUiAsync(report);
                else if (_mode == "gemma-memory") await MemoryAndCacheAsync(report);
                else await ModelAsync(report, _mode switch
                {
                    "gemma" => BalancedModelAdvisor.GemmaId,
                    "minicpm" => "06-minicpm5-2b-q4-k-m",
                    _ => "portable-unsloth-qwen35-4b-q4-k-m"
                });
                await Ui(() => _vm.FlushDraftsAsync());
            }
            report["success"] = true;
        }
        catch (Exception e) { report["success"] = false; report["exception"] = e.ToString(); Status(e.Message); }
        finally
        {
            _app.Platform.Runtime.StatusChanged -= Status;
            try { await _app.Platform.Runtime.UnloadAsync(); } catch (Exception e) { report["cleanup_error"] = e.Message; }
            // Keep the diagnostic view awake between phases. Backgrounding, the power
            // button or restoring the normal APK ends this window-only setting.
            Running = null; _main = null;
            await File.WriteAllTextAsync(Path.Combine(_folder, _mode + ".json"), report.ToJsonString());
            RunOnUiThread(Finish);
        }
    }
    private async Task CourseUiAsync(JsonObject report)
    {
        await Ui(() => _main!.RequestedOrientation = Android.Content.PM.ScreenOrientation.Portrait);
        await Wait(() => _view!.Bounds.Height > _view.Bounds.Width, 30);
        await SummaryAsync(report, "empty-portrait");
        Check("three-units", _vm.Units.Length == 3);
        foreach (var unit in _vm.Units)
        {
            await Ui(() => _vm.OpenUnit(unit)); Check("lesson-" + unit.Unit.Id, _vm.ShowLesson);
            foreach (var exercise in unit.Unit.Activities.Where(a => !a.IsWriting))
            {
                await Ui(() =>
                {
                    _vm.OpenActivity(exercise);
                    if (exercise.Type == "single_choice") _view!.FindControl<ListBox>("AnswerChoices")!.SelectedItem = exercise.Options!.Single(o => o.Id == exercise.Answer);
                    else _vm.WordAnswer = exercise.Answer!;
                });
                await Command(_vm.CheckCommand); Check(exercise.Id, _vm.ClosedHeading.Contains("Bien"));
            }
        }
        var writing = _vm.Units[0].Unit.Activities.Single(a => a.IsWriting);
        await Ui(() => { _vm.OpenUnit(_vm.Units[0]); _vm.OpenActivity(writing); _view!.FindControl<TextBox>("WritingAnswer")!.Text = writing.CorrectExample; });
        await Ui(() => _vm.FlushDraftsAsync());
        Check("draft-saved", (await _store.SnapshotAsync()).Drafts[writing.Id] == writing.CorrectExample);
        await KeyboardAsync(report);
        await Ui(() => _main!.RequestedOrientation = Android.Content.PM.ScreenOrientation.Landscape);
        await Wait(() => _view!.Bounds.Width > _view.Bounds.Height, 30); Check("rotation-landscape", _vm.StudentText == writing.CorrectExample);
        await Ui(() => _main!.RequestedOrientation = Android.Content.PM.ScreenOrientation.Portrait);
        await Wait(() => _view!.Bounds.Height > _view.Bounds.Width, 30);
        await Ui(() => { _vm.NavigateCommand.Execute("lab"); _vm.SimulateCommand.Execute(null); });
        Check("invalid-json-warning", _vm.HasResult && !_vm.HasSession && _vm.CourseProgress == "30 / 33");
        await using (var output = File.Create(Path.Combine(_folder, "history.json"))) await _vm.ExportHistoryAsync(output, false);
        await using (var output = File.Create(Path.Combine(_folder, "history.csv"))) await _vm.ExportHistoryAsync(output, true);
        using var backup = new MemoryStream(); await Ui(() => _vm.ExportBackupAsync(backup));
        await Ui(() => { _vm.OpenUnit(_vm.Units[0]); _vm.OpenActivity(_vm.Units[0].Unit.Activities.First(a => a.Type == "one_word")); _vm.WordAnswer = "wrong-fixture"; });
        await Command(_vm.CheckCommand); Check("wrong-answer", (await _store.SnapshotAsync()).ClosedCorrect == 29);
        backup.Position = 0; await Ui(() => _vm.RestoreAsync(backup));
        Check("backup-restore", (await _store.SnapshotAsync()).ClosedCorrect == 30);
        await Ui(() => _vm.SelectedModel = _vm.Models.First(m => m.Id.Contains("qwen35-2b-q8")));
        await Ui(() => _vm.FlushDraftsAsync()); Check("advanced-model-selection", (await _store.SettingsAsync()).ModelId == _vm.SelectedModel!.Id);
        await SummaryAsync(report, "practiced-portrait");
        await Ui(() => _main!.RequestedOrientation = Android.Content.PM.ScreenOrientation.Landscape);
        await Wait(() => _view!.Bounds.Width > _view.Bounds.Height, 30);
        await SummaryAsync(report, "practiced-landscape");
        await Ui(() => _main!.RequestedOrientation = Android.Content.PM.ScreenOrientation.Portrait);
        await Wait(() => _view!.Bounds.Height > _view.Bounds.Width, 30);
        await SummaryAsync(report, "restored-portrait");
        report["progress"] = _vm.CourseProgress;
    }
    private async Task SummaryAsync(JsonObject report, string stage)
    {
        await Ui(() => _vm.NavigateCommand.Execute("course"));
        await Task.Delay(150);
        await Ui(() =>
        {
            _view!.UpdateLayout();
            var summary = _view.FindControl<Grid>("SummaryMetrics")!;
            var cards = new[] { "PracticeSummary", "AccuracySummary", "WritingSummary" }.Select(n => _view.FindControl<Border>(n)!).ToArray();
            Check("summary-cards-" + stage, cards.All(c => c.Bounds.Width > 0 && c.Bounds.Left >= 0 && c.Bounds.Right <= summary.Bounds.Width + 1 && c.Bounds.Bottom <= summary.Bounds.Height + 1)
                && !cards[0].Bounds.Intersects(cards[1].Bounds) && !cards[1].Bounds.Intersects(cards[2].Bounds));
            var textFits = cards.All(c => c.GetVisualDescendants().OfType<TextBlock>().Where(t => t.IsEffectivelyVisible).All(t =>
            {
                var p = t.TranslatePoint(default, c)!.Value;
                return p.X >= 0 && p.Y >= 0 && p.X + t.Bounds.Width <= c.Bounds.Width + 1 && p.Y + t.Bounds.Height <= c.Bounds.Height + 1
                    && t.TextLayout.Width <= t.Bounds.Width + 1 && t.TextLayout.Height <= t.Bounds.Height + 1;
            }));
            Check("summary-text-" + stage, textFits);
            var label = _view.FindControl<TextBlock>("AccuracyLabel")!; var detail = _view.FindControl<TextBlock>("AccuracyDetail")!;
            Check("summary-detail-separated-" + stage, label.Bounds.Bottom <= detail.Bounds.Top);
            var bar = _view.FindControl<Avalonia.Controls.ProgressBar>("CourseProgressBar")!; var point = bar.TranslatePoint(default, cards[0])!.Value;
            Check("summary-progress-" + stage, bar.ClipToBounds && bar.Bounds.Width > 0 && point.X >= 0 && point.X + bar.Bounds.Width <= cards[0].Bounds.Width + 1);
            Check("summary-responsive-" + stage, Grid.GetRow(cards[1]) == (summary.Bounds.Width < 900 ? 1 : 0)
                && Grid.GetColumn(cards[1]) == (summary.Bounds.Width < 900 ? 0 : 1));
            var samples = report["summary_layout"] as JsonArray;
            if (samples is null) report["summary_layout"] = samples = new JsonArray();
            samples.Add(new JsonObject { ["stage"] = stage, ["width_dip"] = summary.Bounds.Width, ["height_dip"] = summary.Bounds.Height,
                ["accuracy"] = _vm.ClosedAccuracy, ["detail"] = detail.Text });
            var scroll = _view.FindControl<ScrollViewer>("PageScroll")!;
            if (summary.TranslatePoint(default, _view.FindControl<StackPanel>("PageBody")!) is { } at) scroll.Offset = new(0, Math.Max(0, at.Y - 12));
        });
    }
    private async Task KeyboardAsync(JsonObject report)
    {
        await Task.Delay(250);
        await Ui(() =>
        {
            _view!.UpdateLayout(); var box = _view.FindControl<TextBox>("WritingAnswer")!;
            var scroll = _view.FindControl<ScrollViewer>("PageScroll")!;
            if (box.TranslatePoint(default, scroll) is { } at) scroll.Offset = new(0, Math.Max(0, scroll.Offset.Y + at.Y - 12));
            box.Focus();
            var ime = (global::Android.Views.InputMethods.InputMethodManager)GetSystemService(InputMethodService)!;
            ime.ShowSoftInput(_main!.CurrentFocus ?? _main.Window!.DecorView, global::Android.Views.InputMethods.ShowFlags.Implicit);
        });
        var end = DateTime.UtcNow.AddSeconds(15); var open = false;
        while (DateTime.UtcNow < end && !open) { await Ui(() => open = TopLevel.GetTopLevel(_view)?.InputPane?.State == Avalonia.Controls.Platform.InputPaneState.Open); await Task.Delay(150); }
        report["keyboard_opened"] = open;
        if (open)
        {
            await Task.Delay(350);
            await Ui(() =>
            {
                var top = TopLevel.GetTopLevel(_view)!; var shell = _view!.FindControl<Grid>("Shell")!;
                var bottom = shell.TranslatePoint(new(0, shell.Bounds.Height), top)!.Value.Y;
                Check("keyboard-content-visible", bottom <= top.InputPane!.OccludedRect.Top + 1);
                var box = _view!.FindControl<TextBox>("WritingAnswer")!; var original = box.Text; box.CaretIndex = box.Text!.Length;
                box.RaiseEvent(new Avalonia.Input.TextInputEventArgs { RoutedEvent = Avalonia.Input.InputElement.TextInputEvent, Text = "X" });
                box.RaiseEvent(new Avalonia.Input.KeyEventArgs { RoutedEvent = Avalonia.Input.InputElement.KeyDownEvent, Key = Avalonia.Input.Key.Back });
                Check("control-input-roundtrip", box.Text == original);
                top.FocusManager.Focus(null);
                ((global::Android.Views.InputMethods.InputMethodManager)GetSystemService(InputMethodService)!).HideSoftInputFromWindow(_main!.Window!.DecorView.WindowToken, global::Android.Views.InputMethods.HideSoftInputFlags.None);
            });
            await Wait(() => TopLevel.GetTopLevel(_view)?.InputPane?.State == Avalonia.Controls.Platform.InputPaneState.Closed, 20);
        }
    }
    private async Task ModelAsync(JsonObject report, string modelId, bool automatic = false)
    {
        var model = _vm.Models.Single(m => m.Id == modelId);
        Status("Verifying cached model: " + modelId);
        var path = await _app.Platform.Services.ModelStore.FindVerifiedAsync(model, CancellationToken.None);
        Check("pinned-local-gguf", path is not null, modelId);
        report["model_id"] = modelId; report["model_sha256"] = model.Sha256;
        if (Intent?.GetBooleanExtra("fresh", false) == true)
        {
            Status("Archiving prior calibration for a fresh foreground comparison");
            await _app.Platform.Runtime.RecalibrateAsync(model, 2048, CancellationToken.None);
            report["fresh_calibration_requested"] = true;
        }
        await Ui(() => { _vm.SelectedModel = model; _vm.AutomaticModel = automatic; _vm.SelectedBackend = _vm.BackendChoices.First(b => b.Value == BackendPreference.AutoVulkanCpu); _vm.Context = 2048; _vm.MaximumAttempts = 1; });
        var timer = Stopwatch.StartNew(); await Command(_vm.PrepareCommand);
        report["prepare_including_verification_and_calibration_seconds"] = timer.Elapsed.TotalSeconds;
        Check("model-prepared", _vm.ModelReady, _vm.ModelMessage);
        if (automatic && _vm.SelectedModel is { } actual && actual.Id != model.Id)
        {
            report["initial_requested_model_id"] = model.Id;
            model = actual; report["model_id"] = actual.Id; report["model_sha256"] = actual.Sha256;
            Check("automatic-model-transition-pinned", await _app.Platform.Services.ModelStore.FindVerifiedAsync(actual, CancellationToken.None) is not null);
        }
        report["prepared_model_id"] = _vm.SelectedModel?.Id;
        report["engine"] = JsonNode.Parse(JsonSerializer.Serialize(_app.Platform.Runtime.State, AppJsonContext.Default.EngineState));
        report["profile"] = _app.Platform.LastCalibration is { } profile ? JsonNode.Parse(JsonSerializer.Serialize(profile, AppJsonContext.Default.AdaptiveProfile)) : null;
        var sessions = new JsonArray(); report["sessions"] = sessions;
        var writing = _vm.Units[0].Unit.Activities.Single(a => a.IsWriting);
        foreach (var correct in new[] { true, false })
        {
            Status("Course generation: " + (correct ? "correct example" : "incorrect example"));
            await Ui(() => { _vm.OpenUnit(_vm.Units[0]); _vm.OpenActivity(writing); _vm.StudentText = correct ? writing.CorrectExample! : writing.IncorrectExample!; });
            await Command(_vm.EvaluateCommand);
            Check("native-generation-" + correct, _vm.LastSession is { Attempts.Length: 1 }, _vm.Status);
            sessions.Add(JsonNode.Parse(SessionStore.Serialize(_vm.LastSession!)));
            await File.WriteAllTextAsync(Path.Combine(_folder, _mode + "-checkpoint.json"), report.ToJsonString());
        }
        Check("profile-present", _app.Platform.LastCalibration is not null);
        await using var export = File.Create(Path.Combine(_folder, _mode + "-history.json")); await _vm.ExportHistoryAsync(export, false);
        var selectedProfile = _app.Platform.LastCalibration!;
        await Command(_vm.UnloadCommand, () => !_vm.ModelReady); timer.Restart(); await Command(_vm.PrepareCommand);
        report["cached_prepare_seconds"] = timer.Elapsed.TotalSeconds;
        Check("calibration-cache-reused", _app.Platform.LastCalibration?.Key == selectedProfile.Key && _app.Platform.LastCalibration?.DateUtc == selectedProfile.DateUtc);
        report["progress"] = _vm.CourseProgress;
    }
    private async Task BackgroundGuardAsync(JsonObject report)
    {
        var model = _vm.Models.Single(m => m.Id == BalancedModelAdvisor.GemmaId);
        Check("pinned-local-gguf", await _app.Platform.Services.ModelStore.FindVerifiedAsync(model, CancellationToken.None) is not null);
        await _app.Platform.Runtime.RecalibrateAsync(model, 2048, CancellationToken.None);
        var warmup = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        void Observe(string message) { if (message.StartsWith("Calibrando CPU: calentamiento", StringComparison.Ordinal)) warmup.TrySetResult(); }
        _app.Platform.Runtime.StatusChanged += Observe;
        try
        {
            await Ui(() => { _vm.SelectedModel = model; _vm.AutomaticModel = false; _vm.SelectedBackend = _vm.BackendChoices.First(b => b.Value == BackendPreference.AutoVulkanCpu); _vm.PrepareCommand.Execute(null); });
            await warmup.Task.WaitAsync(TimeSpan.FromSeconds(90));
            await Ui(() =>
            {
                report["busy_keeps_display_awake"] = _vm.KeepsDisplayAwake;
                report["window_keep_screen_on"] = (_main!.Window!.Attributes!.Flags & WindowManagerFlags.KeepScreenOn) != 0;
                StartActivity(new Intent(Intent.ActionMain).AddCategory(Intent.CategoryHome).SetFlags(ActivityFlags.NewTask));
            });
            await Wait(() => !_vm.IsBusy, 30);
            Check("background-calibration-cancelled", !_vm.ModelReady && _app.Platform.LastCalibration is null, _vm.ModelMessage);
            Check("foreground-message", _vm.ModelMessage.Contains("Mantén la app visible", StringComparison.Ordinal));
            Check("display-hold-ended", !_vm.KeepsDisplayAwake);
            report["message"] = _vm.ModelMessage;
        }
        finally { _app.Platform.Runtime.StatusChanged -= Observe; }
    }
    private async Task DownloadAsync(JsonObject report)
    {
        var original = CourseModelCatalog.All.Single(m => m.Id == BalancedModelAdvisor.LfmId);
        var fixture = original with { Id = "phone-download-" + _run, DownloadUrl = original.DownloadUrl + "&phone_validation=" + _run };
        var transport = new AndroidDownloadTransport(this, [fixture], "Luma technical transfer");
        var checkpoint = Path.Combine(_folder, "download-ticket.json");
        if (_mode == "download-start")
        {
            var id = await transport.StartOrFindAsync(fixture);
            var snapshot = await transport.QueryAsync(id);
            await File.WriteAllTextAsync(checkpoint, new JsonObject { ["id"] = id, ["uri"] = fixture.DownloadUrl, ["started_utc"] = DateTimeOffset.UtcNow.ToString("O") }.ToJsonString());
            report["id"] = id; report["bytes"] = snapshot.ReceivedBytes; report["state"] = snapshot.State.ToString();
            Check("system-transfer-created", id > 0);
            report["cleanup_required"] = true;
        }
        else
        {
            var ticket = JsonNode.Parse(await File.ReadAllTextAsync(checkpoint))!; var id = ticket["id"]!.GetValue<long>();
            var before = await transport.QueryAsync(id); var reattached = await transport.StartOrFindAsync(fixture); var after = await transport.QueryAsync(id);
            report["id"] = id; report["reattached_id"] = reattached; report["bytes"] = after.ReceivedBytes; report["state"] = after.State.ToString();
            try { Check("same-system-job-after-process-restart", id == reattached); Check("transfer-progress", after.ReceivedBytes > 0 && after.State != SystemDownloadState.Failed, after.Message); }
            finally { await transport.RemoveAsync(id); if (reattached != id) await transport.RemoveAsync(reattached); report["temporary_job_removed"] = true; }
        }
    }
    private async Task MemoryAndCacheAsync(JsonObject report)
    {
        var model = _vm.Models.Single(m => m.Id == BalancedModelAdvisor.GemmaId);
        var previous = Directory.EnumerateFiles(Path.Combine(FilesDir!.AbsolutePath, "adaptive-profiles"), "*.json")
            .Where(p => !Path.GetFileName(p).StartsWith("trace-", StringComparison.Ordinal))
            .Select(p => { try { return JsonSerializer.Deserialize(File.ReadAllText(p), AppJsonContext.Default.AdaptiveProfile); } catch (JsonException) { return null; } })
            .First(p => p?.ModelId == model.Id && p.Context == 2048)!;
        var samples = new JsonArray(); report["samples"] = samples;
        foreach (var backend in new[] { BackendPreference.Cpu, BackendPreference.Vulkan })
        {
            Status("MEMORY_ROUTE " + backend);
            await Ui(() => { _vm.AutomaticModel = false; _vm.SelectedModel = model; _vm.SelectedBackend = _vm.BackendChoices.First(b => b.Value == backend); });
            var clock = Stopwatch.StartNew(); await Command(_vm.PrepareCommand);
            Check("manual-prepare-" + backend, _vm.ModelReady, _vm.ModelMessage);
            var prepare = clock.Elapsed.TotalSeconds;
            var writing = _vm.Units[0].Unit.Activities.Single(a => a.IsWriting);
            await Ui(() => { _vm.OpenUnit(_vm.Units[0]); _vm.OpenActivity(writing); _vm.StudentText = writing.IncorrectExample!; });
            await Command(_vm.EvaluateCommand);
            Check("manual-generation-" + backend, _vm.LastSession is { Attempts.Length: 1 });
            samples.Add(new JsonObject { ["backend_requested"] = backend.ToString(), ["prepare_seconds_including_hash"] = prepare,
                ["session"] = JsonNode.Parse(SessionStore.Serialize(_vm.LastSession!)) });
            await File.WriteAllTextAsync(Path.Combine(_folder, _mode + "-checkpoint.json"), report.ToJsonString());
        }
        Status("CACHE_REUSE Auto");
        await Ui(() => _vm.SelectedBackend = _vm.BackendChoices.First(b => b.Value == BackendPreference.AutoVulkanCpu));
        await Command(_vm.PrepareCommand);
        var current = _app.Platform.LastCalibration;
        Check("auto-profile-present", current is not null);
        report["prior_package_profile_key"] = previous.Key;
        report["runtime_update_invalidated_prior_profile"] = current!.Runtime != previous.Runtime;
        // A new APK can change the runtime fingerprint. Test reuse only after the
        // first Auto preparation in this installation, never against an old APK.
        await Command(_vm.UnloadCommand, () => !_vm.ModelReady); await Command(_vm.PrepareCommand);
        Check("calibration-cache-reused", _app.Platform.LastCalibration?.Key == current.Key && _app.Platform.LastCalibration?.DateUtc == current.DateUtc);
        report["reused_profile_key"] = current.Key; report["reused_profile_date"] = current.DateUtc.ToString("O");
        report["engine"] = JsonNode.Parse(JsonSerializer.Serialize(_app.Platform.Runtime.State, AppJsonContext.Default.EngineState));
    }
}
#endif
