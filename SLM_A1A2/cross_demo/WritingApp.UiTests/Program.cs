using WritingApp.Shared;
using WritingApp.UI;
using WritingDemo.Core;

var checks = new (string Name, Action Run)[]
{
    ("clears a correct result after each editable evaluation input changes", InvalidatesOldResult),
    ("shows inconsistent and invalid JSON as warnings", ShowsWarnings),
    ("keeps RAW for every attempt in the visible session history", KeepsRawHistory),
    ("overwrites an existing seekable export stream without leaving its old tail", TruncatesOldExportStream)
};

var failures = 0;
foreach (var (name, run) in checks)
{
    try
    {
        run();
        Console.WriteLine("PASS " + name);
    }
    catch (Exception exception)
    {
        failures++;
        Console.WriteLine($"FAIL {name}: {exception}");
    }
}

Console.WriteLine($"{checks.Length - failures}/{checks.Length} UI state checks passed.");
return failures == 0 ? 0 : 1;

static void InvalidatesOldResult()
{
    var mutations = new (string Name, Action<MainWindowViewModel> Apply)[]
    {
        ("student text", vm => vm.StudentText = "I eat lunch at home."),
        ("task text", vm => vm.TaskText = "Write about a different day."),
        ("model", vm => vm.SelectedModel = vm.Models.First(model => model.Id != vm.SelectedModel!.Id)),
        ("backend", vm => vm.SelectedBackend = vm.BackendChoices.First(choice => choice.Preference != vm.SelectedBackend.Preference)),
        ("level", vm => vm.SelectedLevel = "A2"),
        ("attempt limit", vm => vm.MaximumAttempts = 2)
    };

    foreach (var (name, mutation) in mutations)
    {
        using var fixture = new UiFixture();
        var vm = fixture.ViewModel;
        vm.StudentText = "I wake up at seven.";
        vm.ApplySession(CreateSession(fixture, [CreateValidAttempt(vm)], usable: true));

        Require(vm.LastSession is not null && vm.CanExport, $"baseline session was not displayed before changing {name}");
        Require(vm.VerdictText.StartsWith("✓", StringComparison.Ordinal), $"baseline correct verdict missing before changing {name}");

        mutation(vm);

        Require(vm.LastSession is null && !vm.CanExport, $"old session survived {name} change");
        Require(!vm.VerdictText.Contains('✓') && !vm.VerdictText.Contains('✕'), $"a definitive old verdict survived {name} change");
        Require(vm.CorrectedText.Length == 0 && vm.FeedbackText.Length == 0 && vm.EditsText.Length == 0,
            $"old feedback survived {name} change");
        Require(vm.RawAttempts.Length == 0, $"old RAW remained associated with the new input after {name} change");
    }
}

static void ShowsWarnings()
{
    using var fixture = new UiFixture();
    var vm = fixture.ViewModel;
    vm.StudentText = "I wake up at seven.";

    var inconsistentRaw = "{inconsistent-output}";
    var inconsistentValue = new ParsedFeedback(true, "I wake up at seven.", Array.Empty<FeedbackEdit>(), "");
    var inconsistentParsed = new FeedbackParseResult("INCONSISTENT", inconsistentValue,
        "is_correct contradicts the fields", inconsistentRaw, null);
    vm.ApplySession(CreateSession(fixture, [CreateAttempt(1, inconsistentRaw, inconsistentParsed)], usable: false));
    RequireWarning(vm, "INCONSISTENT");
    Require(vm.RawAttempts.Contains(inconsistentRaw, StringComparison.Ordinal), "inconsistent RAW was not shown");

    var invalidRaw = "this is not JSON";
    var invalidParsed = new FeedbackParseResult("INVALID_JSON", null,
        "No se encontró un objeto JSON completo.", invalidRaw, null);
    vm.ApplySession(CreateSession(fixture, [CreateAttempt(1, invalidRaw, invalidParsed)], usable: false));
    RequireWarning(vm, "INVALID_JSON");
    Require(vm.RawAttempts.Contains(invalidRaw, StringComparison.Ordinal), "invalid JSON RAW was not shown");
}

static void KeepsRawHistory()
{
    using var fixture = new UiFixture();
    var vm = fixture.ViewModel;
    vm.StudentText = "I wake up at seven.";
    var firstRaw = "first-attempt-invalid-json";
    var firstParsed = new FeedbackParseResult("INVALID_JSON", null, "incomplete JSON", firstRaw, null);
    var second = CreateValidAttempt(vm, number: 2, diagnostics: "second attempt fixture");
    var session = CreateSession(fixture,
        [CreateAttempt(1, firstRaw, firstParsed), second], usable: true);

    vm.ApplySession(session);

    Require(vm.LastSession is not null && vm.CanExport, "usable session was not retained");
    Require(vm.RawAttempts.Contains("INVALID_JSON", StringComparison.Ordinal)
            && vm.RawAttempts.Contains(firstRaw, StringComparison.Ordinal), "first failed attempt was hidden");
    Require(vm.RawAttempts.Contains("STRICT", StringComparison.Ordinal)
            && vm.RawAttempts.Contains(second.Output.Content, StringComparison.Ordinal), "later successful attempt was not shown");
    Require(vm.VerdictText.StartsWith("✓", StringComparison.Ordinal), "final usable model verdict was not shown");
}

static void TruncatesOldExportStream()
{
    const string previousSession = "old session content that is intentionally longer than the replacement JSON";
    const string newJson = "{\"ok\":true}";
    using var stream = new MemoryStream();
    var previousBytes = System.Text.Encoding.UTF8.GetBytes(previousSession);
    stream.Write(previousBytes, 0, previousBytes.Length);

    SessionExportWriter.WriteAsync(stream, System.Text.Encoding.UTF8.GetBytes(newJson)).GetAwaiter().GetResult();

    var result = System.Text.Encoding.UTF8.GetString(stream.ToArray());
    Require(result == newJson && stream.Length == System.Text.Encoding.UTF8.GetByteCount(newJson),
        "old session bytes remained after writing the shorter replacement");
}

static void RequireWarning(MainWindowViewModel vm, string status)
{
    Require(vm.VerdictText.Contains("Advertencia", StringComparison.Ordinal), $"{status} was not labeled as a warning");
    Require(!vm.VerdictText.Contains('✓') && !vm.VerdictText.Contains('✕'), $"{status} was shown as a definitive correct/error verdict");
    Require(vm.ParseStatusText.Length > 0, $"{status} parse details were missing");
}

static EvaluationAttempt CreateValidAttempt(MainWindowViewModel vm, int number = 1, string diagnostics = "fixture valid JSON")
{
    const string raw = "{\"is_correct\":true,\"corrected_text\":\"I wake up at seven.\",\"errors\":[],\"feedback\":\"\"}";
    var parsed = FeedbackParser.Parse(raw, vm.StudentText);
    Require(parsed.Status == "STRICT", "synthetic correct response did not parse strictly");
    return new EvaluationAttempt(number, 41 + number, new EngineOutput(raw, "stop", 0, diagnostics), parsed);
}

static EvaluationAttempt CreateAttempt(int number, string raw, FeedbackParseResult parsed) =>
    new(number, 41 + number, new EngineOutput(raw, "stop", 0, "fixture output"), parsed);

static ReviewSession CreateSession(UiFixture fixture, EvaluationAttempt[] attempts, bool usable)
{
    var vm = fixture.ViewModel;
    var exercise = vm.CreateCurrentExercise();
    return new ReviewSession(
        "writing-ui-fixture/1",
        "INTERACTIVE_DEMO_NOT_BENCHMARK",
        DateTimeOffset.UtcNow,
        vm.SelectedModel ?? throw new InvalidOperationException("View model has no selected model."),
        fixture.Services.Device,
        new EngineState(vm.SelectedBackend.Preference, "fixture backend", "fixture device", 0, null, fixture.Services.DefaultContext),
        exercise.Id,
        exercise.Level,
        exercise.Task,
        vm.StudentText,
        "fixture-prompt-hash",
        Math.Max(1, attempts.Length),
        attempts,
        usable,
        usable ? "usable_envelope" : "unusable_envelope");
}

static void Require(bool condition, string message)
{
    if (!condition) throw new InvalidOperationException(message);
}

sealed class UiFixture : IDisposable
{
    private readonly string _root = Path.Combine(Path.GetTempPath(), "writing-ui-fixture-" + Guid.NewGuid().ToString("N"));

    public UiFixture()
    {
        var modelStore = new ModelStore(Path.Combine(_root, "models"));
        Services = new AppServices(
            new DeviceProfile("Windows", "x64", 16L << 30, 8L << 30, 32L << 30),
            modelStore,
            new NoInferenceEngine(),
            new SessionStore(Path.Combine(_root, "sessions")));
        ViewModel = new MainWindowViewModel(Services);
    }

    public AppServices Services { get; }
    public MainWindowViewModel ViewModel { get; }

    public void Dispose()
    {
        Services.ModelStore.Dispose();
        if (Directory.Exists(_root)) Directory.Delete(_root, recursive: true);
    }
}

sealed class NoInferenceEngine : IInferenceEngine
{
    public Task<EngineState> LoadAsync(ModelEntry model, string modelPath, BackendPreference backend, int context, CancellationToken ct) =>
        throw new InvalidOperationException("UI state fixtures must not load a model.");

    public Task<EngineOutput> GenerateAsync(WritingExercise exercise, string studentText, int seed, CancellationToken ct) =>
        throw new InvalidOperationException("UI state fixtures must not generate a response.");

    public Task UnloadAsync() => throw new InvalidOperationException("UI state fixtures must not load a model.");

    public ValueTask DisposeAsync() => ValueTask.CompletedTask;
}
