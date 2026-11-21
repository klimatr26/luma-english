using System.Collections.ObjectModel;
using System.Globalization;
using System.Text.Json;
using Avalonia.Threading;
using Course.Core;
using WritingApp.Shared;
using WritingDemo.Core;

namespace Course.UI;

public enum FileAction { Backup, Restore, HistoryJson, HistoryCsv, ImportModel, SessionJson }
public sealed record BackendChoice(BackendPreference Value, string Label) { public override string ToString() => Label; }
public sealed record AdapterChoice(GpuPlan Plan)
{
    public override string ToString() => $"{Plan.Name} · {Plan.FreeBytes / 1073741824d:F1} GiB libres · hasta {Plan.EstimatedLayers}/{Plan.FullLayers} capas estimadas";
}
public sealed class UnitCard(CourseUnit unit, int number) : Observable
{
    public ActionCommand? OpenCommand { get; set; }
    private int _done;
    private double _width = 300;
    public CourseUnit Unit { get; } = unit;
    public string Id => Unit.Id;
    public string Number => number.ToString("00");
    public string Title => Unit.Title;
    public string Subtitle => Unit.Subtitle;
    public string Summary => Unit.Summary;
    public string Label => Unit.Label;
    public string Duration => $"≈ {Unit.Minutes} min · 11 actividades";
    public string Accent => number switch { 1 => "#E4EEE8", 2 => "#EEE9F8", _ => "#F6EBD8" };
    public int Done { get => _done; set { if (Set(ref _done, value)) Changed(nameof(ProgressLabel), nameof(ProgressValue), nameof(ActionLabel)); } }
    public string ProgressLabel => $"{Done}/11 practicadas";
    public double ProgressValue => Done / 11d * 100;
    public string ActionLabel => Done == 0 ? "Explorar unidad  →" : Done == 11 ? "Volver a practicar  →" : "Continuar unidad  →";
    public double Width { get => _width; set => Set(ref _width, value); }
}
public sealed record ActivityItem(CourseActivity Activity, int Index, bool Practiced)
{
    public ActionCommand? OpenCommand { get; set; }
    public string Label => $"{(Practiced ? "✓" : Index.ToString("00"))}  {Activity.TypeLabel}";
    public string Id => Activity.Id;
}
public sealed record LessonItem(LessonBlock Block)
{
    public string Text => Block.Text;
    public bool Heading => Block.Kind == "heading";
    public bool Paragraph => Block.Kind == "paragraph";
    public bool Bullet => Block.Kind == "bullet";
    public bool Example => Block.Kind == "example";
    public bool Table => Block.Kind == "table";
    public string[] Rows => Block.Rows.Skip(1).Select(row => string.Join("\n", row.Select((cell, i) => $"{Block.Rows[0][i]}: {cell}"))).ToArray();
}
public sealed record HistoryItem(HistoryEntry Entry, string Title, string Detail)
{
    public ActionCommand? OpenCommand { get; set; }
    public string Date => Entry.DateUtc.ToLocalTime().ToString("dd MMM · HH:mm", CultureInfo.GetCultureInfo("es-EC"));
    public string Kind => Entry.Kind switch { "closed" => "Práctica", "laboratory" => "Laboratorio", _ => "Writing" };
    public string Status => Entry.Status switch
    {
        "checked" => Entry.IsCorrect == true ? "Respuesta correcta" : "Respuesta por repasar",
        "usable" => Entry.IsCorrect == true ? "Correcto según el modelo" : "Revisar con retroalimentación",
        "unusable" => "JSON no utilizable", "cancelled" => "Cancelada", "technical_error" => "Problema técnico", _ => "Interrumpida"
    };
}

public sealed class CourseViewModel : Observable, IAsyncDisposable
{
    private readonly ICourseRepository _course;
    private readonly CourseStore _store;
    private readonly CourseRuntime _runtime;
    private readonly WritingPracticeService _writing;
    private CourseSettings _settings = new();
    private ProgressSnapshot _snapshot = new([], [], 0, 0, []);
    private readonly Dictionary<string, string> _drafts = new(StringComparer.Ordinal);
    private readonly HashSet<Task> _pendingDrafts = [];
    private readonly List<AsyncCommand> _asyncCommands = [];
    private CancellationTokenSource? _operation;
    private TaskCompletionSource? _idle;
    private string _page = "course";
    private UnitCard? _unit;
    private CourseActivity? _activity;
    private bool _lesson = true, _laboratory, _busy, _initializing = true, _automatic = true, _advanced;
    private string _student = "", _word = "", _status = "El curso está disponible sin conexión. Prepara la IA cuando llegues al Writing.";
    private ChoiceOption? _choice;
    private string _closedText = "", _closedHeading = "";
    private string _modelMessage = "La IA se prepara al llegar al primer Writing.", _advice = "Consultando el equipo…";
    private ModelEntry? _selectedModel;
    private BackendChoice _backend;
    private int _context = 2048, _maximumAttempts = 1;
    private double _transfer;
    private bool _transferIndeterminate;
    private AdapterChoice? _adapter;
    private string _layers = "";
    private ReviewSession? _result;
    private string _verdict = "Tu siguiente paso empieza aquí", _feedback = "", _corrected = "", _edits = "", _parse = "", _raw = "", _resultMetrics = "";
    private HistoryItem? _selectedHistory;
    private string _historyDetail = "";
    private string _labLevel = "A1", _labTask = "Write 2 to 4 sentences to introduce yourself. Say your name, where you are from and what you do.";
    private bool _compact, _warning;
    public Func<FileAction, Task>? FileRequested { get; set; }
    public CourseViewModel(ICourseRepository course, CourseStore store, CourseRuntime runtime)
    {
        _course = course; _store = store; _runtime = runtime; _writing = new(store, runtime);
        _backend = BackendChoices[0];
        Units = course.Course.Units.Select((u, i) => new UnitCard(u, i + 1)).ToArray();
        foreach (var unit in Units) unit.OpenCommand = new(_ => OpenUnit(unit));
        _selectedModel = Models.First(m => m.Id == BalancedModelAdvisor.GemmaId);
        _runtime.StatusChanged += RuntimeProgress;
        _runtime.EngineStarting += EngineStarting;
        NavigateCommand = new(p => Navigate(p as string ?? "course"));
        OpenUnitCommand = new(p => { if (p is UnitCard card) OpenUnit(card); });
        OpenActivityCommand = new(p => { if (p is ActivityItem item) OpenActivity(item.Activity); });
        LessonCommand = new(_ => { _lesson = true; ClearResult(); RefreshView(); });
        PracticeCommand = new(_ => StartPractice());
        ContinueCommand = new(_ => Continue());
        NextCommand = new(_ => Next());
        CheckCommand = Async(_ => CheckAsync(), () => !_busy && _activity is { IsWriting: false });
        PrepareCommand = Async(_ => PrepareAsync(download: true), () => !_busy && _selectedModel is not null);
        DownloadCommand = Async(_ => DownloadAsync(), () => !_busy && _selectedModel is { } m && (m.DownloadUrl is not null || _runtime.Services.ModelStore.FindExisting(m) is not null));
        EvaluateCommand = Async(_ => EvaluateAsync(), () => CanEvaluate);
        CancelCommand = new(_ => { _operation?.Cancel(); Status = "Cancelando la operación…"; });
        UnloadCommand = Async(async _ => { await _runtime.UnloadAsync(); _modelMessage = "Modelo liberado. Tus archivos siguen en el dispositivo."; RefreshModel(); }, () => !_busy && _runtime.State is not null);
        RecommendCommand = Async(async _ => { AutomaticModel = true; await RefreshAdviceAsync(); }, () => !_busy);
        InspectCommand = Async(_ => InspectAsync(), () => !_busy);
        RecalibrateCommand = Async(async _ =>
        {
            await WithOperation(async ct => { await _runtime.RecalibrateAsync(SelectedModel!, Context, ct); ModelMessage = "Perfil anterior archivado. Pulsa Preparar para repetir la medición."; });
            RefreshModel();
        }, () => !_busy && _selectedModel is not null);
        FileCommand = Async(async p => { if (p is string action && Enum.TryParse<FileAction>(action, out var file) && FileRequested is not null) await FileRequested(file); }, () => !_busy);
        CorrectExampleCommand = new(_ => SetExample(true));
        IncorrectExampleCommand = new(_ => SetExample(false));
        SimulateCommand = new(_ => SimulateInvalid(), () => !_busy);
        HistoryCommand = new(p => { if (p is HistoryItem item) ShowHistory(item); });
    }
    private AsyncCommand Async(Func<object?, Task> action, Func<bool>? can = null)
    { var command = new AsyncCommand(action, ReportError, can); _asyncCommands.Add(command); return command; }
    public ActionCommand NavigateCommand { get; }
    public ActionCommand OpenUnitCommand { get; }
    public ActionCommand OpenActivityCommand { get; }
    public ActionCommand LessonCommand { get; }
    public ActionCommand PracticeCommand { get; }
    public ActionCommand ContinueCommand { get; }
    public ActionCommand NextCommand { get; }
    public ActionCommand CancelCommand { get; }
    public ActionCommand CorrectExampleCommand { get; }
    public ActionCommand IncorrectExampleCommand { get; }
    public ActionCommand SimulateCommand { get; }
    public ActionCommand HistoryCommand { get; }
    public AsyncCommand CheckCommand { get; }
    public AsyncCommand PrepareCommand { get; }
    public AsyncCommand DownloadCommand { get; }
    public AsyncCommand EvaluateCommand { get; }
    public AsyncCommand UnloadCommand { get; }
    public AsyncCommand RecommendCommand { get; }
    public AsyncCommand InspectCommand { get; }
    public AsyncCommand RecalibrateCommand { get; }
    public AsyncCommand FileCommand { get; }
    public UnitCard[] Units { get; }
    public IReadOnlyList<ModelEntry> Models => _runtime.Models;
    public IReadOnlyList<ModelEntry> RecommendedModels => Models.Where(m => m.Id == _selectedModel?.Id || m.Id is BalancedModelAdvisor.GemmaId or BalancedModelAdvisor.MiniId or BalancedModelAdvisor.LfmId or "portable-unsloth-qwen35-4b-q4-k-m" or "11-qwen35-4b-q4-k-m").ToArray();
    public IReadOnlyList<BackendChoice> BackendChoices { get; } = new BackendChoice[] { new(BackendPreference.AutoVulkanCpu, "Automático · Vulkan / CPU"), new(BackendPreference.Cpu, "CPU"), new(BackendPreference.Vulkan, "Vulkan") };
    public int[] ContextChoices { get; } = [2048, 4096];
    public int[] AttemptChoices { get; } = [1, 2, 3];
    public string[] Levels { get; } = ["A1", "A2"];
    public ObservableCollection<AdapterChoice> Adapters { get; } = [];
    public ObservableCollection<HistoryItem> History { get; } = [];
    public ActivityItem[] ActivityItems => _unit?.Unit.Activities.Select((a, i) => new ActivityItem(a, i + 1, _snapshot.Practiced.Contains(a.Id)) { OpenCommand = new(_ => OpenActivity(a)) }).ToArray() ?? [];
    public LessonItem[] Lessons => _unit?.Unit.Lessons.Select(b => new LessonItem(b)).ToArray() ?? [];
    public bool HomePage => _page == "course" && _unit is null;
    public bool UnitPage => _page == "course" && _unit is not null;
    public bool HistoryPage => _page == "history";
    public bool ModelsPage => _page == "models";
    public bool LabPage => _page == "lab";
    public bool ShowLesson => UnitPage && _lesson;
    public bool ShowActivity => UnitPage && !_lesson;
    public bool ShowClosed => ShowActivity && _activity is { IsWriting: false };
    public bool ShowWriting => ShowActivity && _activity?.IsWriting == true || LabPage;
    public bool ShowOptions => ShowClosed && _activity?.Type == "single_choice";
    public bool ShowWord => ShowClosed && _activity?.Type == "one_word";
    public bool HasClosedFeedback => _closedText.Length > 0;
    public bool HasHistory => History.Count > 0;
    public bool EmptyHistory => !HasHistory;
    public bool HasHistoryDetail => _selectedHistory is not null;
    public bool HasResult => _raw.Length > 0 || _warning;
    public bool HasSession => _result is not null;
    public bool EmptyResult => !HasResult;
    public bool UsableResult => _result?.Usable == true;
    public bool IsBusy => _busy;
    private bool _keepsDisplayAwake;
    public bool KeepsDisplayAwake { get => _keepsDisplayAwake; private set => Set(ref _keepsDisplayAwake, value); }
    public bool CanEdit => !_busy && !_initializing;
    public bool CanEvaluate => CanEdit && ModelReady && !string.IsNullOrWhiteSpace(StudentText);
    public bool ModelReady => _runtime.State is { } state && _runtime.LoadedModel?.Id == SelectedModel?.Id &&
        state.ContextTokens == Context && state.Requested == _backend.Value &&
        (_backend.Value != BackendPreference.Vulkan || (_adapter?.Plan.Id ?? _settings.AdapterId) is not { } requestedAdapter || requestedAdapter == state.AdapterId) &&
        (string.IsNullOrWhiteSpace(_layers) || int.TryParse(_layers, out var layers) && layers == state.OffloadedLayers && (_adapter?.Plan.Id ?? _settings.AdapterId) == state.AdapterId);
    public bool NeedsModel => !ModelReady;
    public bool Compact { get => _compact; set { if (Set(ref _compact, value)) Changed(nameof(HeroArtVisible)); } }
    public bool HeroArtVisible => !Compact;
    public string PageTitle => _page switch { "history" => "Tu recorrido", "models" => "Tu IA, en este equipo", "lab" => "Laboratorio de Writing", _ => _unit?.Title ?? "Un poco de práctica. Mucho por decir." };
    public string PageSubtitle => _page switch { "history" => "Vuelve a tus respuestas y observa lo que has practicado.", "models" => "Una recomendación sencilla. Todo el control cuando lo necesitas.", "lab" => "Explora la evaluación y su JSON. Esta sección no cambia tu progreso.", _ => _unit?.Summary ?? "Inglés A1 para expresarte en situaciones cotidianas." };
    public string CourseProgress => $"{Units.Sum(u => u.Done)} / 33";
    public double CourseProgressValue => Units.Sum(u => u.Done) / 33d * 100;
    public string ClosedAccuracy => _snapshot.ClosedPracticed == 0 ? "—" : $"{Math.Round(_snapshot.ClosedCorrect * 100d / _snapshot.ClosedPracticed)} %";
    public string ClosedAccuracyDetail => _snapshot.ClosedPracticed == 0
        ? "Aún no has comprobado ejercicios."
        : $"{_snapshot.ClosedCorrect} de {_snapshot.ClosedPracticed} · último intento por ejercicio";
    public string WritingCount => $"{_course.Course.Units.SelectMany(u => u.Activities).Count(a => a.IsWriting && _snapshot.Practiced.Contains(a.Id))} / 3";
    public string UnitTitle => _unit?.Title ?? "";
    public string UnitSubtitle => _unit?.Subtitle ?? "";
    public string UnitProgress => _unit?.ProgressLabel ?? "";
    public string ActivityNumber => _activity is null || _unit is null ? "" : $"ACTIVIDAD {Array.IndexOf(_unit.Unit.Activities, _activity) + 1:00} / 11";
    public string ActivityType => _activity?.TypeLabel ?? "Writing libre";
    public string Prompt => _activity?.Prompt ?? LabTask;
    public ChoiceOption[] Options => _activity?.Options ?? [];
    public string ClosedText => _closedText;
    public string ClosedHeading => _closedHeading;
    public string WordAnswer { get => _word; set { if (Set(ref _word, value)) ClearClosed(); } }
    public ChoiceOption? SelectedChoice { get => _choice; set { if (Set(ref _choice, value)) ClearClosed(); } }
    private string DraftKey => LabPage ? "laboratory-draft" : _activity?.Id ?? "";
    public string StudentText
    {
        get => _student;
        set
        {
            if (!Set(ref _student, value)) return;
            ClearResult();
            var key = DraftKey;
            if (key.Length > 0)
            {
                _drafts[key] = value;
                TrackDraft(_store.SaveDraftAsync(key, value));
            }
            Changed(nameof(CharacterCount)); RefreshCommands();
        }
    }
    public string CharacterCount => $"{StudentText.Length}/4000 caracteres · borrador local";
    public string LabTask { get => _labTask; set { if (Set(ref _labTask, value)) { ClearResult(); Changed(nameof(Prompt)); } } }
    public string LabLevel { get => _labLevel; set { if (Set(ref _labLevel, value)) ClearResult(); } }
    public bool AutomaticModel
    {
        get => _automatic;
        set { if (Set(ref _automatic, value) && !_initializing) { SavePreferences(); if (value) _ = RefreshAdviceSafelyAsync(); } }
    }
    public bool Advanced { get => _advanced; set => Set(ref _advanced, value); }
    public ModelEntry? SelectedModel
    {
        get => _selectedModel;
        set
        {
            if (value is null || !Set(ref _selectedModel, value)) return;
            ClearResult();
            if (!_initializing) { _automatic = false; Changed(nameof(AutomaticModel)); SavePreferences(); }
            RefreshModel();
        }
    }
    private void SelectModelAutomatically(ModelEntry model)
    { _selectedModel = model; Changed(nameof(SelectedModel)); RefreshModel(); }
    public BackendChoice SelectedBackend
    {
        get => _backend;
        set
        {
            if (value is null || !Set(ref _backend, value)) return;
            ClearResult(); _adapter = null; _layers = ""; _settings = _settings with { AdapterId = null, GpuLayers = null };
            Changed(nameof(SelectedAdapter), nameof(ManualLayers));
            if (_automatic && !_initializing)
            {
                var advice = new BalancedModelAdvisor().Recommend(Models, _runtime.Device, _runtime.Hardware, CurrentSettings(), m => _runtime.Services.ModelStore.FindExisting(m) is not null);
                SelectModelAutomatically(advice.Model); Recommendation = advice.Reason;
            }
            SavePreferences(); RefreshModel();
        }
    }
    public int Context { get => _context; set { if (Set(ref _context, value)) { ClearResult(); SavePreferences(); RefreshModel(); } } }
    public int MaximumAttempts { get => _maximumAttempts; set { if (Set(ref _maximumAttempts, value)) { ClearResult(); SavePreferences(); } } }
    public AdapterChoice? SelectedAdapter { get => _adapter; set { if (Set(ref _adapter, value)) { ClearResult(); SavePreferences(); } } }
    public string ManualLayers { get => _layers; set { if (Set(ref _layers, value)) { ClearResult(); SavePreferences(); } } }
    public string SelectedModelName => SelectedModel is null ? "Selecciona un modelo" : $"{SelectedModel.Name} · {SelectedModel.Quantization}";
    public string PrepareLabel => SelectedModel is null ? "Preparar IA" : _runtime.Services.ModelStore.FindExisting(SelectedModel) is null
        ? SelectedModel.DownloadUrl is null ? "Importar este GGUF…" : $"Descargar y preparar · {SelectedModel.SizeBytes / 1e9:F2} GB" : "Verificar y preparar IA";
    public string Availability => SelectedModel is not null && _runtime.Services.ModelStore.FindExisting(SelectedModel) is not null ? "Disponible en este equipo · se verifica antes de cargar" : "Necesita descarga o importación";
    public string ModelInfo => SelectedModel is null ? "" : $"{SelectedModel.SizeBytes / 1e9:F2} GB de archivo · RAM de trabajo estimada {ModelMemoryPlanner.Plan(SelectedModel, _runtime.Device, Context, true).WorkingSetBytes / 1073741824d:F2} GiB · {SelectedModel.License}";
    public string ModelSource => SelectedModel is null ? "" : $"Fuente: {SelectedModel.SourceUrl}\nSHA-256: {SelectedModel.Sha256}\nArchivo: {_runtime.Services.ModelStore.FindExisting(SelectedModel) ?? "Aún no está preparado"}\nAlmacén: {_runtime.Services.ModelStore.CacheDirectory}";
    public string DeviceInfo => $"{_runtime.Device.Platform} · {_runtime.Device.Architecture} · RAM {_runtime.Device.TotalMemoryBytes / 1073741824d:F1} GiB total / {_runtime.Device.AvailableMemoryBytes / 1073741824d:F1} GiB disponible\n{_runtime.Hardware.Description}";
    public string RuntimeInfo => _runtime.State is { } state ? $"{state.Backend} · {state.Device ?? "procesador"} · {state.OffloadedLayers}/{state.TotalLayers?.ToString() ?? "?"} capas GPU · contexto {state.ContextTokens}" : "El modelo aún no está cargado";
    public string Recommendation { get => _advice; private set => Set(ref _advice, value); }
    public string ModelMessage { get => _modelMessage; private set => Set(ref _modelMessage, value); }
    public double Transfer { get => _transfer; private set => Set(ref _transfer, value); }
    public bool TransferIndeterminate { get => _transferIndeterminate; private set => Set(ref _transferIndeterminate, value); }
    public string Status { get => _status; private set => Set(ref _status, value); }
    public string Verdict => _verdict;
    public string VerdictColor => !UsableResult ? "#926316" : _result!.Attempts.Last().Parsed.Value!.IsCorrect ? "#196451" : "#87562C";
    public string Feedback => _feedback;
    public string CorrectedText => _corrected;
    public string Edits => _edits;
    public bool HasEdits => _edits.Length > 0;
    public string ParseStatus => _parse;
    public string Raw => _raw;
    public string ResultMetrics => _resultMetrics;
    public ReviewSession? LastSession => _result;
    public string HistoryDetail => _historyDetail;

    private Task? _initialization;
    public Task InitializeAsync() => _initialization ??= LoadStateAsync();
    private async Task LoadStateAsync()
    {
        try
        {
            _settings = await _store.SettingsAsync();
            _automatic = _settings.AutomaticModel; _context = _settings.Context; _maximumAttempts = _settings.MaximumAttempts;
            _backend = BackendChoices.First(b => b.Value == _settings.Backend);
            _selectedModel = Models.FirstOrDefault(m => m.Id == _settings.ModelId) ?? _selectedModel;
            Changed(nameof(SelectedModel));
            _advanced = _selectedModel is not null && !RecommendedModels.Any(m => m.Id == _selectedModel.Id);
            _adapter = null; Adapters.Clear(); _layers = _settings.GpuLayers?.ToString() ?? "";
            await RefreshSnapshotAsync();
            foreach (var draft in _snapshot.Drafts) _drafts[draft.Key] = draft.Value;
            await RefreshAdviceAsync();
        }
        catch (Exception e) { ReportError(e); }
        finally { _initializing = false; RefreshView(); RefreshModel(); Changed(nameof(AutomaticModel), nameof(Advanced), nameof(Context), nameof(MaximumAttempts), nameof(SelectedBackend), nameof(SelectedAdapter), nameof(ManualLayers)); }
    }
    public async Task RefreshSnapshotAsync()
    {
        _snapshot = await _store.SnapshotAsync();
        foreach (var unit in Units) unit.Done = unit.Unit.Activities.Count(a => _snapshot.Practiced.Contains(a.Id));
        History.Clear();
        foreach (var h in _snapshot.History.Take(100))
        {
            var unit = _course.Course.Units.FirstOrDefault(u => u.Activities.Any(a => a.Id == h.ActivityId));
            var activity = unit?.Activities.First(a => a.Id == h.ActivityId);
            var title = unit is null ? "Writing libre" : $"{unit.Title} · {activity!.TypeLabel}";
            var item = new HistoryItem(h, title, h.Detail); item.OpenCommand = new(_ => ShowHistory(item)); History.Add(item);
        }
        Changed(nameof(CourseProgress), nameof(CourseProgressValue), nameof(ClosedAccuracy), nameof(ClosedAccuracyDetail), nameof(WritingCount), nameof(ActivityItems), nameof(UnitProgress), nameof(HasHistory), nameof(EmptyHistory));
    }
    private void Navigate(string page)
    {
        _page = page; _laboratory = page == "lab"; ClearResult();
        if (_laboratory) { _activity = null; _student = _drafts.GetValueOrDefault("laboratory-draft", ""); Changed(nameof(StudentText)); }
        if (page == "course") _unit = null;
        RefreshView();
    }
    public void OpenUnit(UnitCard unit)
    { _page = "course"; _laboratory = false; _unit = unit; _lesson = true; _activity = null; ClearResult(); RefreshView(); }
    public void OpenActivity(CourseActivity activity)
    {
        _activity = activity; _lesson = false; _laboratory = false; _page = "course";
        _choice = null; _word = ""; _student = _drafts.GetValueOrDefault(activity.Id, "");
        ClearClosed(); ClearResult(); Changed(nameof(StudentText), nameof(WordAnswer), nameof(SelectedChoice)); RefreshView();
    }
    private void StartPractice()
    { if (_unit is not null) OpenActivity(_unit.Unit.Activities.FirstOrDefault(a => !_snapshot.Practiced.Contains(a.Id)) ?? _unit.Unit.Activities[0]); }
    private void Continue()
    {
        var unit = Units.FirstOrDefault(u => u.Done < 11) ?? Units[0]; OpenUnit(unit);
        if (unit.Done > 0) StartPractice();
    }
    private void Next()
    {
        if (_unit is null || _activity is null) return;
        var index = Array.IndexOf(_unit.Unit.Activities, _activity);
        if (index + 1 < _unit.Unit.Activities.Length) OpenActivity(_unit.Unit.Activities[index + 1]);
        else { Navigate("course"); Status = "Unidad recorrida. Puedes repetirla o explorar otra."; }
    }
    private async Task CheckAsync()
    {
        if (_activity is null) return;
        var activity = _activity;
        var answer = activity.Type == "single_choice" ? _choice?.Id ?? "" : WordAnswer;
        var result = ClosedExercise.Check(activity, answer);
        await _store.SaveClosedAsync(activity, answer, result);
        if (_activity?.Id == activity.Id)
        {
            _closedHeading = result.Correct ? "✓ ¡Bien hecho!" : "Vamos a repasarlo";
            _closedText = (result.Correct ? "" : $"Respuesta: {result.Expected}\n\n") + result.Explanation;
        }
        Changed(nameof(ClosedText), nameof(ClosedHeading), nameof(HasClosedFeedback)); await RefreshSnapshotAsync();
    }
    private CourseSettings CurrentSettings()
    {
        int? layers = null;
        if (!string.IsNullOrWhiteSpace(_layers))
        {
            if (!int.TryParse(_layers, out var parsed) || parsed <= 0) throw new ArgumentException("Las capas manuales deben ser un entero positivo. Déjalo vacío para estimarlas.");
            layers = parsed;
        }
        return new CourseSettings(SelectedModel?.Id, _automatic, _backend.Value, Context, MaximumAttempts, _adapter?.Plan.Id ?? _settings.AdapterId, layers).Validated();
    }
    private void SavePreferences()
    {
        if (_initializing) return;
        try { _settings = CurrentSettings(); TrackDraft(SavePreferencesSafelyAsync(_settings)); }
        catch (Exception e) { Status = e.Message; }
    }
    private async Task SavePreferencesSafelyAsync(CourseSettings settings)
    { try { await _store.SaveSettingsAsync(settings); } catch (Exception e) { Dispatcher.UIThread.Post(() => ReportError(e)); } }
    private async Task RefreshAdviceSafelyAsync()
    { try { await RefreshAdviceAsync(); } catch (Exception e) { ReportError(e); } }
    public async Task RefreshAdviceAsync()
    {
        var advice = await _runtime.RecommendAsync(CurrentSettings(), CancellationToken.None);
        Recommendation = advice.Reason;
        if (_automatic) SelectModelAutomatically(advice.Model);
        Changed(nameof(DeviceInfo)); SavePreferences();
    }
    private async Task PrepareAsync(bool download)
    {
        if (SelectedModel is not { } model) return;
        if (ModelReady) { ModelMessage = "El modelo ya está preparado. Usa Recalibrar si quieres repetir la medición."; return; }
        if (_runtime.Services.ModelStore.FindExisting(model) is null && model.DownloadUrl is null)
        {
            Navigate("models"); ModelMessage = "Esta conversión local no tiene descarga directa. Pulsa Importar GGUF o elige una variante descargable de Unsloth.";
            Status = ModelMessage; return;
        }
        await WithOperation(async ct =>
        {
            if (_automatic)
            {
                var advice = await _runtime.RecommendAsync(CurrentSettings(), ct);
                Recommendation = advice.Reason;
                if (advice.Model.Id != model.Id)
                {
                    SelectModelAutomatically(advice.Model); model = advice.Model; SavePreferences();
                    if (_runtime.Services.ModelStore.FindExisting(model) is null)
                    {
                        ModelMessage = "Cambió el margen de recursos y se actualizó la propuesta. Revisa el modelo y pulsa de nuevo para autorizar su descarga: " + model.Label;
                        Status = ModelMessage; return;
                    }
                }
            }
            var settings = CurrentSettings();
            KeepsDisplayAwake = _runtime.Services.ModelStore.FindExisting(model) is not null;
            ModelMessage = "Verificando el modelo. La primera calibración puede tardar varios minutos; puedes cancelarla.";
            var result = await _runtime.PrepareAsync(model, settings, download, DownloadProgress(), ct);
            SelectModelAutomatically(result.Model); ModelMessage = result.Message; Status = result.Engine is null ? result.Message : "IA preparada. Ya puedes evaluar tu Writing.";
            SavePreferences();
        });
        RefreshModel();
    }
    private IProgress<DownloadProgress> DownloadProgress() => new Progress<DownloadProgress>(p =>
    {
        Transfer = p.TotalBytes > 0 ? p.ReceivedBytes * 100d / p.TotalBytes : 0;
        TransferIndeterminate = p.ReceivedBytes == 0 || p.Message.Contains("Verificando", StringComparison.OrdinalIgnoreCase);
        ModelMessage = p.Message + (p.BytesPerSecond > 0 ? $" · {p.BytesPerSecond / 1e6:F1} MB/s" : "") + (p.RemainingSeconds is { } seconds ? $" · ≈ {TimeSpan.FromSeconds(seconds):mm\\:ss}" : "");
    });
    private async Task DownloadAsync()
    {
        if (SelectedModel is not { } model) return;
        await WithOperation(async ct => { await _runtime.Services.Downloads.EnsureAsync(model, DownloadProgress(), ct); ModelMessage = "GGUF verificado y guardado. Pulsa Preparar IA para medir el motor."; });
        RefreshModel();
    }
    public async Task ImportAsync(Stream stream)
    {
        if (SelectedModel is not { } model) return;
        await WithOperation(async ct => { await _runtime.Services.ModelStore.ImportAsync(model, stream, DownloadProgress(), ct); ModelMessage = "Modelo importado y verificado. Puedes prepararlo sin conexión."; });
        RefreshModel();
    }
    private async Task InspectAsync()
    {
        if (SelectedModel is not { } model) return;
        await WithOperation(async ct =>
        {
            var inventory = await _runtime.InspectAsync(model, Context, ct);
            Adapters.Clear(); foreach (var device in inventory.Devices) Adapters.Add(new(device));
            _adapter = Adapters.FirstOrDefault(a => a.Plan.Id == _settings.AdapterId);
            Changed(nameof(SelectedAdapter));
            ModelMessage = $"{Adapters.Count} adaptadores consultados. Deja las capas vacías para ajustar según memoria; la selección manual requiere Vulkan.";
        });
    }
    private async Task EvaluateAsync()
    {
        var exercise = LabPage ? LabExercise() : _activity!.ToExercise();
        var text = StudentText; var laboratory = LabPage;
        ClearResult();
        await WithOperation(async ct =>
        {
            KeepsDisplayAwake = true;
            Status = "La IA está leyendo tu respuesta…";
            var session = await _writing.EvaluateAsync(exercise, text, laboratory, MaximumAttempts, null, ct);
            if (StudentText == text && (LabPage == laboratory) && (laboratory ? LabTask == exercise.Task && LabLevel == exercise.Level : _activity?.Id == exercise.Id)) ApplySession(session);
            Status = session.Usable ? "Evaluación guardada. Puedes revisar la retroalimentación o seguir practicando." : "La salida no fue utilizable. Tu texto y todos los intentos se conservaron.";
            await RefreshSnapshotAsync();
        });
        RefreshModel();
    }
    private WritingExercise LabExercise() => new("laboratory-writing", LabLevel, "Writing libre", LabTask,
        "Hello, my name is Sofia. I am from Colombia. I am a student.", "Hello, my name is Sofia. I are from Colombia. I am a student.");
    private void SetExample(bool correct)
    { if (!_busy && LabPage) { var exercise = LabExercise(); StudentText = correct ? exercise.CorrectExample : exercise.IncorrectExample; } }
    private void SimulateInvalid()
    {
        if (!LabPage || _busy) return;
        ClearResult(); _raw = "SIMULACIÓN · no procede de un modelo\n{\"is_correct\":";
        _verdict = "⚠ Ejemplo de JSON incompleto"; _parse = "SIMULADO · la interfaz debe avisar y conservar el texto original.";
        _feedback = "Esta demostración no ejecuta el modelo ni se registra como práctica."; NotifyResult();
    }
    public void ApplySession(ReviewSession session)
    {
        _result = session; var last = session.Attempts.Last(); var value = last.Parsed.Value;
        _verdict = !session.Usable || value is null ? "⚠ No pudimos interpretar la evaluación" : value.IsCorrect ? "✓ Bien escrito, según el modelo" : "✕ Revisa estos detalles, según el modelo";
        _corrected = session.Usable ? value!.CorrectedText : "";
        _feedback = session.Usable ? string.IsNullOrWhiteSpace(value!.Feedback) ? "Sin comentario adicional del modelo." : value.Feedback : last.Parsed.Error ?? "El modelo devolvió una salida no utilizable.";
        _edits = session.Usable ? string.Join("\n\n", value!.Errors.Select(e => $"{e.Original}  →  {e.Correction}\n{e.Explanation}")) : "";
        _parse = last.Parsed.Status switch { "STRICT" => "JSON válido · contrato interpretado", "RECOVERED" => "JSON recuperado · se conserva el RAW completo", _ => $"{last.Parsed.Status} · sin veredicto utilizable" };
        _raw = string.Join("\n\n", session.Attempts.Select(a => $"INTENTO {a.Number} · semilla {a.Seed} · {a.Parsed.Status} · {a.Output.Seconds:F2} s\n{a.Output.Content}"));
        _resultMetrics = $"{session.Model.Name} · {session.Model.Quantization}\n{session.Engine.Backend} · {session.Engine.OffloadedLayers}/{session.Engine.TotalLayers} capas GPU · {session.Attempts.Sum(a => a.Output.Seconds):F1} s · {session.Attempts.Length} intento(s)";
        NotifyResult();
    }
    private void ShowHistory(HistoryItem item)
    {
        _selectedHistory = item;
        if (item.Entry.SessionJson is { } json)
        {
            var session = JsonSerializer.Deserialize(json, AppJsonContext.Default.ReviewSession)!;
            var final = session.Attempts.Last();
            _historyDetail = $"{item.Title}\n{session.Task}\n\nTu texto\n{session.StudentText}\n\n{(session.Usable ? final.Parsed.Value?.CorrectedText : final.Parsed.Error)}\n{final.Parsed.Value?.Feedback}\n\n{session.Model.Name} · {session.Model.Quantization} · {session.Engine.Backend}\n\nJSON / RAW\n" + string.Join("\n\n", session.Attempts.Select(a => a.Output.Content));
        }
        else _historyDetail = $"{item.Title}\n{item.Entry.StudentText}\n\n{item.Status}\n{item.Entry.Detail}";
        Changed(nameof(HistoryDetail), nameof(HasHistoryDetail));
    }
    private async Task WithOperation(Func<CancellationToken, Task> work)
    {
        if (_busy) throw new InvalidOperationException("Espera a que termine la operación actual.");
        _operation = new(); _idle = new(); _busy = true; Transfer = 0; TransferIndeterminate = true; Changed(nameof(IsBusy), nameof(CanEdit)); RefreshCommands();
        try { await work(_operation.Token); }
        catch (CalibrationInterruptedException e) { Status = e.Message; ModelMessage = Status; }
        catch (OperationCanceledException) { Status = "Operación cancelada. Los archivos completos y los borradores se conservan."; ModelMessage = Status; }
        finally { _busy = false; KeepsDisplayAwake = false; _operation.Dispose(); _operation = null; TransferIndeterminate = false; Changed(nameof(IsBusy), nameof(CanEdit)); RefreshCommands(); RefreshModel(); _idle.TrySetResult(); }
    }
    public async Task ExportBackupAsync(Stream target) { await FlushDraftsAsync(); await _store.BackupAsync(target); Status = "Respaldo exportado con progreso, borradores e historial. Los modelos no se incluyen."; }
    public async Task RestoreAsync(Stream source)
    {
        await WithOperation(async _ =>
        {
            await FlushDraftsAsync(); await _runtime.UnloadAsync();
            var previous = await _store.RestoreAsync(source);
            _initializing = true; _initialization = LoadStateAsync(); await _initialization;
            _drafts.Clear(); foreach (var draft in _snapshot.Drafts) _drafts[draft.Key] = draft.Value;
            Navigate("course"); Status = $"Respaldo restaurado. Copia automática del estado anterior: {previous}";
        });
    }
    public Task ExportHistoryAsync(Stream target, bool csv) => csv ? _store.ExportCsvAsync(target) : _store.ExportHistoryAsync(target);
    private void TrackDraft(Task task)
    {
        _pendingDrafts.Add(task);
        _ = ObserveDraft(task);
    }
    private async Task ObserveDraft(Task task)
    { try { await task; } catch (Exception e) { ReportError(e); } finally { _pendingDrafts.Remove(task); } }
    public Task FlushDraftsAsync() => Task.WhenAll(_pendingDrafts.ToArray());
    public bool GoBack()
    {
        if (_page != "course") { Navigate("course"); return true; }
        if (_unit is null) return false;
        if (!_lesson) { OpenUnit(_unit); return true; }
        Navigate("course"); return true;
    }
    public void ReportError(Exception error)
    {
        Status = "No se completó: " + error.Message; ModelMessage = Status;
        _warning = true; _parse = "PROBLEMA TÉCNICO · no se emitió un veredicto"; _corrected = _edits = _resultMetrics = "";
        _verdict = "⚠ No se pudo completar esta acción";
        _feedback = error.Message; _raw = ""; _result = null; NotifyResult(); RefreshModel();
    }
    private void RuntimeProgress(string message) => Dispatcher.UIThread.Post(() => { ModelMessage = message; if (_busy) Status = message; });
    private void EngineStarting() => Dispatcher.UIThread.Post(() => { if (_busy) KeepsDisplayAwake = true; });
    private void ClearClosed() { _closedText = ""; _closedHeading = ""; Changed(nameof(ClosedText), nameof(ClosedHeading), nameof(HasClosedFeedback)); }
    private void ClearResult()
    { _result = null; _warning = false; _verdict = "Tu retroalimentación aparecerá aquí"; _feedback = _corrected = _edits = _parse = _raw = _resultMetrics = ""; NotifyResult(); }
    private void NotifyResult() => Changed(nameof(HasResult), nameof(HasSession), nameof(EmptyResult), nameof(UsableResult), nameof(Verdict), nameof(VerdictColor), nameof(Feedback), nameof(CorrectedText), nameof(Edits), nameof(HasEdits), nameof(ParseStatus), nameof(Raw), nameof(ResultMetrics), nameof(LastSession));
    private void RefreshCommands() { foreach (var command in _asyncCommands) command.Refresh(); Changed(nameof(CanEvaluate)); }
    private void RefreshModel()
    { Changed(nameof(SelectedModelName), nameof(RecommendedModels), nameof(ModelInfo), nameof(ModelSource), nameof(PrepareLabel), nameof(Availability), nameof(RuntimeInfo), nameof(ModelReady), nameof(NeedsModel), nameof(DeviceInfo)); RefreshCommands(); }
    private void RefreshView()
    {
        Changed(nameof(HomePage), nameof(UnitPage), nameof(HistoryPage), nameof(ModelsPage), nameof(LabPage), nameof(ShowLesson), nameof(ShowActivity), nameof(ShowClosed), nameof(ShowWriting), nameof(ShowOptions), nameof(ShowWord), nameof(PageTitle), nameof(PageSubtitle), nameof(UnitTitle), nameof(UnitSubtitle), nameof(UnitProgress), nameof(ActivityItems), nameof(Lessons), nameof(ActivityNumber), nameof(ActivityType), nameof(Prompt), nameof(Options), nameof(CharacterCount), nameof(CanEdit));
        RefreshCommands();
    }
    public void Adapt(double availableWidth)
    {
        Compact = availableWidth < 760;
        var contentWidth = Math.Max(280, availableWidth - (Compact ? 32 : 284));
        var columns = contentWidth >= 900 ? 3 : contentWidth >= 580 ? 2 : 1;
        var width = Math.Max(240, (contentWidth - columns * 16) / columns);
        foreach (var unit in Units) unit.Width = width;
    }
    public async ValueTask DisposeAsync()
    {
        _operation?.Cancel(); if (_idle is not null) await _idle.Task; await FlushDraftsAsync(); _runtime.StatusChanged -= RuntimeProgress; _runtime.EngineStarting -= EngineStarting;
        await _runtime.DisposeAsync();
    }
}
