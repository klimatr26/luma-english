using System.Text;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Interactivity;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using WritingApp.Shared;

namespace WritingApp.UI;

public partial class MainView : UserControl
{
    private readonly MainWindowViewModel _viewModel;
    private readonly SemaphoreSlim _engineGate = new(1, 1);
    private CancellationTokenSource? _transferCancellation;
    private CancellationTokenSource? _loadCancellation;
    private CancellationTokenSource? _evaluationCancellation;
    private bool _transferActive;
    private bool _evaluationActive;
    private bool _unloadActive;
    private ModelEntry? _transferModel;
    private bool _transferIsImport;
    private TaskCompletionSource? _transferFinished;
    private EngineState? _loadedEngineState;
    private string? _loadedModelId;

    public MainView() : this(App.ConfiguredServices) { }

    public MainView(AppServices services)
    {
        InitializeComponent();
        _viewModel = new MainWindowViewModel(services);
        DataContext = _viewModel;
        if (services.Downloads.ContinuesInBackground)
        {
            AttachedToVisualTree += (_, _) => services.ModelStore.ModelPublished += OnModelPublished;
            DetachedFromVisualTree += (_, _) => services.ModelStore.ModelPublished -= OnModelPublished;
        }
        SizeChanged += OnContentSizeChanged;
        AdaptToWidth(Bounds.Width);
    }

    private void OnContentSizeChanged(object? sender, SizeChangedEventArgs e) => AdaptToWidth(e.NewSize.Width);

    private void OnModelPublished()
        => Dispatcher.UIThread.Post(_viewModel.NotifyModelStoreChanged);

    private void AdaptToWidth(double width)
    {
        if (ContentGrid is null) return;
        var narrow = width < 760;
        ContentGrid.ColumnDefinitions = narrow
            ? new ColumnDefinitions("*")
            : new ColumnDefinitions("1.05*,0.95*");
        ContentGrid.RowDefinitions = narrow
            ? new RowDefinitions("Auto,Auto")
            : new RowDefinitions("Auto");
        Grid.SetColumn(InputPanel, 0);
        Grid.SetRow(InputPanel, 0);
        Grid.SetColumn(ResultPanel, narrow ? 0 : 1);
        Grid.SetRow(ResultPanel, narrow ? 1 : 0);
        HeaderBadge.IsVisible = width >= 590;
    }

    private void OnModelChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (!_transferActive && _viewModel.SelectedModel is { } model)
        {
            _viewModel.DownloadProgressValue = 0;
            _viewModel.SetOperationMessage($"Seleccionado {model.Label}. La descarga/importación se ejecuta por separado de la carga del modelo.");
        }
    }

    private void OnBackendChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (_viewModel.SelectedBackend is { } backend && _viewModel.LastSession is null)
        {
            _viewModel.SetEvaluationStatus($"Backend seleccionado: {backend.Label}. Se aplicará al cargar el modelo.");
        }
    }

    private void OnLevelChanged(object? sender, SelectionChangedEventArgs e)
    {
        _viewModel.SetEvaluationStatus($"Nivel seleccionado: {_viewModel.SelectedLevel}.");
    }

    private void OnExerciseChanged(object? sender, SelectionChangedEventArgs e)
    {
        if (_viewModel.SelectedExercise is { } exercise)
            _viewModel.SetEvaluationStatus($"Ejercicio: {exercise.Label}.");
    }

    private async void OnDownloadClicked(object? sender, RoutedEventArgs e) =>
        await TransferSelectedModelAsync(importOnly: false);

    private async void OnImportClicked(object? sender, RoutedEventArgs e) =>
        await TransferSelectedModelAsync(importOnly: true);

    private async Task TransferSelectedModelAsync(bool importOnly)
    {
        if (_transferActive)
        {
            _viewModel.SetOperationMessage("Ya hay una descarga o importación en curso. Puedes cambiar la selección y cargar otro modelo; esta operación mantiene el modelo elegido al iniciarla.");
            return;
        }

        if (_viewModel.SelectedModel is not { } model)
        {
            _viewModel.SetOperationMessage("Selecciona un modelo.");
            return;
        }

        if (!importOnly && model.DownloadUrl is null)
        {
            _viewModel.SetOperationMessage("Este GGUF no tiene una descarga directa fijada. Usa Importar GGUF… y selecciona el archivo exacto.");
            return;
        }

        _transferActive = true;
        _transferModel = model;
        _transferIsImport = importOnly;
        _transferFinished = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        using var cancellation = new CancellationTokenSource();
        _transferCancellation = cancellation;
        _viewModel.DownloadProgressValue = 0;
        _viewModel.DownloadIsIndeterminate = true;
        try
        {
            var progress = new Progress<DownloadProgress>(value => _viewModel.SetDownloadProgress(model, value));
            if (importOnly)
            {
                var storageProvider = TopLevel.GetTopLevel(this)?.StorageProvider;
                if (storageProvider is null)
                {
                    _viewModel.SetOperationMessage("Este dispositivo no ofrece un selector de archivos para importar el GGUF.");
                    return;
                }

                var files = await storageProvider.OpenFilePickerAsync(new FilePickerOpenOptions
                {
                    Title = $"Importar GGUF verificado: {model.Name} {model.Quantization}",
                    AllowMultiple = false,
                    FileTypeFilter =
                    [
                        new FilePickerFileType("GGUF model") { Patterns = ["*.gguf"] },
                        new FilePickerFileType("Any file") { Patterns = ["*"] }
                    ]
                });
                if (files.Count == 0)
                {
                    _viewModel.SetOperationMessage("Importación cancelada. El modelo no fue modificado.");
                    return;
                }

                await using var input = await files[0].OpenReadAsync();
                await _viewModel.Services.ModelStore.ImportAsync(model, input, progress, cancellation.Token);
            }
            else
            {
                await _viewModel.Services.Downloads.EnsureAsync(model, progress, cancellation.Token);
            }

            _viewModel.DownloadIsIndeterminate = false;
            _viewModel.DownloadProgressValue = 100;
            _viewModel.SetOperationMessage($"{model.Label} está disponible y verificado. Cargarlo inicia la inferencia local.");
            _viewModel.NotifyModelStoreChanged();
        }
        catch (OperationCanceledException)
        {
            _viewModel.SetOperationMessage(importOnly
                ? "Importación detenida. No se publicó un archivo parcial."
                : _viewModel.Services.Downloads.ContinuesInBackground
                    ? "Se detuvo el seguimiento de la descarga. Si no pulsaste Cancelar transferencia, Android conserva su trabajo; vuelve a Descargar / reanudar."
                    : "Descarga detenida. Se conserva el parcial para reanudar; no se publicó un modelo incompleto.");
        }
        catch (Exception exception)
        {
            _viewModel.SetOperationMessage($"No se completó para {model.Name}: {exception.Message}");
        }
        finally
        {
            _transferCancellation = null;
            _transferActive = false;
            _transferModel = null;
            _transferFinished?.TrySetResult();
            _transferFinished = null;
        }
    }

    private async void OnCancelDownloadClicked(object? sender, RoutedEventArgs e)
    {
        if (_transferCancellation is null)
        {
            _viewModel.SetOperationMessage("No hay ninguna descarga o importación activa.");
            return;
        }

        var model = _transferModel;
        var isImport = _transferIsImport;
        _viewModel.SetOperationMessage("Cancelando descarga o importación…");
        _transferCancellation.Cancel();
        if(!isImport && model is not null)
        {
            try
            {
                await _viewModel.Services.Downloads.CancelAsync(model);
                _viewModel.SetOperationMessage(_viewModel.Services.Downloads.ContinuesInBackground
                    ? "Descarga cancelada explícitamente en Android; se retiró su archivo temporal."
                    : "Descarga detenida; el parcial se conserva para reanudar.");
            }
            catch(Exception exception)
            { _viewModel.SetOperationMessage($"No se pudo cancelar el trabajo del sistema: {exception.Message}"); }
        }
    }

    private async void OnLoadClicked(object? sender, RoutedEventArgs e)
    {
        if (_viewModel.IsLoadActive)
        {
            _viewModel.SetOperationMessage("La carga ya está en curso. Puedes cancelarla antes de volver a intentarlo.");
            return;
        }

        if (_viewModel.IsEvaluationActive || _unloadActive)
        {
            _viewModel.SetOperationMessage("Espera a que termine la operación actual antes de cargar un modelo.");
            return;
        }

        if (_viewModel.SelectedModel is not { } model || _viewModel.SelectedBackend is not { } backend)
        {
            _viewModel.SetOperationMessage("Selecciona un modelo.");
            return;
        }

        using var cancellation = new CancellationTokenSource();
        _loadCancellation = cancellation;
        _viewModel.IsLoadActive = true;
        var gateEntered = false;
        try
        {
            await _engineGate.WaitAsync(cancellation.Token);
            gateEntered = true;
            _viewModel.SetOperationMessage($"Buscando y verificando copias GGUF de {model.Name}…");
            var path = await _viewModel.Services.ModelStore.FindVerifiedAsync(model, cancellation.Token);
            if (path is null)
            {
                var progress = new Progress<DownloadProgress>(value => _viewModel.SetDownloadProgress(model, value));
                path = await _viewModel.Services.Downloads.RecoverCompletedAsync(model, progress, cancellation.Token);
            }
            if (path is null)
            {
                var hasUnverifiedCopy = _viewModel.Services.ModelStore.FindExisting(model) is not null;
                var message = hasUnverifiedCopy
                    ? "Ninguna copia existente coincide con el tamaño y SHA-256 fijados. Importa el GGUF exacto; la copia anterior de caché se preservará como no verificada."
                    : model.DownloadUrl is null
                        ? "Este GGUF es una conversión local. Usa Importar GGUF… y selecciona el archivo exacto verificado."
                        : "Aún no hay un GGUF listo. Usa Descargar / reanudar para ver el progreso o Importar GGUF…";
                _viewModel.SetOperationMessage(message);
                return;
            }

            cancellation.Token.ThrowIfCancellationRequested();
            await _viewModel.Services.Engine.UnloadAsync();
            _viewModel.SetLoaded(null, null);
            _loadedEngineState = null;
            _loadedModelId = null;

            _viewModel.SetOperationMessage(_viewModel.Services.Device.Platform == "Android" && backend.Preference == BackendPreference.AutoVulkanCpu
                ? $"Cargando {model.Label}. La primera carga compara CPU y Vulkan y guarda la elección…"
                : $"Cargando {model.Label} con {backend.Label}…");
            var engine = await _viewModel.Services.Engine.LoadAsync(
                model, path, backend.Preference, _viewModel.Services.DefaultContext, cancellation.Token);
            _viewModel.SetLoaded(model, engine);
            _loadedEngineState = engine;
            _loadedModelId = model.Id;
            var layers = engine.OffloadedLayers < 0 ? "capas GPU no medidas" : $"capas GPU informadas: {engine.OffloadedLayers}";
            _viewModel.SetOperationMessage($"Modelo cargado · {backend.Label} → backend efectivo: {engine.Backend} · {layers}.");
        }
        catch (OperationCanceledException)
        {
            if (_loadedEngineState is null) _viewModel.SetLoaded(null, null);
            var message = _loadedEngineState is null
                ? "Carga cancelada. Puedes volver a intentarlo cuando quieras."
                : $"Carga cancelada; {_viewModel.LoadedModelStatus}";
            _viewModel.SetOperationMessage(message);
        }
        catch (Exception exception)
        {
            if (_loadedEngineState is null) _viewModel.SetLoaded(null, null);
            var previous = _loadedEngineState is null ? string.Empty : $" El modelo anterior sigue cargado: {_viewModel.LoadedModelStatus}";
            _viewModel.SetOperationMessage($"No se pudo cargar el modelo seleccionado: {exception.Message}.{previous}");
        }
        finally
        {
            if (gateEntered) _engineGate.Release();
            _loadCancellation = null;
            _viewModel.IsLoadActive = false;
        }
    }

    private async void OnUnloadClicked(object? sender, RoutedEventArgs e)
    {
        if (_unloadActive || _viewModel.IsLoadActive || _viewModel.IsEvaluationActive)
        {
            _viewModel.SetOperationMessage("Espera a que termine la operación actual antes de liberar el modelo.");
            return;
        }

        _unloadActive = true;
        await _engineGate.WaitAsync();
        try
        {
            await _viewModel.Services.Engine.UnloadAsync();
            _viewModel.SetLoaded(null, null);
            _loadedEngineState = null;
            _loadedModelId = null;
            _viewModel.SetOperationMessage("Modelo liberado de memoria.");
        }
        catch (Exception exception)
        {
            _viewModel.SetOperationMessage($"No se pudo liberar el modelo: {exception.Message}");
        }
        finally
        {
            _unloadActive = false;
            _engineGate.Release();
        }
    }

    private void OnCorrectExampleClicked(object? sender, RoutedEventArgs e) => _viewModel.UseExample(correct: true);

    private void OnIncorrectExampleClicked(object? sender, RoutedEventArgs e) => _viewModel.UseExample(correct: false);

    private async void OnEvaluateClicked(object? sender, RoutedEventArgs e)
    {
        if (_evaluationActive || _viewModel.IsLoadActive || _unloadActive)
        {
            _viewModel.SetEvaluationStatus("Espera a que termine la carga o evaluación actual.");
            return;
        }

        if (_viewModel.SelectedModel is not { } selectedModel || _viewModel.SelectedBackend is not { } selectedBackend)
        {
            _viewModel.SetEvaluationStatus("Selecciona un modelo y carga el backend elegido.");
            return;
        }

        var exercise = _viewModel.CreateCurrentExercise();
        var studentText = _viewModel.StudentText;
        var maximumAttempts = _viewModel.MaximumAttempts;
        var loaded = _loadedEngineState;
        if (loaded is null || _loadedModelId != selectedModel.Id || loaded.Requested != selectedBackend.Preference)
        {
            _viewModel.SetEvaluationStatus("Carga el modelo y el backend que tienes seleccionados antes de evaluar.");
            return;
        }

        var exerciseId = exercise.Id;
        var taskText = exercise.Task;
        _evaluationActive = true;
        _viewModel.IsEvaluationActive = true;
        using var cancellation = new CancellationTokenSource();
        _evaluationCancellation = cancellation;
        var gateEntered = false;
        _viewModel.BeginEvaluation();
        try
        {
            await _engineGate.WaitAsync(cancellation.Token);
            gateEntered = true;
            var engine = _viewModel.Services.Engine;
            var progress = new InlineProgress<EvaluationAttempt>(attempt =>
            {
                if (Dispatcher.UIThread.CheckAccess()) _viewModel.AddAttempt(attempt);
                else Dispatcher.UIThread.InvokeAsync(() => _viewModel.AddAttempt(attempt)).GetAwaiter().GetResult();
            });
            var session = await EvaluationService.EvaluateAsync(
                _viewModel.Services, selectedModel, loaded, exercise, studentText,
                maximumAttempts, progress, cancellation.Token);
            if (_viewModel.InputsMatch(selectedModel.Id, selectedBackend.Preference,
                    exerciseId, taskText, studentText, maximumAttempts))
            {
                _viewModel.ApplySession(session);
            }
            else
            {
                _viewModel.ShowEvaluationFailure("Las entradas cambiaron durante la inferencia. La sesión de esa ejecución se guardó, pero no se muestra como resultado del texto actual.");
            }
            BringResultIntoView();
        }
        catch (OperationCanceledException)
        {
            _viewModel.SetEvaluationStatus("Evaluación cancelada. Las salidas RAW ya recibidas permanecen visibles.");
            BringResultIntoView();
        }
        catch (Exception exception)
        {
            _viewModel.ShowEvaluationFailure(exception.Message);
            BringResultIntoView();
        }
        finally
        {
            _evaluationCancellation = null;
            _evaluationActive = false;
            _viewModel.IsEvaluationActive = false;
            if (gateEntered) _engineGate.Release();
        }
    }

    private async void OnExportClicked(object? sender, RoutedEventArgs e)
    {
        if (_viewModel.LastSession is not { } session)
        {
            _viewModel.SetEvaluationStatus("Termina o cancela una evaluación con al menos un resultado antes de exportar la sesión.");
            return;
        }

        try
        {
            var storageProvider = TopLevel.GetTopLevel(this)?.StorageProvider;
            if (storageProvider is null)
            {
                _viewModel.SetEvaluationStatus("Este dispositivo no ofrece un selector de archivos para exportar JSON.");
                return;
            }

            var file = await storageProvider.SaveFilePickerAsync(new FilePickerSaveOptions
            {
                Title = "Exportar sesión de escritura",
                SuggestedFileName = $"writing-session-{DateTime.UtcNow:yyyyMMdd-HHmmss}",
                DefaultExtension = "json",
                FileTypeChoices = [new FilePickerFileType("JSON session") { Patterns = ["*.json"], MimeTypes = ["application/json"] }]
            });
            if (file is null)
            {
                _viewModel.SetEvaluationStatus("Exportación cancelada; la sesión local permanece intacta.");
                return;
            }

            var json = SessionStore.Serialize(session);
            var bytes = Encoding.UTF8.GetBytes(json);
            await using var output = await file.OpenWriteAsync();
            await SessionExportWriter.WriteAsync(output, bytes);
            _viewModel.SetEvaluationStatus("Sesión JSON exportada correctamente.");
        }
        catch (Exception exception)
        {
            _viewModel.SetEvaluationStatus($"No se pudo exportar la sesión: {exception.Message}");
        }
    }

    private void OnCancelEvaluationClicked(object? sender, RoutedEventArgs e)
    {
        if (_evaluationCancellation is { } evaluation)
        {
            _viewModel.SetEvaluationStatus("Cancelando evaluación…");
            evaluation.Cancel();
            return;
        }

        if (_loadCancellation is { } load)
        {
            _viewModel.SetOperationMessage("Cancelando carga del modelo…");
            load.Cancel();
            return;
        }

        _viewModel.SetEvaluationStatus("No hay una carga ni evaluación activa.");
    }

    private void BringResultIntoView() => Dispatcher.UIThread.Post(
        () => ResultPanel.BringIntoView(), DispatcherPriority.Background);

    public async Task DisposeServicesAsync()
    {
        _transferCancellation?.Cancel();
        _loadCancellation?.Cancel();
        _evaluationCancellation?.Cancel();
        try
        {
            if (_transferFinished is { } transfer) await transfer.Task;
            await _engineGate.WaitAsync();
            try
            {
                await _viewModel.Services.Engine.DisposeAsync();
                _viewModel.Services.ModelStore.Dispose();
            }
            finally
            {
                _engineGate.Release();
                _engineGate.Dispose();
            }
        }
        catch (ObjectDisposedException)
        {
            // The engine may already have closed its native handle during process teardown.
        }
    }

    private sealed class InlineProgress<T>(Action<T> report) : IProgress<T>
    {
        public void Report(T value) => report(value);
    }
}
