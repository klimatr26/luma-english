#if COURSE_AUTOMATION
using Android.App;
using Android.Content;
using Android.Content.PM;
using Android.OS;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Platform;
using Avalonia.Controls.Presenters;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Course.Core;
using Course.UI;
using System.Text.Json.Nodes;
using System.Windows.Input;
using WritingApp.Shared;
using App = Course.UI.App;
using Path = System.IO.Path;

namespace Luma.AndroidApp;

/// <summary>Compiled only for the emulator verification APK; never part of the delivery APK.</summary>
[Activity(Name = "org.kevinlima.writinglab.CourseVerificationActivity", Exported = true, Label = "Luma verification")]
public sealed class CourseVerificationActivity : Activity
{
    private readonly JsonArray _checks = [];
    private string _mode = "full";
    private int _requestId;
    private string _folder = "";
    private CourseViewModel Vm => App.ViewModel!;
    private MainView View => ((App)Avalonia.Application.Current!).ActiveView!;
    protected override void OnCreate(Bundle? arguments)
    {
        base.OnCreate(arguments);
        _mode = Intent?.GetStringExtra("mode") ?? "full";
        _folder = Path.Combine(FilesDir!.AbsolutePath, "course-verification");
        Directory.CreateDirectory(_folder);
        _ = Task.Run(RunAsync);
    }
    private static Task Ui(Func<Task> work)
    {
        var result = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        Dispatcher.UIThread.Post(async () => { try { await work(); result.SetResult(); } catch (Exception e) { result.SetException(e); } });
        return result.Task.WaitAsync(TimeSpan.FromSeconds(60));
    }
    private Task OnUi(Action work) => Ui(() => { work(); return Task.CompletedTask; });
    private void Check(string id, bool pass, string? detail = null)
    {
        _checks.Add(new JsonObject { ["id"] = id, ["passed"] = pass, ["detail"] = detail });
        File.AppendAllText(Path.Combine(_folder, "progress.log"), $"{DateTimeOffset.UtcNow:O} {id}: {pass}\n");
        if (!pass) throw new InvalidOperationException(id + ": " + detail);
    }
    private async Task Wait(Func<bool> condition, int seconds = 60)
    {
        var deadline = DateTime.UtcNow.AddSeconds(seconds);
        while (DateTime.UtcNow < deadline)
        {
            var ready = false; await OnUi(() => ready = condition());
            if (ready) return;
            await Task.Delay(150);
        }
        throw new TimeoutException("No se completó la operación: " + Vm.Status);
    }
    private async Task Command(ICommand command)
    {
        await OnUi(() => { if (!command.CanExecute(null)) throw new InvalidOperationException("Comando no disponible."); command.Execute(null); });
        await Wait(() => !Vm.IsBusy && command.CanExecute(null), 600);
    }
    private async Task Shot(string name, string action = "screenshot", Avalonia.Point? point = null)
    {
        await Task.Delay(400);
        var id = ++_requestId;
        await File.WriteAllTextAsync(Path.Combine(_folder, "screenshot-request.json"), new JsonObject { ["id"] = id, ["name"] = name,
            ["action"] = action, ["x"] = point is null ? null : (int)point.Value.X, ["y"] = point is null ? null : (int)point.Value.Y }.ToJsonString());
        var deadline = DateTime.UtcNow.AddSeconds(45);
        while (DateTime.UtcNow < deadline)
        {
            if (File.Exists(Path.Combine(_folder, "screenshot-ack.txt")) && await File.ReadAllTextAsync(Path.Combine(_folder, "screenshot-ack.txt")) == id.ToString()) return;
            await Task.Delay(150);
        }
        throw new TimeoutException("El controlador ADB no confirmó la captura.");
    }
    private async Task Reveal(string name)
    {
        await Task.Delay(200);
        await OnUi(() =>
        {
            View.UpdateLayout();
            var page = View.FindControl<ScrollViewer>("PageScroll")!;
            var control = View.FindControl<Control>(name)!;
            if (control.TranslatePoint(default, page) is { } at) page.Offset = new(0, Math.Max(0, page.Offset.Y + at.Y - 12));
        });
    }
    private async Task RunAsync()
    {
        var report = new JsonObject { ["date_utc"] = DateTimeOffset.UtcNow.ToString("O"), ["mode"] = _mode, ["checks"] = _checks };
        try
        {
            File.WriteAllText(Path.Combine(_folder, "progress.log"), "Starting main activity\n");
            await OnUi(() => StartActivity(new Intent(this, typeof(MainActivity))));
            File.AppendAllText(Path.Combine(_folder, "progress.log"), "Waiting for course view\n");
            await Wait(() => App.ViewModel is not null && ((App?)Avalonia.Application.Current)?.ActiveView is not null);
            await Ui(() => Vm.InitializeAsync());
            File.AppendAllText(Path.Combine(_folder, "progress.log"), "Course initialized\n");
            var app = (AndroidApplication)Application!;
            var store = app.Store;
            var model = CourseModelCatalog.All.Single(m => m.Id == "09-lfm25-12b-q4-k-m");
            Check("A01-native-course-startup", Vm.Units.Length == 3 && Vm.Units.Sum(u => u.Unit.Activities.Length) == 33);
            Check("A02-complete-model-catalog", Vm.Models.Count == 18 && Vm.Models.Any(m => m.Id.Contains("qwen") && m.Name.Contains("2B") && m.DownloadUrl?.Contains("unsloth") == true));
            if (_mode == "resume")
            {
                var snapshot = await store.SnapshotAsync();
                Check("A18-restart-progress", snapshot.ClosedCorrect == 30 && snapshot.ClosedPracticed == 30);
                Check("A19-restart-draft", snapshot.Drafts.Values.Contains("Hello, my name is Sofia. I am a student."));
                Check("A20-restart-model", await app.Platform.Services.ModelStore.FindVerifiedAsync(model, CancellationToken.None) is not null);
                Check("A21-restart-writing-history", snapshot.History.Any(h => h.Kind == "writing" && h.SessionJson is not null));
                await Shot("home-restored");
                var historical = snapshot.History.First(h => h.Kind == "writing" && h.SessionJson is not null);
                var session = System.Text.Json.JsonSerializer.Deserialize(historical.SessionJson!, AppJsonContext.Default.ReviewSession)!;
                await OnUi(() =>
                {
                    Vm.OpenUnit(Vm.Units[0]); Vm.OpenActivity(Vm.Units[0].Unit.Activities.Single(a => a.IsWriting));
                    Vm.ApplySession(session); View.FindControl<Border>("WritingResult")!.BringIntoView();
                });
                Check("A22-restored-session-rendered", Vm.LastSession?.DateUtc == session.DateUtc && Vm.HasResult);
                Check("A23-restored-contract-state", Vm.UsableResult == session.Usable && (session.Usable || Vm.CorrectedText.Length == 0));
                Check("A24-cpu-package-not-advertised-as-vulkan", !app.Platform.Runtime.Hardware.HasVulkan);
                await Reveal("WritingResult");
                await Shot("writing-result-restored");
                await Reveal("WritingAnswer");
                Avalonia.Point? tap = null;
                await OnUi(() =>
                {
                    var top = TopLevel.GetTopLevel(View)!;
                    var at = View.FindControl<TextBox>("WritingAnswer")!.TranslatePoint(new(28, 28), top)!.Value;
                    tap = new(at.X * top.RenderScaling, at.Y * top.RenderScaling);
                });
                await Shot("keyboard-tap", "tap", tap);
                await Wait(() => TopLevel.GetTopLevel(View)?.InputPane?.State == InputPaneState.Open);
                await Task.Delay(400);
                await OnUi(() =>
                {
                    var top = TopLevel.GetTopLevel(View)!;
                    var pane = top.InputPane!.OccludedRect;
                    var shell = View.FindControl<Grid>("Shell")!;
                    var bottom = shell.TranslatePoint(new(0, shell.Bounds.Height), top)!.Value.Y;
                    Check("A25-keyboard-resizes-content", shell.Margin.Bottom > 0 && bottom <= pane.Top + 1, $"bottom={bottom}; keyboard={pane.Top}; inset={shell.Margin.Bottom}");
                    var presenter = View.FindControl<TextBox>("WritingAnswer")!.GetVisualDescendants().OfType<TextPresenter>().First();
                    var caret = presenter.TranslatePoint(presenter.CursorRectangle.BottomRight, top)!.Value;
                    Check("A26-caret-above-keyboard", caret.Y <= pane.Top + 1, $"caret={caret.Y}; keyboard={pane.Top}");
                });
                await Shot("keyboard-open");
                var original = Vm.StudentText;
                await Shot("native-typing", "type-roundtrip");
                await Wait(() => Vm.StudentText == original && !Vm.HasResult);
                await Ui(() => Vm.FlushDraftsAsync());
                Check("A27-native-input-and-draft", (await store.SnapshotAsync()).Drafts[session.ExerciseId] == original);
                await Shot("keyboard-dismiss", "hide-keyboard");
                await Wait(() => TopLevel.GetTopLevel(View)?.InputPane?.State == InputPaneState.Closed);
                await OnUi(() => Check("A28-keyboard-close-restores-layout", View.FindControl<Grid>("Shell")!.Margin.Bottom == 0 && View.FindControl<Border>("BottomNavigation")!.IsVisible));
                await Shot("keyboard-closed");
                await OnUi(() => Vm.SelectedModel = Vm.Models.Single(m => m.Id == session.Model.Id));
                await Ui(() => Vm.FlushDraftsAsync());
                var preferences = await store.SettingsAsync();
                Check("A29-manual-model-saved", preferences.ModelId == session.Model.Id && !preferences.AutomaticModel && Vm.SelectedModel?.Id == session.Model.Id);
                report["preferences"] = JsonNode.Parse(System.Text.Json.JsonSerializer.Serialize(preferences, CourseJsonContext.Default.CourseSettings));
            }
            else
            {
                Check("A03-model-free-course", !Vm.ModelReady && Vm.HomePage, Vm.CourseProgress);
                await Shot("home-portrait");
                foreach (var unit in Vm.Units)
                {
                    await OnUi(() => Vm.OpenUnit(unit));
                    Check("A04-lesson-" + unit.Unit.Id, Vm.ShowLesson && unit.Unit.Lessons.Length >= 5);
                    foreach (var exercise in unit.Unit.Activities.Where(a => !a.IsWriting))
                    {
                        await OnUi(() =>
                        {
                            Vm.OpenActivity(exercise);
                            if (exercise.Type == "single_choice") View.FindControl<ListBox>("AnswerChoices")!.SelectedItem = exercise.Options!.Single(o => o.Id == exercise.Answer);
                            else Vm.WordAnswer = exercise.Answer!;
                        });
                        await Command(Vm.CheckCommand);
                        Check("closed-" + exercise.Id, Vm.HasClosedFeedback && Vm.ClosedHeading.Contains("Bien"), Vm.ClosedHeading);
                    }
                }
                var closed = await store.SnapshotAsync();
                Check("A05-closed-progress", closed.ClosedPracticed == 30 && closed.ClosedCorrect == 30);
                var writing = Vm.Units[0].Unit.Activities.Single(a => a.IsWriting);
                await OnUi(() => { Vm.OpenUnit(Vm.Units[0]); Vm.OpenActivity(writing); View.FindControl<TextBox>("WritingAnswer")!.Text = "Hello, my name is Sofia. I am a student."; });
                await Ui(() => Vm.FlushDraftsAsync());
                Check("A06-real-editor-draft", (await store.SnapshotAsync()).Drafts[writing.Id] == Vm.StudentText);
                await OnUi(() => { if (MainActivity.Current?.TryGetTarget(out var main) == true) main.RequestedOrientation = ScreenOrientation.Landscape; });
                await Wait(() => View.Bounds.Width > View.Bounds.Height);
                Check("A07-landscape-draft", Vm.StudentText == "Hello, my name is Sofia. I am a student.");
                await Shot("writing-landscape");
                await OnUi(() => { if (MainActivity.Current?.TryGetTarget(out var main) == true) main.RequestedOrientation = ScreenOrientation.Portrait; });
                await Wait(() => View.Bounds.Height > View.Bounds.Width);
                await Shot("writing-portrait");
                await OnUi(() => { Vm.NavigateCommand.Execute("lab"); Vm.SimulateCommand.Execute(null); });
                Check("A08-invalid-json-warning", Vm.HasResult && !Vm.HasSession && Vm.Raw.Contains("SIMULACIÓN") && Vm.CourseProgress == "30 / 33");
                await Shot("json-warning");
                var staging = Path.Combine(FilesDir!.AbsolutePath, "diagnostic-models", Path.GetFileName(model.RelativePath));
                if (await app.Platform.Services.ModelStore.FindVerifiedAsync(model, CancellationToken.None) is null)
                {
                    await using var input = File.OpenRead(staging);
                    await app.Platform.Services.ModelStore.ImportAsync(model, input, null, CancellationToken.None);
                }
                Check("A09-import-sha256", await app.Platform.Services.ModelStore.FindVerifiedAsync(model, CancellationToken.None) is not null);
                await OnUi(() => { Vm.AutomaticModel = false; Vm.Advanced = true; Vm.SelectedModel = model; Vm.SelectedBackend = Vm.BackendChoices.First(b => b.Value == BackendPreference.AutoVulkanCpu); });
                await Command(Vm.PrepareCommand);
                Check("A10-auto-cpu-fallback", Vm.ModelReady && app.Platform.Runtime.State?.Backend == "CPU", Vm.ModelMessage);
                report["engine"] = JsonNode.Parse(System.Text.Json.JsonSerializer.Serialize(app.Platform.Runtime.State, AppJsonContext.Default.EngineState));
                await OnUi(() => { Vm.OpenUnit(Vm.Units[0]); Vm.OpenActivity(writing); });
                await Command(Vm.EvaluateCommand);
                Check("A11-real-native-inference", Vm.LastSession is { Attempts.Length: > 0 } session && session.Attempts[0].Output.Content.Length > 0, Vm.Status);
                report["session"] = JsonNode.Parse(SessionStore.Serialize(Vm.LastSession!));
                Check("A12-inference-not-technical-error", (await store.SnapshotAsync()).History.First().Status is "usable" or "unusable");
                await OnUi(() => View.FindControl<Border>("WritingResult")!.BringIntoView());
                await Shot("writing-result");
                await using (var file = File.Create(Path.Combine(_folder, "history.json"))) await Vm.ExportHistoryAsync(file, false);
                await using (var file = File.Create(Path.Combine(_folder, "history.csv"))) await Vm.ExportHistoryAsync(file, true);
                Check("A13-json-csv-export", JsonNode.Parse(await File.ReadAllTextAsync(Path.Combine(_folder, "history.json"))) is JsonObject && (await File.ReadAllLinesAsync(Path.Combine(_folder, "history.csv"))).Length > 30);
                using var backup = new MemoryStream(); await Ui(() => Vm.ExportBackupAsync(backup));
                await OnUi(() => { Vm.OpenActivity(Vm.Units[0].Unit.Activities.First(a => a.Type == "one_word")); Vm.WordAnswer = "wrong-answer"; });
                await Command(Vm.CheckCommand);
                Check("A14-incorrect-answer", (await store.SnapshotAsync()).ClosedCorrect == 29);
                backup.Position = 0; await Ui(() => Vm.RestoreAsync(backup));
                Check("A15-backup-restore", (await store.SnapshotAsync()).ClosedCorrect == 30);
                Check("A16-model-survives-restore", app.Platform.Services.ModelStore.FindExisting(model) is not null);
                await OnUi(() => { Vm.OpenUnit(Vm.Units[0]); Vm.OpenActivity(writing); Check("A17-restored-editor", Vm.StudentText == "Hello, my name is Sofia. I am a student."); Vm.GoBack(); });
            }
            report["success"] = true;
        }
        catch (Exception e) { report["success"] = false; report["exception"] = e.ToString(); }
        finally
        {
            await File.WriteAllTextAsync(Path.Combine(_folder, _mode + ".json"), report.ToJsonString());
            await OnUi(() => { if (MainActivity.Current?.TryGetTarget(out var main) == true) main.RequestedOrientation = ScreenOrientation.Unspecified; });
            RunOnUiThread(Finish);
        }
    }
}
#endif
