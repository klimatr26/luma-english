using System.ComponentModel;
using System.Runtime.CompilerServices;
using Avalonia.Media;
using WritingApp.Shared;
using WritingDemo.Core;

namespace WritingApp.UI;

public sealed record BackendChoice(BackendPreference Preference, string Label)
{
    public override string ToString() => Label;
}

public sealed record ExerciseOption(WritingExercise Exercise, string Label)
{
    public override string ToString() => Label;
}

public sealed class MainWindowViewModel : INotifyPropertyChanged
{
    private static readonly IReadOnlyList<BackendChoice> BackendOptions = Array.AsReadOnly(new BackendChoice[]
    {
        new(BackendPreference.AutoVulkanCpu, "Auto Vulkan/CPU"),
        new(BackendPreference.Vulkan, "Vulkan"),
        new(BackendPreference.Cpu, "CPU")
    });

    private static readonly IReadOnlyList<int> Attempts = Array.AsReadOnly(new[] { 1, 2, 3 });
    private static readonly IReadOnlyList<string> LevelOptions = Array.AsReadOnly(new[] { "A1", "A2" });

    private readonly List<EvaluationAttempt> _attempts = [];
    private ModelEntry? _selectedModel;
    private BackendChoice _selectedBackend = BackendOptions[0];
    private IReadOnlyList<ExerciseOption> _exercises = Array.Empty<ExerciseOption>();
    private ExerciseOption? _selectedExercise;
    private string _selectedLevel = "A1";
    private string _taskText = string.Empty;
    private string _studentText = string.Empty;
    private string _exampleStatus = "Escribe una respuesta o carga un ejemplo para revisarlo.";
    private int _maximumAttempts = 1;
    private bool _isLoadActive;
    private bool _isEvaluationActive;
    private string _modelOperationStatus = "Selecciona un modelo. La primera preparación verifica el tamaño y el SHA-256.";
    private string _loadedModelStatus = "Todavía no hay un modelo cargado.";
    private double _downloadProgressValue;
    private bool _downloadIsIndeterminate;
    private string _verdictText = "Esperando una respuesta";
    private IBrush _verdictBrush = new SolidColorBrush(Color.Parse("#183A37"));
    private string _parseStatusText = "El estado del JSON y el contrato aparecerá después de evaluar.";
    private string _evaluationStatus = string.Empty;
    private string _correctedText = string.Empty;
    private string _feedbackText = string.Empty;
    private string _editsText = string.Empty;
    private string _rawAttempts = string.Empty;
    private ReviewSession? _lastSession;

    public MainWindowViewModel(AppServices services)
    {
        Services = services ?? throw new ArgumentNullException(nameof(services));
        if (services.Engine is IRuntimeProgress progress)
            progress.StatusChanged += message => Avalonia.Threading.Dispatcher.UIThread.Post(() => ModelOperationStatus = message);
        var pendingModelId = services.Downloads.PendingModelId;
        _selectedModel = services.Models.FirstOrDefault(m => m.Id == pendingModelId)
            ?? services.Models.FirstOrDefault(m => m.Id == services.Recommendation.ModelId)
            ?? services.Models.FirstOrDefault();
        Exercises = BuildExercises(_selectedLevel);
        SelectedExercise = Exercises.FirstOrDefault();
    }

    public event PropertyChangedEventHandler? PropertyChanged;

    public AppServices Services { get; }
    public IReadOnlyList<ModelEntry> Models => Services.Models;
    public IReadOnlyList<BackendChoice> BackendChoices => BackendOptions;
    public IReadOnlyList<int> AttemptChoices => Attempts;
    public IReadOnlyList<string> Levels => LevelOptions;
    public IReadOnlyList<ExerciseOption> Exercises
    {
        get => _exercises;
        private set => Set(ref _exercises, value);
    }

    public ModelEntry? SelectedModel
    {
        get => _selectedModel;
        set
        {
            if (!Set(ref _selectedModel, value)) return;
            OnPropertyChanged(nameof(ModelDetails));
            OnPropertyChanged(nameof(ModelDiagnosticDetails));
            OnPropertyChanged(nameof(ModelActionText));
            OnPropertyChanged(nameof(CanDownloadModel));
            OnPropertyChanged(nameof(RecommendationText));
            OnPropertyChanged(nameof(LoadedModelStatus));
            InvalidateEvaluationResult("El modelo seleccionado cambió.");
        }
    }

    public BackendChoice SelectedBackend
    {
        get => _selectedBackend;
        set
        {
            if (!Set(ref _selectedBackend, value)) return;
            OnPropertyChanged(nameof(LoadedModelStatus));
            InvalidateEvaluationResult("El backend seleccionado cambió.");
        }
    }

    public ExerciseOption? SelectedExercise
    {
        get => _selectedExercise;
        set
        {
            if (!Set(ref _selectedExercise, value) || value is null) return;
            TaskText = value.Exercise.Task;
            StudentText = string.Empty;
            ExampleStatus = "Escribe una respuesta o carga un ejemplo para revisarlo.";
            InvalidateEvaluationResult("El ejercicio seleccionado cambió.");
        }
    }

    public string SelectedLevel
    {
        get => _selectedLevel;
        set
        {
            if (!Set(ref _selectedLevel, value)) return;
            Exercises = BuildExercises(value);
            SelectedExercise = Exercises.FirstOrDefault();
            InvalidateEvaluationResult("El nivel seleccionado cambió.");
        }
    }

    public string TaskText
    {
        get => _taskText;
        set
        {
            if (Set(ref _taskText, value)) InvalidateEvaluationResult("La consigna cambió.");
        }
    }
    public string StudentText
    {
        get => _studentText;
        set
        {
            if (Set(ref _studentText, value))
            {
                ExampleStatus = "Respuesta editada por el usuario.";
                InvalidateEvaluationResult("La respuesta cambió.");
            }
        }
    }

    public string ExampleStatus { get => _exampleStatus; set => Set(ref _exampleStatus, value); }
    public int MaximumAttempts
    {
        get => _maximumAttempts;
        set
        {
            if (Set(ref _maximumAttempts, Math.Clamp(value, 1, 3)))
                InvalidateEvaluationResult("La cantidad máxima de intentos cambió.");
        }
    }
    public bool IsLoadActive
    {
        get => _isLoadActive;
        set
        {
            if (!Set(ref _isLoadActive, value)) return;
            OnPropertyChanged(nameof(CanLoadModel));
            OnPropertyChanged(nameof(CanUnloadModel));
            OnPropertyChanged(nameof(CanEvaluate));
            OnPropertyChanged(nameof(CanEditEvaluationInputs));
            OnPropertyChanged(nameof(CanCancelInferenceOperation));
            OnPropertyChanged(nameof(CanImportModel));
        }
    }
    public bool IsEvaluationActive
    {
        get => _isEvaluationActive;
        set
        {
            if (!Set(ref _isEvaluationActive, value)) return;
            OnPropertyChanged(nameof(CanLoadModel));
            OnPropertyChanged(nameof(CanUnloadModel));
            OnPropertyChanged(nameof(CanEvaluate));
            OnPropertyChanged(nameof(CanEditEvaluationInputs));
            OnPropertyChanged(nameof(CanCancelInferenceOperation));
        }
    }
    public bool CanLoadModel => !IsLoadActive && !IsEvaluationActive;
    public bool CanUnloadModel => !IsLoadActive && !IsEvaluationActive;
    public bool CanImportModel => !IsLoadActive;
    public bool CanEvaluate => !IsLoadActive && !IsEvaluationActive;
    public bool CanEditEvaluationInputs => !IsLoadActive && !IsEvaluationActive;
    public bool CanCancelInferenceOperation => IsLoadActive || IsEvaluationActive;
    public string ModelOperationStatus { get => _modelOperationStatus; set => Set(ref _modelOperationStatus, value); }
    public double DownloadProgressValue { get => _downloadProgressValue; set => Set(ref _downloadProgressValue, Math.Clamp(value, 0, 100)); }
    public bool DownloadIsIndeterminate { get => _downloadIsIndeterminate; set => Set(ref _downloadIsIndeterminate, value); }
    public string VerdictText { get => _verdictText; private set => Set(ref _verdictText, value); }
    public IBrush VerdictBrush { get => _verdictBrush; private set => Set(ref _verdictBrush, value); }
    public string ParseStatusText { get => _parseStatusText; private set => Set(ref _parseStatusText, value); }
    public string EvaluationStatus { get => _evaluationStatus; set => Set(ref _evaluationStatus, value); }
    public string CorrectedText { get => _correctedText; private set => Set(ref _correctedText, value); }
    public string FeedbackText { get => _feedbackText; private set => Set(ref _feedbackText, value); }
    public string EditsText { get => _editsText; private set => Set(ref _editsText, value); }
    public string RawAttempts { get => _rawAttempts; private set => Set(ref _rawAttempts, value); }
    public ReviewSession? LastSession
    {
        get => _lastSession;
        private set
        {
            if (Set(ref _lastSession, value)) OnPropertyChanged(nameof(CanExport));
        }
    }
    public bool CanExport => LastSession is not null;

    public string ModelActionText => SelectedModel is { DownloadUrl: not null } model && Services.ModelStore.FindExisting(model) is not null
        ? "Verificar GGUF"
        : SelectedModel?.DownloadUrl is null ? "Sin descarga directa" : "Descargar / reanudar";
    public string DownloadHelp => Services.Downloads.ContinuesInBackground
        ? "Android gestiona la transferencia en segundo plano. Al completarse, Writing Lab verifica y guarda el GGUF en sus archivos permanentes. Pulsa Descargar / reanudar para ver el progreso."
        : "Las descargas interrumpidas conservan un parcial para reanudar. El archivo solo se publica tras verificar SHA-256.";
    public bool CanDownloadModel => SelectedModel?.DownloadUrl is not null;

    public string ModelDetails
    {
        get
        {
            if (SelectedModel is not { } model) return "No hay un modelo disponible en el catálogo.";
            var size = FormatBytes(model.SizeBytes);
            var estimate = FormatBytes(ModelRecommender.Estimate(model, Services.DefaultContext));
            var cached = Services.ModelStore.FindExisting(model) is null
                ? "Aún no hay un GGUF listo para cargar."
                : "GGUF disponible en el dispositivo. Se comprobará su SHA-256 al cargarlo.";
            var source = model.DownloadUrl is null ? " · conversión local: importa el GGUF exacto" : string.Empty;
            var mobile = Services.Device.Platform == "Android" ? "\nEn CPU de móviles, los modelos mayores pueden tardar mucho aunque quepan en RAM. Q4 reduce tamaño y tráfico de memoria; no garantiza calidad ni velocidad." : "";
            return $"Archivo: {size} · Licencia: {model.License} · RAM estimada a {Services.DefaultContext} tokens: {estimate}{source}.\n{cached}{mobile}";
        }
    }

    public string ModelDiagnosticDetails
    {
        get
        {
            var recommendation = Services.Recommendation;
            var recommendationModel = Services.Models.FirstOrDefault(m => m.Id == recommendation.ModelId);
            var model = SelectedModel;
            var source = model is null ? "" : model.DownloadUrl is null
                ? "Origen GGUF: conversión local registrada; debes importar el archivo original verificado. No se descargará ni sustituirá por otro modelo."
                : $"Origen fijado: {model.SourceUrl}";
            var localPath = model is null ? "" : Services.ModelStore.FindExisting(model) ?? "No se encontró archivo local para esta variante.";
            var hardware = $"Dispositivo: {Services.Device.Platform} · arquitectura {Services.Device.Architecture} · RAM total {FormatBytes(Services.Device.TotalMemoryBytes)} · RAM disponible {FormatBytes(Services.Device.AvailableMemoryBytes)} · espacio libre de caché {FormatBytes(Services.Device.FreeStorageBytes)}.";
            var detectedBackend = string.IsNullOrWhiteSpace(Services.Device.GpuDescription)
                ? "GPU: no consultada durante la recomendación; se mostrará solo lo que confirme el backend después de cargar."
                : $"GPU reportada por el host: {Services.Device.GpuDescription}";
            var suggested = recommendationModel is null ? recommendation.ModelId : recommendationModel.Label;
            return $"Motivo de la sugerencia para {suggested}: {recommendation.Reason}\n{hardware}\n{detectedBackend}\n{source}\nArchivo local: {localPath}\nAlmacén de modelos: {Services.ModelStore.CacheDirectory}";
        }
    }

    public string RecommendationText
    {
        get
        {
            var recommendation = Services.Recommendation;
            var model = Services.Models.FirstOrDefault(m => m.Id == recommendation.ModelId);
            var memory = Services.Device.TotalMemoryBytes > 0 ? FormatBytes(Services.Device.TotalMemoryBytes) : "no disponible";
            var available = Services.Device.AvailableMemoryBytes > 0 ? FormatBytes(Services.Device.AvailableMemoryBytes) : "no disponible";
            var storage = Services.Device.FreeStorageBytes > 0 ? FormatBytes(Services.Device.FreeStorageBytes) : "no disponible";
            var name = model is null ? recommendation.ModelId : model.Label;
            var fit = recommendation.FitsEstimate ? "dentro del presupuesto estimado" : "por encima del presupuesto estimado";
            return $"Sugerido: {name}. RAM detectada: {memory} total / {available} disponible · libre en caché: {storage}. RAM prevista: {FormatBytes(recommendation.EstimatedMemoryBytes)} a {Services.DefaultContext} tokens ({fit}); estimación orientativa.";
        }
    }

    public string LoadedModelStatus
    {
        get
        {
            if (_loadedModel is null || _loadedEngine is null) return _loadedModelStatus;
            if (SelectedModel?.Id != _loadedModel.Id)
                return $"{_loadedModel.Label} continúa cargado. Al cargar la selección actual se sustituirá.";
            if (SelectedBackend.Preference != _loadedEngine.Requested)
                return $"{_loadedModel.Label} está cargado con {_loadedEngine.Backend}; carga de nuevo para aplicar {SelectedBackend.Label}.";
            var device = string.IsNullOrWhiteSpace(_loadedEngine.Device) ? string.Empty : $" · dispositivo informado por el backend: {_loadedEngine.Device}";
            var fallback = string.IsNullOrWhiteSpace(_loadedEngine.FallbackReason) ? string.Empty : $" · selección: {_loadedEngine.FallbackReason}";
            var offload = _loadedEngine.OffloadedLayers < 0
                ? "capas GPU: no medidas"
                : $"capas GPU: {_loadedEngine.OffloadedLayers}" + (_loadedEngine.TotalLayers is > 0 ? $"/{_loadedEngine.TotalLayers}" : "");
            var format = _loadedEngine.ResponseFormat=="writing_json_grammar_v1" ? " · JSON guiado (no garantiza que el juicio lingüístico sea correcto)" : " · salida libre";
            return $"Cargado: {_loadedModel.Label} · backend efectivo: {_loadedEngine.Backend}{device} · {offload}{fallback}{format}";
        }
    }

    private ModelEntry? _loadedModel;
    private EngineState? _loadedEngine;

    public void SetLoaded(ModelEntry? model, EngineState? engine)
    {
        _loadedModel = model;
        _loadedEngine = engine;
        _loadedModelStatus = model is null ? "Modelo liberado de memoria." : string.Empty;
        OnPropertyChanged(nameof(LoadedModelStatus));
    }

    public void SetDownloadProgress(ModelEntry model, DownloadProgress progress)
    {
        var ratio = progress.TotalBytes > 0 ? Math.Clamp((double)progress.ReceivedBytes / progress.TotalBytes, 0d, 1d) : 0d;
        DownloadIsIndeterminate = progress.TotalBytes <= 0;
        DownloadProgressValue = ratio * 100;
        var received = progress.ReceivedBytes > 0 ? $" · {FormatBytes(progress.ReceivedBytes)}" : string.Empty;
        var total = progress.TotalBytes > 0 ? $" / {FormatBytes(progress.TotalBytes)}" : string.Empty;
        var speed = progress.BytesPerSecond > 0 ? $" · {progress.BytesPerSecond / 1e6:F1} MB/s" : string.Empty;
        var eta = progress.RemainingSeconds is > 0 and < 86400 ? $" · aprox. {TimeSpan.FromSeconds(progress.RemainingSeconds.Value):hh\\:mm\\:ss} restantes" : string.Empty;
        ModelOperationStatus = $"{model.Name}: {progress.Message}{received}{total}{speed}{eta}";
        OnPropertyChanged(nameof(ModelDetails));
    }

    public void SetOperationMessage(string message)
    {
        ModelOperationStatus = message;
        DownloadIsIndeterminate = false;
    }

    public void NotifyModelStoreChanged()
    {
        OnPropertyChanged(nameof(ModelDetails));
        OnPropertyChanged(nameof(ModelDiagnosticDetails));
        OnPropertyChanged(nameof(ModelActionText));
    }

    public void UseExample(bool correct)
    {
        if (SelectedExercise is not { } selected) return;
        StudentText = correct ? selected.Exercise.CorrectExample : selected.Exercise.IncorrectExample;
        ExampleStatus = correct
            ? "Ejemplo correcto de demostración seleccionado; el modelo lo evaluará sin una etiqueta oculta."
            : "Ejemplo con errores de demostración seleccionado; el modelo lo evaluará sin una etiqueta oculta.";
    }

    public WritingExercise CreateCurrentExercise()
    {
        if (SelectedExercise is not { } selected) throw new InvalidOperationException("Selecciona un ejercicio A1 o A2.");
        return selected.Exercise with { Task = TaskText };
    }

    public void BeginEvaluation()
    {
        _attempts.Clear();
        LastSession = null;
        VerdictText = "Evaluación en curso…";
        VerdictBrush = new SolidColorBrush(Color.Parse("#183A37"));
        ParseStatusText = "La salida RAW de cada intento aparecerá aquí mientras se evalúa.";
        EvaluationStatus = "Enviando solo la consigna y la respuesta escrita.";
        CorrectedText = string.Empty;
        FeedbackText = string.Empty;
        EditsText = string.Empty;
        RawAttempts = string.Empty;
    }

    public bool InputsMatch(string modelId, BackendPreference backend, string exerciseId,
        string task, string studentText, int maximumAttempts) =>
        string.Equals(SelectedModel?.Id, modelId, StringComparison.Ordinal)
        && SelectedBackend.Preference == backend
        && string.Equals(SelectedExercise?.Exercise.Id, exerciseId, StringComparison.Ordinal)
        && string.Equals(TaskText, task, StringComparison.Ordinal)
        && string.Equals(StudentText, studentText, StringComparison.Ordinal)
        && MaximumAttempts == maximumAttempts;

    public void AddAttempt(EvaluationAttempt attempt)
    {
        _attempts.Add(attempt);
        RawAttempts = FormatAttempts(_attempts);
        EvaluationStatus = $"Intento {attempt.Number} de {MaximumAttempts} recibido · semilla {attempt.Seed}.";
    }

    public void ApplySession(ReviewSession session)
    {
        LastSession = session;
        _attempts.Clear();
        _attempts.AddRange(session.Attempts);
        RawAttempts = FormatAttempts(_attempts);
        var last = session.Attempts.LastOrDefault();
        if (last is null)
        {
            ShowWarning("No se recibió una salida del modelo.", session.StopReason);
            return;
        }

        var parsed = last.Parsed;
        var value = parsed.Value;
        if (session.Usable && value is not null)
        {
            var isRecovered = parsed.Status == "RECOVERED";
            VerdictText = value.IsCorrect ? "✓ El modelo indica: correcto" : "✕ El modelo indica: con errores";
            VerdictBrush = new SolidColorBrush(Color.Parse(value.IsCorrect ? "#27735D" : "#A33C36"));
            ParseStatusText = isRecovered
                ? "Advertencia: se recuperó JSON de una envoltura; la salida original se conserva abajo."
                : "JSON válido y contrato correcto.";
            CorrectedText = value.CorrectedText;
            FeedbackText = string.IsNullOrWhiteSpace(value.Feedback) ? "El modelo no añadió comentarios." : value.Feedback;
            EditsText = value.Errors.Count == 0
                ? "El modelo no enumeró ediciones."
                : string.Join(Environment.NewLine + Environment.NewLine, value.Errors.Select((edit, index) =>
                    $"{index + 1}. {edit.Original} → {edit.Correction}\nTipo: {edit.Type}\n{edit.Explanation}"));
        }
        else
        {
            var label = parsed.Status switch
            {
                "INCONSISTENT" => "JSON interpretado, pero sus campos se contradicen.",
                "INVALID_SCHEMA" => "JSON recibido, pero el contrato de campos no coincide.",
                _ => "No se pudo interpretar un único JSON válido."
            };
            ShowWarning(label, parsed.Error ?? session.StopReason);
            if (value is not null)
            {
                CorrectedText = value.CorrectedText;
                FeedbackText = value.Feedback;
                EditsText = value.Errors.Count == 0 ? string.Empty : string.Join(Environment.NewLine, value.Errors.Select(e => $"{e.Original} → {e.Correction} · {e.Explanation}"));
            }
        }
        EvaluationStatus = session.Usable
            ? "Evaluación terminada. La marca refleja solo lo que afirma el modelo; no es una calificación humana."
            : $"No se obtuvo un contrato utilizable después de {session.Attempts.Length} intento(s). {session.StopReason}";
        if(last.Output.Metrics is { } metrics)
            EvaluationStatus += $" Tiempo total: {last.Output.Seconds:F1} s · prompt: {metrics.PromptSeconds:F1} s · salida: {metrics.OutputTokens} tokens · decodificación: {metrics.DecodeTokensPerSecond:F1} tok/s.";
    }

    public void ShowEvaluationFailure(string message)
    {
        ShowWarning("Problema al completar la evaluación.", message);
        EvaluationStatus = message;
        RawAttempts = FormatAttempts(_attempts);
    }

    public void SetEvaluationStatus(string message) => EvaluationStatus = message;

    private void ShowWarning(string title, string? details)
    {
        VerdictText = "⚠ Advertencia · " + title;
        VerdictBrush = new SolidColorBrush(Color.Parse("#9A6100"));
        ParseStatusText = string.IsNullOrWhiteSpace(details) ? title : $"{title} {details}";
        CorrectedText = string.Empty;
        FeedbackText = string.Empty;
        EditsText = string.Empty;
    }

    private void InvalidateEvaluationResult(string reason)
    {
        if (LastSession is null && _attempts.Count == 0) return;
        _attempts.Clear();
        LastSession = null;
        VerdictText = "Esperando una respuesta";
        VerdictBrush = new SolidColorBrush(Color.Parse("#183A37"));
        ParseStatusText = $"Se limpió el resultado anterior porque {char.ToLowerInvariant(reason[0])}{reason[1..]}";
        EvaluationStatus = "Evalúa de nuevo para revisar las entradas actuales.";
        CorrectedText = string.Empty;
        FeedbackText = string.Empty;
        EditsText = string.Empty;
        RawAttempts = string.Empty;
    }

    private static string FormatAttempts(IEnumerable<EvaluationAttempt> attempts)
    {
        var blocks = attempts.Select(attempt =>
        {
            var parsed = attempt.Parsed;
            var heading = $"--- Intento {attempt.Number} · semilla {attempt.Seed} · {parsed.Status} ---";
            var error = string.IsNullOrWhiteSpace(parsed.Error) ? string.Empty : $"{Environment.NewLine}Parser: {parsed.Error}";
            var diagnostics = string.IsNullOrWhiteSpace(attempt.Output.Diagnostics) ? string.Empty : $"{Environment.NewLine}Diagnóstico del motor: {attempt.Output.Diagnostics}";
            return $"{heading}{error}{diagnostics}{Environment.NewLine}{attempt.Output.Content}";
        });
        return string.Join(Environment.NewLine + Environment.NewLine, blocks);
    }

    private static IReadOnlyList<ExerciseOption> BuildExercises(string level) => Array.AsReadOnly(
        ExerciseCatalog.All
            .Where(exercise => string.Equals(exercise.Level, level, StringComparison.Ordinal))
            .Select(exercise => new ExerciseOption(exercise, $"{exercise.Title} · {exercise.Level}"))
            .ToArray());

    private static string FormatBytes(long bytes)
    {
        var value = bytes / 1_000_000_000d;
        return $"{value:F2} GB";
    }

    private bool Set<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value)) return false;
        field = value;
        OnPropertyChanged(propertyName);
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null) =>
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
}
