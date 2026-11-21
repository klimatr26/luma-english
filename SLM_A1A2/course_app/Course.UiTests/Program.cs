using System.Text.Json;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Headless;
using Avalonia.Media.Imaging;
using Avalonia.Threading;
using Avalonia.VisualTree;
using Course.Core;
using Course.Tests;
using Course.UI;
using WritingApp.Shared;
using WritingDemo.Core;

namespace Course.UiTests;

internal static class Program
{
    private static int _failed;
    private static readonly List<(string Id, string? Error)> Evidence = [];
    private static string _screenshots = Path.GetFullPath("artifacts/verification/screenshots");
    [STAThread]
    private static int Main(string[] args)
    {
        var screenshotsIndex = Array.IndexOf(args, "--screenshots");
        if (screenshotsIndex >= 0 && screenshotsIndex + 1 < args.Length) _screenshots = Path.GetFullPath(args[screenshotsIndex + 1]);
        Directory.CreateDirectory(_screenshots);
        var initial = new Fixture();
        App.ViewModel = new(new EmbeddedCourse(), initial.Store, initial.Runtime);
        AppBuilder.Configure<App>().UseSkia().UseHeadless(new AvaloniaHeadlessPlatformOptions { UseHeadlessDrawing = false }).SetupWithoutStarting();
        AvaloniaSynchronizationContext.InstallIfNeeded();
        Run("UI01-course-works-without-model", f =>
        {
            Require(f.Vm.HomePage && f.Vm.Units.Length == 3 && !f.Vm.ModelReady);
            f.Vm.OpenUnit(f.Vm.Units[0]); Require(f.Vm.ShowLesson && f.Vm.Lessons.Length >= 30 && f.Data.Engine.Generations == 0);
        });
        Run("UI02-closed-selection-check-and-history", f =>
        {
            f.Vm.OpenUnit(f.Vm.Units[0]); f.Vm.PracticeCommand.Execute(null); Layout(f.Window);
            var choices = f.View.FindControl<ListBox>("AnswerChoices")!; choices.SelectedIndex = 1; Dispatcher.UIThread.RunJobs();
            Require(f.Vm.SelectedChoice?.Id == "b"); f.Vm.CheckCommand.Execute(null);
            WaitUntil(() => f.Vm.HasClosedFeedback && f.Vm.History.Count == 1);
            Require(f.Vm.ClosedHeading.Contains("Bien hecho") && f.Vm.CourseProgress == "1 / 33");
        });
        Run("UI03-writing-draft-navigation-and-model-change", f =>
        {
            f.Writing(); f.Vm.StudentText = "I am a student."; f.Vm.ApplySession(Session(f)); Require(f.Vm.UsableResult);
            f.Vm.SelectedModel = f.Vm.Models.First(m => m.Id.Contains("qwen35-2b-q8"));
            Require(!f.Vm.HasResult && !f.Vm.AutomaticModel);
            f.Vm.NavigateCommand.Execute("course"); f.Writing(); Require(f.Vm.StudentText == "I am a student.");
        });
        Run("UI04-catalog-bindings-include-all-qwen2-variants", f =>
        {
            f.Vm.NavigateCommand.Execute("models"); f.Vm.Advanced = true; Layout(f.Window);
            var picker = f.View.FindControl<ComboBox>("FullModelPicker")!;
            Require(picker.ItemCount == 18);
            picker.SelectedItem = f.Vm.Models.First(m => m.Id == "portable-unsloth-qwen35-2b-ud-q4-k-xl"); Dispatcher.UIThread.RunJobs();
            Require(f.Vm.SelectedModel?.Id == "portable-unsloth-qwen35-2b-ud-q4-k-xl" && !f.Vm.AutomaticModel);
        });
        Run("UI05-real-parser-results-clear-on-edit", f =>
        {
            f.Writing(); f.Vm.StudentText = "I am a student."; f.Vm.ApplySession(Session(f)); Require(f.Vm.HasSession && f.Vm.ParseStatus.StartsWith("JSON válido"));
            f.Vm.StudentText = "I am a teacher."; Require(!f.Vm.HasResult && !f.Vm.HasSession && f.Vm.CorrectedText.Length == 0);
        });
        Run("UI06-json-warning-and-simulation-no-progress", f =>
        {
            f.Vm.NavigateCommand.Execute("lab"); f.Vm.SimulateCommand.Execute(null);
            Require(f.Vm.HasResult && !f.Vm.HasSession && f.Vm.Raw.Contains("SIMULACIÓN") && f.Vm.CourseProgress == "0 / 33");
            f.Vm.ReportError(new IOException("Synthetic native error")); Require(f.Vm.HasResult && !f.Vm.UsableResult && f.Vm.Feedback.Contains("Synthetic"));
        });
        Run("UI07-reconfiguration-disables-old-loaded-model", f =>
        {
            Pump(f.Data.PrepareAsync()); f.Writing(); f.Vm.SelectedModel = f.Data.Model; f.Vm.SelectedBackend = f.Vm.BackendChoices.First(b => b.Value == BackendPreference.Cpu); f.Vm.StudentText = "I am a student.";
            Require(f.Vm.CanEvaluate); f.Vm.Context = 4096; Require(!f.Vm.CanEvaluate && f.Vm.NeedsModel);
        });
        Run("UI18-unload-disables-itself-and-keeps-model-file", f =>
        {
            Pump(f.Data.PrepareAsync()); f.Vm.SelectedModel = f.Data.Model;
            f.Vm.SelectedBackend = f.Vm.BackendChoices.First(b => b.Value == BackendPreference.Cpu);
            Require(f.Vm.ModelReady && f.Vm.UnloadCommand.CanExecute(null));
            f.Vm.UnloadCommand.Execute(null); WaitUntil(() => f.Data.Runtime.State is null); Layout(f.Window);
            Require(!f.Vm.ModelReady && !f.Vm.UnloadCommand.CanExecute(null) && f.Vm.PrepareCommand.CanExecute(null));
            Require(f.Data.Models.FindExisting(f.Data.Model) is not null && f.Data.Engine.Generations == 0);
        });
        Run("UI19-display-stays-awake-only-during-native-work", f =>
        {
            f.Vm.SelectedModel = f.Data.Model; f.Vm.SelectedBackend = f.Vm.BackendChoices.First(b => b.Value == BackendPreference.Cpu);
            var load = new TaskCompletionSource(); var generate = new TaskCompletionSource();
            try
            {
                f.Data.Engine.LoadGate = load.Task; f.Vm.PrepareCommand.Execute(null);
                WaitUntil(() => f.Data.Engine.Loads == 1); Require(f.Vm.IsBusy && f.Vm.KeepsDisplayAwake);
                load.SetResult(); WaitUntil(() => !f.Vm.IsBusy && f.Vm.PrepareCommand.CanExecute(null));
                Require(f.Vm.ModelReady && !f.Vm.KeepsDisplayAwake);
                f.Writing(); f.Vm.StudentText = "I am a student."; f.Data.Engine.GenerationGate = generate.Task;
                f.Vm.EvaluateCommand.Execute(null); WaitUntil(() => f.Data.Engine.Generations == 1);
                Require(f.Vm.IsBusy && f.Vm.KeepsDisplayAwake);
                generate.SetResult(); WaitUntil(() => !f.Vm.IsBusy && f.Vm.EvaluateCommand.CanExecute(null));
                Require(f.Vm.UsableResult && !f.Vm.KeepsDisplayAwake);
            }
            finally { load.TrySetResult(); generate.TrySetResult(); }
        });
        Run("UI20-download-action-does-not-hold-the-display", f =>
        {
            f.Vm.SelectedModel = f.Data.Model;
            var awake = new List<bool>();
            f.Vm.PropertyChanged += (_, e) => { if (e.PropertyName == nameof(CourseViewModel.KeepsDisplayAwake)) awake.Add(f.Vm.KeepsDisplayAwake); };
            f.Vm.DownloadCommand.Execute(null); WaitUntil(() => !f.Vm.IsBusy && f.Vm.DownloadCommand.CanExecute(null));
            Require(!f.Vm.KeepsDisplayAwake && !awake.Contains(true) && f.Data.Engine.Loads == 0 && f.Data.Engine.Generations == 0);
        });
        Run("UI08-responsive-portrait-landscape-and-wide", f =>
        {
            foreach (var (width, height) in new[] { (360, 800), (480, 900), (800, 480), (1320, 900) })
            {
                f.Window.Width = width; f.Window.Height = height; Layout(f.Window); f.View.Adapt(); Layout(f.Window);
                Require(f.Vm.Compact == (width < 760));
                Require(f.View.FindControl<Border>("BottomNavigation")!.IsVisible == (width < 760));
                var scroll = f.View.FindControl<ScrollViewer>("PageScroll")!;
                Require(scroll.Extent.Width <= scroll.Viewport.Width + 1, $"Horizontal overflow at {width}: {scroll.Extent.Width}/{scroll.Viewport.Width}");
                f.Writing(); Layout(f.Window);
                var result = f.View.FindControl<Border>("WritingResult")!; Require(Grid.GetRow(result) == (width >= 1100 ? 0 : 1));
                f.Vm.NavigateCommand.Execute("course");
            }
        });
        Run("UI12-android-view-recreation-preserves-live-state", f =>
        {
            f.Writing(); f.Vm.StudentText = "I am a student.";
            var model = f.Vm.Models.First(m => m.Id.Contains("qwen35-2b-q8")); f.Vm.SelectedModel = model;
            var first = f.Vm.InitializeAsync(); var recreated = new MainView(f.Vm);
            f.Window.Content = recreated; Layout(f.Window); Pump(f.Vm.InitializeAsync());
            Require(ReferenceEquals(first, f.Vm.InitializeAsync()) && f.Vm.SelectedModel == model && f.Vm.StudentText == "I am a student.");
            Require(f.Vm.FileRequested is not null);
        });
        Run("UI13-platform-back-retains-writing-draft", f =>
        {
            f.Writing(); f.Vm.StudentText = "I am a student.";
            var back = new Avalonia.Interactivity.RoutedEventArgs(TopLevel.BackRequestedEvent);
            f.View.RaiseEvent(back); Require(back.Handled && f.Vm.ShowLesson);
            Require(f.Vm.GoBack() && f.Vm.HomePage && !f.Vm.GoBack());
            f.Writing(); Require(f.Vm.StudentText == "I am a student.");
        });
        Run("UI14-software-keyboard-keeps-editor-visible-without-double-insets", f =>
        {
            f.Window.Width = 480; f.Window.Height = 900; f.Writing(); Layout(f.Window);
            var input = f.View.FindControl<TextBox>("WritingAnswer")!; input.Focus();
            f.View.ApplyInputPane(true, new Rect(0, 600, 480, 300)); Layout(f.Window);
            var shell = f.View.FindControl<Grid>("Shell")!;
            Require(shell.Bounds.Bottom <= 601 && shell.Margin.Bottom == 300);
            f.Window.Height = 550; Layout(f.Window); f.View.ApplyInputPane(true, new Rect(0, 600, 480, 300)); Layout(f.Window);
            Require(shell.Margin.Bottom == 0, "Window was already resized: keyboard space was subtracted twice.");
            f.View.ApplyInputPane(false, default); Require(shell.Margin.Bottom == 0);
        });
        Run("UI15-manual-model-persists-after-startup-and-backup-restore", f =>
        {
            foreach (var id in new[] { "09-lfm25-12b-q4-k-m", f.Vm.Models.First(m => m.Id.Contains("qwen35-2b-q8")).Id })
            {
                f.Vm.SelectedModel = f.Vm.Models.First(m => m.Id == id); Pump(f.Vm.FlushDraftsAsync());
                using var backup = new MemoryStream(); Pump(f.Vm.ExportBackupAsync(backup));
                var restarted = new CourseViewModel(new EmbeddedCourse(), f.Data.Store, f.Data.Runtime);
                f.Window.Content = new MainView(restarted); Pump(restarted.InitializeAsync()); Layout(f.Window);
                Require(restarted.SelectedModel?.Id == id && !restarted.AutomaticModel, $"Restart changed {id} to {restarted.SelectedModel?.Id}.");
                backup.Position = 0; Pump(restarted.RestoreAsync(backup)); Layout(f.Window);
                Require(restarted.SelectedModel?.Id == id && !restarted.AutomaticModel, $"Restore changed {id} to {restarted.SelectedModel?.Id}.");
                f.Window.Content = f.View; Layout(f.Window);
            }
        });
        Run("UI09-larger-writing-text-and-keyboard-focus", f =>
        {
            f.Window.Width = 480; f.Window.FontSize = 28; f.Writing(); Layout(f.Window);
            var text = f.View.FindControl<TextBox>("WritingAnswer")!; text.FontSize = 32; Layout(f.Window); text.Focus();
            f.Window.KeyTextInput("I am a student."); Dispatcher.UIThread.RunJobs();
            Require(f.Vm.StudentText == "I am a student.");
        });
        Run("UI10-render-home-and-writing-evidence", f =>
        {
            var output = _screenshots;
            Capture(f.Window, Path.Combine(output, "home-wide.png"));
            f.Window.Width = 480; f.Window.Height = 900; Layout(f.Window); Capture(f.Window, Path.Combine(output, "home-portrait.png"));
            f.Writing(); f.Vm.StudentText = "I am a student."; f.Vm.ApplySession(Session(f));
            f.Window.Width = 1320; f.Window.Height = 900; Layout(f.Window); Capture(f.Window, Path.Combine(output, "writing-wide.png"));
        });
        Run("UI16-home-summary-fits-width-and-enlarged-text", f =>
        {
            Require(f.Vm.ClosedAccuracy == "—" && f.Vm.ClosedAccuracyDetail == "Aún no has comprobado ejercicios.");
            var summary = f.View.FindControl<Grid>("SummaryMetrics")!;
            var fonts = summary.GetVisualDescendants().OfType<TextBlock>().Where(t => t.IsEffectivelyVisible).ToDictionary(t => t, t => t.FontSize);
            foreach (var scale in new[] { 1d, 1.5d })
            {
                foreach (var (text, font) in fonts) text.FontSize = font * scale;
                foreach (var width in new[] { 360, 385, 411, 480, 800, 1140, 1160, 1320 })
                {
                    f.Window.Width = width; f.Window.Height = 900; Layout(f.Window);
                    AssertSummary(f);
                    if (width == 385)
                    {
                        ScrollToSummary(f);
                        Capture(f.Window, Path.Combine(_screenshots, scale == 1 ? "summary-empty-portrait.png" : "summary-enlarged-portrait.png"));
                    }
                }
            }
            Require(f.Data.Engine.Generations == 0);
        });
        Run("UI17-home-summary-preserves-latest-attempt-metrics", f =>
        {
            var activities = f.Vm.Units.SelectMany(u => u.Unit.Activities).Where(a => !a.IsWriting).ToArray();
            foreach (var activity in activities.Take(2)) Pump(f.Data.Store.SaveClosedAsync(activity, activity.Answer!, ClosedExercise.Check(activity, activity.Answer!)));
            var first = activities[0]; var wrong = first.Options!.First(o => o.Id != first.Answer).Id;
            Pump(f.Data.Store.SaveClosedAsync(first, wrong, ClosedExercise.Check(first, wrong)));
            Pump(f.Vm.RefreshSnapshotAsync()); Layout(f.Window);
            Require(f.Vm.ClosedAccuracy == "50 %" && f.Vm.ClosedAccuracyDetail == "1 de 2 · último intento por ejercicio" && f.Vm.CourseProgress == "2 / 33");
            f.Window.Width = 385; Layout(f.Window); AssertSummary(f); ScrollToSummary(f);
            Capture(f.Window, Path.Combine(_screenshots, "summary-progress-portrait.png"));
            foreach (var activity in activities) Pump(f.Data.Store.SaveClosedAsync(activity, activity.Answer!, ClosedExercise.Check(activity, activity.Answer!)));
            Pump(f.Vm.RefreshSnapshotAsync()); Layout(f.Window);
            Require(f.Vm.ClosedAccuracy == "100 %" && f.Vm.ClosedAccuracyDetail == "30 de 30 · último intento por ejercicio");
            foreach (var width in new[] { 360, 385, 800, 1160, 1320 })
            {
                f.Window.Width = width; Layout(f.Window); AssertSummary(f);
                if (width == 385 || width == 1320)
                {
                    ScrollToSummary(f); Capture(f.Window, Path.Combine(_screenshots, $"summary-practiced-{width}.png"));
                }
            }
            Require(f.Data.Engine.Generations == 0);
        });
        Run("UI11-inconsistent-output-displays-warning-without-verdict", f =>
        {
            f.Writing(); f.Vm.StudentText = "I am a student.";
            var session = Session(f); var output = session.Attempts[0].Output with { Content = FakeEngine.CorrectRaw.Replace("\"is_correct\":true", "\"is_correct\":false") };
            var attempt = new EvaluationAttempt(1, 42, output, FeedbackParser.Parse(output.Content, "I am a student."));
            f.Vm.ApplySession(session with { Attempts = [attempt], Usable = false });
            Require(f.Vm.HasResult && f.Vm.HasSession && !f.Vm.UsableResult && f.Vm.CorrectedText.Length == 0 && f.Vm.ParseStatus.Contains("INCONSISTENT") && !f.Vm.Verdict.StartsWith("✓"));
        });
        var reportIndex = Array.IndexOf(args, "--report");
        if (reportIndex >= 0 && reportIndex + 1 < args.Length)
        {
            var path = Path.GetFullPath(args[reportIndex + 1]); Directory.CreateDirectory(Path.GetDirectoryName(path)!);
            using var file = File.Create(path); using var writer = new Utf8JsonWriter(file, new() { Indented = true });
            writer.WriteStartObject(); writer.WriteString("kind", "AVALONIA_HEADLESS_REAL_CONTROLS_WITH_SYNTHETIC_ENGINE"); writer.WriteString("dateUtc", DateTimeOffset.UtcNow);
            writer.WriteNumber("passed", Evidence.Count - _failed); writer.WriteNumber("total", Evidence.Count); writer.WritePropertyName("checks"); writer.WriteStartArray();
            foreach (var e in Evidence) { writer.WriteStartObject(); writer.WriteString("id", e.Id); writer.WriteBoolean("passed", e.Error is null); writer.WriteString("error", e.Error); writer.WriteEndObject(); }
            writer.WriteEndArray(); writer.WriteEndObject();
        }
        Pump(initial.DisposeAsync().AsTask()); Console.WriteLine($"{Evidence.Count - _failed}/{Evidence.Count} UI checks passed."); return _failed == 0 ? 0 : 1;
    }
    private static void Run(string id, Action<UiFixture> check)
    {
        using var f = new UiFixture();
        try { check(f); Evidence.Add((id, null)); Console.WriteLine("PASS " + id); }
        catch (Exception error) { Evidence.Add((id, error.ToString())); _failed++; Console.WriteLine($"FAIL {id}: {error}"); }
    }
    internal static void Pump(Task task) { WaitUntil(() => task.IsCompleted); task.GetAwaiter().GetResult(); }
    private static void WaitUntil(Func<bool> condition)
    {
        var deadline = DateTime.UtcNow.AddSeconds(30);
        while (!condition()) { Dispatcher.UIThread.RunJobs(); if (DateTime.UtcNow > deadline) throw new TimeoutException("UI test did not complete"); Thread.Sleep(5); }
        Dispatcher.UIThread.RunJobs();
    }
    private static void Layout(Window window) { Dispatcher.UIThread.RunJobs(); window.UpdateLayout(); }
    private static void ScrollToSummary(UiFixture f)
    {
        var summary = f.View.FindControl<Grid>("SummaryMetrics")!;
        var point = summary.TranslatePoint(default, f.View.FindControl<StackPanel>("PageBody")!)!.Value;
        f.View.FindControl<ScrollViewer>("PageScroll")!.Offset = new Vector(0, Math.Max(0, point.Y - 12)); Layout(f.Window);
    }
    private static void AssertSummary(UiFixture f)
    {
        var summary = f.View.FindControl<Grid>("SummaryMetrics")!;
        var cards = new[] { "PracticeSummary", "AccuracySummary", "WritingSummary" }.Select(n => f.View.FindControl<Border>(n)!).ToArray();
        foreach (var card in cards)
        {
            Require(card.Bounds.X >= 0 && card.Bounds.Right <= summary.Bounds.Width + 1 && card.Bounds.Bottom <= summary.Bounds.Height + 1, $"{card.Name} escapes summary at window width {f.Window.Width}.");
            foreach (var text in card.GetVisualDescendants().OfType<TextBlock>().Where(t => t.IsEffectivelyVisible))
            {
                var point = text.TranslatePoint(default, card)!.Value;
                Require(point.X >= 0 && point.Y >= 0 && point.X + text.Bounds.Width <= card.Bounds.Width + 1 && point.Y + text.Bounds.Height <= card.Bounds.Height + 1, $"{text.Name} escapes {card.Name}.");
                Require(text.TextLayout.Height <= text.Bounds.Height + 1 && text.TextLayout.Width <= text.Bounds.Width + 1, $"{text.Name} ({text.Text}) text is clipped at window width {f.Window.Width}: layout {text.TextLayout.Width}x{text.TextLayout.Height}, bounds {text.Bounds.Size}.");
            }
        }
        for (var i = 0; i < cards.Length; i++)
            for (var j = i + 1; j < cards.Length; j++) Require(!cards[i].Bounds.Intersects(cards[j].Bounds), "Summary cards overlap.");
        var label = f.View.FindControl<TextBlock>("AccuracyLabel")!;
        var detail = f.View.FindControl<TextBlock>("AccuracyDetail")!;
        Require(label.Bounds.Bottom <= detail.Bounds.Top, "Accuracy detail overlaps its label.");
        var bar = f.View.FindControl<ProgressBar>("CourseProgressBar")!;
        var barPoint = bar.TranslatePoint(default, cards[0])!.Value;
        Require(bar.ClipToBounds && bar.Bounds.Width > 0 && barPoint.X >= 0 && barPoint.X + bar.Bounds.Width <= cards[0].Bounds.Width + 1, "Progress track escapes its card.");
        var stacked = summary.Bounds.Width < 900;
        Require(Grid.GetRow(cards[1]) == (stacked ? 1 : 0) && Grid.GetColumn(cards[1]) == (stacked ? 0 : 1), "Summary did not adapt to actual content width.");
    }
    private static void Capture(Window window, string path)
    {
        Layout(window); using var bitmap = new RenderTargetBitmap(new((int)window.Bounds.Width, (int)window.Bounds.Height), new(96, 96)); bitmap.Render(window); bitmap.Save(path, PngBitmapEncoderOptions.Default);
    }
    private static ReviewSession Session(UiFixture f)
    {
        var output = new EngineOutput(FakeEngine.CorrectRaw, "stop", .5);
        var attempt = new EvaluationAttempt(1, 42, output, FeedbackParser.Parse(output.Content, "I am a student."));
        return new("writing_course/1.0", "SYNTHETIC_UI_TEST", DateTimeOffset.UtcNow, f.Data.Model, f.Data.Services.Device,
            new(BackendPreference.Cpu, "CPU", null, 0, null, 2048), "u01-writing-01", "A1", "Introduce yourself", "I am a student.", "synthetic", 1, [attempt], true, "usable_envelope");
    }
    private static void Require(bool condition, string? reason = null) { if (!condition) throw new Exception(reason ?? "Assertion failed"); }
    private sealed class UiFixture : IDisposable
    {
        public Fixture Data { get; } = new();
        public CourseViewModel Vm { get; }
        public MainView View { get; }
        public Window Window { get; }
        public UiFixture()
        {
            Vm = new(new EmbeddedCourse(), Data.Store, Data.Runtime); View = new(Vm, initialize: false);
            Window = new() { Width = 1320, Height = 900, Content = View }; Window.Show(); Pump(Vm.InitializeAsync()); Layout(Window);
        }
        public void Writing() { Vm.OpenUnit(Vm.Units[0]); Vm.OpenActivity(Vm.Units[0].Unit.Activities.Last()); Layout(Window); }
        public void Dispose() { Window.Close(); Pump(Vm.DisposeAsync().AsTask()); Pump(Data.DisposeAsync().AsTask()); }
    }
}
