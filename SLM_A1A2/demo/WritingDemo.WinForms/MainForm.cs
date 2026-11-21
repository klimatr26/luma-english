using System.Text.Json;
using WritingDemo.Core;

namespace WritingDemo.WinForms;

public sealed class MainForm : Form
{
    private static readonly Color Ink = Color.FromArgb(30, 58, 57);
    private static readonly Color Teal = Color.FromArgb(20, 105, 92);
    private static readonly Color Paper = Color.FromArgb(249, 250, 246);
    private readonly DemoPaths _paths;
    private readonly LlamaRuntime _runtime;
    private readonly ModelAssets _assets;
    private readonly IReadOnlyList<ModelSpec> _models;
    private readonly ComboBox _family = Combo("Modelo"), _quant = Combo("Cuantización"), _exercise = Combo("Ejercicio"), _level = Combo("Nivel"), _prompt = Combo("Modo de retroalimentación"), _backend = Combo("Aceleración");
    private readonly TextBox _modelDirectory = new() { Dock = DockStyle.Fill }, _serverPath = new() { Dock = DockStyle.Fill };
    private readonly TextBox _task = Multi("Consigna", false), _student = Multi("Tu respuesta", false), _corrected = Multi("Texto corregido", true), _feedback = Multi("Retroalimentación", true), _raw = Multi("JSON generado", true), _technical = Multi("Detalles de ejecución", true), _token = new() { UseSystemPasswordChar = true, Dock = DockStyle.Fill, AccessibleName = "Token Hugging Face opcional" };
    private readonly Label _modelInfo = new(), _state = new(), _verdict = new(), _format = new(), _example = new(), _stats = new();
    private readonly Button _load = Button("Cargar modelo"), _download = Button("Descargar / preparar"), _unload = Button("Liberar modelo"), _evaluate = Button("Evaluar respuesta"), _cancel = Button("Cancelar"), _export = Button("Guardar sesión");
    private readonly Button _goodExample = Button("Usar ejemplo correcto"), _badExample = Button("Usar ejemplo incorrecto"), _clear = Button("Escribir mi respuesta");
    private readonly ProgressBar _progress = new() { Dock = DockStyle.Fill, Height = 8, Style = ProgressBarStyle.Continuous };
    private readonly DataGridView _edits = new() { Dock = DockStyle.Fill, ReadOnly = true, AllowUserToAddRows = false, AllowUserToDeleteRows = false, RowHeadersVisible = false, AutoSizeColumnsMode = DataGridViewAutoSizeColumnsMode.Fill, BackgroundColor = Color.White, BorderStyle = BorderStyle.None, AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.AllCells, AccessibleName = "Cambios detectados" };
    private CancellationTokenSource? _operation;
    private TaskCompletionSource? _operationFinished;
    private bool _busy, _closing, _shutdownComplete, _editingProgrammatically;
    private string _inputKind = "free_text";
    private object? _lastSession;
    private readonly List<string> _runtimeLog = [];
    private static readonly JsonSerializerOptions PrettyJson = new() { WriteIndented = true };

    public MainForm(DemoPaths paths)
    {
        _paths = paths; _runtime = new(paths); _assets = new(paths); _models = ModelCatalog.Load(paths);
        Text = "Writing local · Laboratorio A1/A2"; StartPosition = FormStartPosition.CenterScreen;
        Size = new Size(1320, 900); MinimumSize = new Size(1080, 760); BackColor = Paper;
        Font = new Font("Segoe UI", 10); ForeColor = Ink; AutoScaleMode = AutoScaleMode.Dpi;
        BuildLayout();
        _modelDirectory.Text = paths.DefaultModelDirectory; _serverPath.Text = paths.DefaultServerPath;
        foreach (var group in _models.GroupBy(m => m.FamilyKey)) _family.Items.Add(new Choice(group.Key, group.First().DisplayName));
        foreach (var exercise in ExerciseCatalog.All) _exercise.Items.Add(new Choice(exercise.Id, $"{exercise.Level} · {exercise.Title}"));
        _level.Items.AddRange(["A1", "A2"]);
        _backend.Items.AddRange([new Choice(nameof(RuntimePreference.AutoVulkanCpu), "Auto Vulkan/CPU"),
            new Choice(nameof(RuntimePreference.Vulkan), "Vulkan"), new Choice(nameof(RuntimePreference.Cpu), "CPU"),
            new Choice(nameof(RuntimePreference.ExistingCuda), "CUDA anterior")]);
        _backend.SelectedIndexChanged += (_, _) => { ClearResult(); UpdateServerPath(); SetBusy(_busy); };
        _backend.SelectedIndex = 0;
        _family.SelectedIndexChanged += (_, _) => RefreshQuants();
        _quant.SelectedIndexChanged += (_, _) => { ClearResult(); RefreshModelInfo(); RefreshPrompts(); };
        _prompt.DisplayMember = nameof(PromptProfile.Label);
        _prompt.SelectedIndexChanged += (_, _) => ClearResult();
        _modelDirectory.TextChanged += (_, _) => RefreshModelInfo();
        _exercise.SelectedIndexChanged += (_, _) => SelectExercise();
        _student.TextChanged += (_, _) => { if (!_editingProgrammatically) { _inputKind = "free_text"; _example.Text = "Respuesta escrita o editada por el usuario"; } ClearResult(); };
        _task.TextChanged += (_, _) => ClearResult(); _level.SelectedIndexChanged += (_, _) => ClearResult();
        _goodExample.Click += (_, _) => UseExample(true); _badExample.Click += (_, _) => UseExample(false);
        _clear.Click += (_, _) => { _student.Clear(); _student.Focus(); };
        _load.Click += async (_, _) => await RunOperationAsync(LoadModelAsync);
        _download.Click += async (_, _) => await RunOperationAsync(DownloadModelAsync);
        _unload.Click += async (_, _) => await RunOperationAsync(async _ => { await _runtime.StopAsync(); _state.Text = "Modelo liberado de memoria."; RefreshModelInfo(); });
        _evaluate.Click += async (_, _) => await RunOperationAsync(EvaluateAsync);
        _cancel.Click += (_, _) => { _operation?.Cancel(); _state.Text = "Cancelando la operación…"; };
        _export.Click += (_, _) => ExportSession();
        _runtime.Log += line => { if (!IsDisposed && IsHandleCreated) BeginInvoke(() => { _runtimeLog.Add(line); if (_runtimeLog.Count > 250) _runtimeLog.RemoveAt(0); _technical.Text = string.Join(Environment.NewLine, _runtimeLog); }); };
        FormClosing += OnClosing;
        var defaultFamily = _models.FirstOrDefault(m => m.Id.StartsWith("11-", StringComparison.Ordinal))?.FamilyKey;
        _family.SelectedIndex = Math.Max(0, _family.Items.Cast<Choice>().ToList().FindIndex(x => x.Id == defaultFamily));
        if (_exercise.Items.Count > 0) _exercise.SelectedIndex = 0;
        _state.Text = "Elige un modelo y pulsa Cargar modelo. La inferencia se ejecuta en este equipo.";
        SetBusy(false);
    }

    private static ComboBox Combo(string accessibleName) => new() { DropDownStyle = ComboBoxStyle.DropDownList, Dock = DockStyle.Fill, AccessibleName = accessibleName };
    private static TextBox Multi(string name, bool readOnly) => new() { Multiline = true, ReadOnly = readOnly, ScrollBars = ScrollBars.Vertical, Dock = DockStyle.Fill, AccessibleName = name, BackColor = Color.White, BorderStyle = BorderStyle.FixedSingle, Margin = new Padding(0, 5, 0, 10) };
    private static Button Button(string text) => new() { Text = text, AutoSize = true, Height = 36, Padding = new Padding(8, 3, 8, 3), FlatStyle = FlatStyle.Flat, Margin = new Padding(0, 4, 8, 4), AccessibleName = text };
    private static Label Label(string text, float size = 10, bool bold = false) => new() { Text = text, AutoSize = true, Font = new Font("Segoe UI", size, bold ? FontStyle.Bold : FontStyle.Regular), Margin = new Padding(0, 2, 0, 2), ForeColor = Ink };
    private static FlowLayoutPanel Flow(params Control[] controls) { var flow = new FlowLayoutPanel { Dock = DockStyle.Fill, AutoSize = true, WrapContents = true, Margin = new Padding(0) }; flow.Controls.AddRange(controls); return flow; }
    private static void Row(TableLayoutPanel table, Control control, SizeType type, float height)
    { var row = table.RowCount++; table.RowStyles.Add(new RowStyle(type, height)); control.Dock = DockStyle.Fill; table.Controls.Add(control, 0, row); }
    private static TableLayoutPanel Stack()
    {
        var stack = new TableLayoutPanel { ColumnCount = 1, RowCount = 0, Dock = DockStyle.Fill, Padding = new Padding(18), Margin = new Padding(0), BackColor = Color.White };
        stack.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); return stack;
    }

    private void BuildLayout()
    {
        var shell = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 3, Margin = new Padding(0) };
        shell.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); shell.RowStyles.Add(new RowStyle(SizeType.Absolute, 92)); shell.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); shell.RowStyles.Add(new RowStyle(SizeType.Absolute, 58)); Controls.Add(shell);
        var header = new Panel { Dock = DockStyle.Fill, BackColor = Ink, Padding = new Padding(22, 12, 22, 10) };
        var title = Label("Writing local", 23, true); title.ForeColor = Color.White; title.Location = new Point(22, 9);
        var subtitle = Label("Inglés A1/A2 · Inferencia local · Demostración tecnológica"); subtitle.ForeColor = Color.FromArgb(210, 228, 217); subtitle.Location = new Point(25, 53); header.Controls.AddRange([title, subtitle]); shell.Controls.Add(header, 0, 0);
        var body = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Padding = new Padding(12), Margin = new Padding(0) };
        body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 48)); body.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 52)); shell.Controls.Add(body, 0, 1);
        var leftHost = new Panel { Dock = DockStyle.Fill, AutoScroll = true, Margin = new Padding(0, 0, 8, 0) };
        var left = Stack(); left.Dock = DockStyle.Top; left.Height = 690; leftHost.Controls.Add(left); body.Controls.Add(leftHost, 0, 0);
        Row(left, Label("1   Modelo en este equipo", 14, true), SizeType.Absolute, 34);
        var selectors = new TableLayoutPanel { ColumnCount = 3, RowCount = 2, Dock = DockStyle.Fill, Margin = new Padding(0) };
        selectors.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 45)); selectors.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 27)); selectors.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 28));
        selectors.Controls.Add(Label("Modelo"), 0, 0); selectors.Controls.Add(Label("Cuantización"), 1, 0); selectors.Controls.Add(Label("Aceleración"), 2, 0);
        selectors.Controls.Add(_family, 0, 1); selectors.Controls.Add(_quant, 1, 1); selectors.Controls.Add(_backend, 2, 1);
        Row(left, selectors, SizeType.Absolute, 66);
        _modelInfo.AutoSize = false; _modelInfo.ForeColor = Color.DimGray; _modelInfo.Font = new Font("Segoe UI", 9); _modelInfo.Padding = new Padding(0, 6, 0, 0);
        Row(left, _modelInfo, SizeType.Absolute, 52);
        _load.BackColor = Teal; _load.ForeColor = Color.White;
        Row(left, Flow(_load, _download, _unload), SizeType.Absolute, 48);
        Row(left, Label("Modo de retroalimentación"), SizeType.Absolute, 24);
        Row(left, _prompt, SizeType.Absolute, 34);
        var storage = new GroupBox { Text = "Carpetas y descargas", Dock = DockStyle.Fill, Padding = new Padding(10), AccessibleName = "Carpetas y descargas" };
        var folders = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 4 };
        folders.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); folders.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 90));
        folders.Controls.Add(Label("Carpeta de modelos"), 0, 0); var browse = Button("Buscar…"); browse.AccessibleName = "Buscar carpeta de modelos"; browse.Click += (_, _) => { using var dialog = new FolderBrowserDialog { InitialDirectory = _modelDirectory.Text, Description = "Carpeta raíz de los modelos" }; if (dialog.ShowDialog(this) == DialogResult.OK) _modelDirectory.Text = dialog.SelectedPath; }; folders.Controls.Add(_modelDirectory, 0, 1); folders.Controls.Add(browse, 1, 1);
        folders.Controls.Add(Label("Token Hugging Face (opcional; solo durante esta sesión)"), 0, 2); folders.SetColumnSpan(folders.GetControlFromPosition(0, 2)!, 2); folders.Controls.Add(_token, 0, 3); folders.SetColumnSpan(_token, 2); storage.Controls.Add(folders);
        Row(left, Label("2   Ejercicio y respuesta", 14, true), SizeType.Absolute, 34);
        var exercises = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 2, RowCount = 1, Margin = new Padding(0) }; exercises.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 80)); exercises.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 20)); exercises.Controls.Add(_exercise, 0, 0); exercises.Controls.Add(_level, 1, 0);
        Row(left, exercises, SizeType.Absolute, 34); Row(left, Label("Consigna"), SizeType.Absolute, 24); Row(left, _task, SizeType.Absolute, 54);
        Row(left, Flow(_goodExample, _badExample, _clear), SizeType.Absolute, 44);
        _example.ForeColor = Color.DimGray; _example.AutoSize = true; _example.Font = new Font("Segoe UI", 9); Row(left, _example, SizeType.Absolute, 24);
        Row(left, Label("Tu respuesta"), SizeType.Absolute, 24); Row(left, _student, SizeType.Percent, 100);
        _evaluate.BackColor = Teal; _evaluate.ForeColor = Color.White; _evaluate.Font = new Font("Segoe UI", 11, FontStyle.Bold);
        Row(left, Flow(_evaluate, _cancel), SizeType.Absolute, 48);
        var right = Stack(); right.Margin = new Padding(8, 0, 0, 0); body.Controls.Add(right, 1, 0);
        Row(right, Label("3   Evaluación del modelo", 14, true), SizeType.Absolute, 36);
        _verdict.Font = new Font("Segoe UI", 18, FontStyle.Bold); _verdict.Text = "Esperando una respuesta"; _verdict.AutoSize = false; Row(right, _verdict, SizeType.Absolute, 46);
        _format.AutoSize = false; _format.ForeColor = Color.DimGray; Row(right, _format, SizeType.Absolute, 48);
        var tabs = new TabControl { Dock = DockStyle.Fill };
        var result = new TabPage("Retroalimentación"); var resultStack = Stack(); resultStack.Padding = new Padding(12);
        Row(resultStack, Label("Texto corregido", 11, true), SizeType.Absolute, 30); Row(resultStack, _corrected, SizeType.Percent, 36);
        Row(resultStack, Label("Retroalimentación", 11, true), SizeType.Absolute, 30); Row(resultStack, _feedback, SizeType.Percent, 25);
        Row(resultStack, Label("Ediciones declaradas", 11, true), SizeType.Absolute, 30); Row(resultStack, _edits, SizeType.Percent, 39); result.Controls.Add(resultStack);
        var raw = new TabPage("JSON generado"); _raw.Font = new Font("Consolas", 10); raw.Controls.Add(_raw);
        var technical = new TabPage("Ejecución local"); var technicalStack = Stack(); technicalStack.Padding = new Padding(10); Row(technicalStack, storage, SizeType.Absolute, 150); Row(technicalStack, Label("llama-server.exe (b11457)"), SizeType.Absolute, 28); Row(technicalStack, _serverPath, SizeType.Absolute, 32); Row(technicalStack, _technical, SizeType.Percent, 100); technical.Controls.Add(technicalStack); tabs.TabPages.AddRange([result, raw, technical]);
        Row(right, tabs, SizeType.Percent, 100); _stats.ForeColor = Color.DimGray; Row(right, _stats, SizeType.Absolute, 26); Row(right, Flow(_export), SizeType.Absolute, 44);
        foreach (var name in new[] { "Original", "Corrección", "Tipo", "Explicación" }) _edits.Columns.Add(name, name);
        _edits.DefaultCellStyle.WrapMode = DataGridViewTriState.True;
        _edits.DefaultCellStyle.Alignment = DataGridViewContentAlignment.TopLeft;
        _edits.DefaultCellStyle.SelectionBackColor = Color.FromArgb(218, 237, 228);
        _edits.DefaultCellStyle.SelectionForeColor = Ink;
        _edits.Columns[0].FillWeight = 65; _edits.Columns[1].FillWeight = 65;
        _edits.Columns[2].FillWeight = 80; _edits.Columns[3].FillWeight = 190;
        var footer = new TableLayoutPanel { Dock = DockStyle.Fill, ColumnCount = 1, RowCount = 2, Padding = new Padding(18, 3, 18, 8) }; footer.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100)); footer.RowStyles.Add(new RowStyle(SizeType.Percent, 100)); footer.RowStyles.Add(new RowStyle(SizeType.Absolute, 6)); _state.AutoSize = false; _state.Dock = DockStyle.Fill; _state.Name = "Estado"; footer.Controls.Add(_state, 0, 0); footer.Controls.Add(_progress, 0, 1); shell.Controls.Add(footer, 0, 2);
    }

    private ModelSpec? SelectedModel => _quant.SelectedItem is Choice choice ? _models.FirstOrDefault(m => m.Id == choice.Id) : null;
    private RuntimePreference SelectedBackend => _backend.SelectedItem is Choice choice
        ? Enum.Parse<RuntimePreference>(choice.Id) : RuntimePreference.AutoVulkanCpu;
    private void UpdateServerPath()
    {
        _serverPath.Text = SelectedBackend == RuntimePreference.ExistingCuda ? _paths.DefaultServerPath
            : Path.Combine(_paths.LabDirectory, "tools", "llama.cpp", "b11457-vulkan", "llama-server.exe");
        _serverPath.ReadOnly = SelectedBackend != RuntimePreference.ExistingCuda;
    }
    private static string BackendSummary(RuntimeSelection? backend) => backend is null ? "Sin motor cargado"
        : backend.ActualBackend + (string.IsNullOrWhiteSpace(backend.Device) ? "" : " · " + backend.Device);
    private WritingExercise CurrentExercise => ExerciseCatalog.All.First(e => e.Id == ((Choice)_exercise.SelectedItem!).Id) with { Task = _task.Text.Trim(), Level = _level.Text };
    private void RefreshQuants()
    {
        if (_family.SelectedItem is not Choice family) return;
        _quant.Items.Clear(); var choices = _models.Where(m => m.FamilyKey == family.Id).ToList();
        foreach (var spec in choices) _quant.Items.Add(new Choice(spec.Id, spec.Quantization));
        _quant.SelectedIndex = Math.Max(0, choices.FindIndex(m => m.Quantization is "Q4_K_M" or "UD-Q4_K_XL"));
    }
    private void RefreshPrompts()
    {
        _prompt.Items.Clear();
        if (SelectedModel is not { } model) return;
        foreach (var profile in PromptCatalog.Load(_paths, model)) _prompt.Items.Add(profile);
        _prompt.SelectedIndex = _prompt.Items.Count - 1;
    }
    private void RefreshModelInfo()
    {
        if (SelectedModel is not { } model) return;
        string path;
        try { path = _assets.ResolvePath(model, _modelDirectory.Text); }
        catch (Exception ex) when (ex is ArgumentException or NotSupportedException or PathTooLongException)
        { _modelInfo.Text = "Indica una carpeta válida en Ejecución local."; SetBusy(_busy); return; }
        var available = File.Exists(path) ? "Archivo disponible" : "Archivo no encontrado";
        _modelInfo.Text = $"{available} · {model.ExpectedSize / 1e9:F2} GB · {model.LicenseLabel}\n{model.Note}";
        SetBusy(_busy);
    }
    private void SelectExercise()
    {
        if (_exercise.SelectedItem is not Choice choice) return;
        var exercise = ExerciseCatalog.All.First(e => e.Id == choice.Id);
        _task.Text = exercise.Task; _level.SelectedItem = exercise.Level; _student.Clear(); _example.Text = "Escribe tu respuesta o carga un ejemplo de demostración.";
    }
    private void UseExample(bool correct)
    {
        ClearResult();
        _editingProgrammatically = true;
        try { var exercise = CurrentExercise; _student.Text = correct ? exercise.CorrectExample : exercise.IncorrectExample; _inputKind = correct ? "demo_example_correct" : "demo_example_incorrect"; _example.Text = correct ? "Ejemplo preparado como correcto · el modelo lo evaluará" : "Ejemplo preparado con errores · el modelo lo evaluará"; }
        finally { _editingProgrammatically = false; }
    }
    private void SetBusy(bool value)
    {
        _busy = value; foreach (var c in new Control[] { _family, _quant, _backend, _prompt, _modelDirectory, _token, _serverPath, _exercise, _level, _task, _student, _goodExample, _badExample, _clear, _load, _download }) c.Enabled = !value && !_closing;
        _cancel.Enabled = value && !_closing; _unload.Enabled = !value && !_closing && _runtime.IsLoaded;
        _evaluate.Enabled = !value && !_closing && _runtime.IsLoaded && _runtime.LoadedModel?.Id == SelectedModel?.Id && _runtime.ActiveBackend?.Requested == SelectedBackend;
        _export.Enabled = !value && !_closing && _lastSession is not null;
        _progress.Style = value ? ProgressBarStyle.Marquee : ProgressBarStyle.Continuous; if (!value) _progress.Value = 0;
    }
    private async Task RunOperationAsync(Func<CancellationToken, Task> action)
    {
        if (_busy || _closing) return;
        var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        _operationFinished = completion;
        _operation = new CancellationTokenSource(); SetBusy(true);
        try { await action(_operation.Token); }
        catch (OperationCanceledException) { await _runtime.StopAsync(); _state.Text = "Operación cancelada. Puedes volver a cargar el modelo."; }
        catch (Exception ex) { _state.Text = "No se completó: " + ex.Message; _verdict.Text = "⚠ Problema de ejecución"; _verdict.ForeColor = Color.DarkOrange; }
        finally { _operation.Dispose(); _operation = null; SetBusy(false); completion.TrySetResult(); }
    }
    private IProgress<TransferProgress> Progress() => new Progress<TransferProgress>(p =>
    {
        _state.Text = p.Status;
        if (p.TotalBytes is > 0) { _progress.Style = ProgressBarStyle.Continuous; _progress.Value = (int)Math.Clamp(100d * p.BytesReceived / p.TotalBytes.Value, 0, 100); }
    });
    private async Task LoadModelAsync(CancellationToken ct)
    {
        var model = SelectedModel ?? throw new InvalidOperationException("Selecciona un modelo.");
        var path = _assets.ResolvePath(model, _modelDirectory.Text);
        await _runtime.StopAsync(); ClearResult(); _runtimeLog.Clear(); _technical.Clear();
        _state.Text = "Comprobando tamaño y SHA-256 del modelo…";
        if (!await _assets.VerifyAsync(model, path, Progress(), ct))
            throw new InvalidDataException("El archivo no está disponible o no coincide con el modelo seleccionado. Revisa la carpeta o usa Descargar / preparar.");
        _state.Text = "Preparando aceleración y cargando modelo. Thinking desactivado…";
        await _runtime.LoadAsync(model, path, _serverPath.Text.Trim(), ct, SelectedBackend);
        var backend = _runtime.ActiveBackend;
        _state.Text = $"Listo · {model.DisplayName} {model.Quantization} · {BackendSummary(backend)}";
        if (backend?.FallbackReason is not null) _state.Text += " · CPU como alternativa a Vulkan; detalle en Ejecución local.";
    }
    private async Task DownloadModelAsync(CancellationToken ct)
    {
        var model = SelectedModel ?? throw new InvalidOperationException("Selecciona un modelo.");
        var target = _assets.ResolvePath(model, _modelDirectory.Text);
        if (File.Exists(target))
        {
            if (!await _assets.VerifyAsync(model, target, Progress(), ct))
                throw new InvalidDataException("El archivo existente no coincide con el modelo esperado. Se conserva intacto; elige otra carpeta para obtener una copia válida.");
            _state.Text = "El modelo ya está disponible y su hash es correcto. No se descargó de nuevo."; return;
        }
        await _assets.DownloadAsync(model, _modelDirectory.Text, Progress(), ct, string.IsNullOrWhiteSpace(_token.Text) ? null : _token.Text);
        RefreshModelInfo(); _state.Text = "Modelo preparado y verificado. Pulsa Cargar modelo para usarlo.";
    }
    private async Task EvaluateAsync(CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(_student.Text) || string.IsNullOrWhiteSpace(_task.Text)) throw new InvalidOperationException("Escribe una consigna y una respuesta.");
        if (_student.Text.Length > 4000 || _task.Text.Length > 1000) throw new InvalidOperationException("Para esta demostración usa hasta 4000 caracteres de respuesta y 1000 de consigna.");
        var exercise = CurrentExercise; var text = _student.Text; var model = _runtime.LoadedModel!;
        ClearResult(); _state.Text = "El modelo está evaluando tu respuesta…";
        var profile = _prompt.SelectedItem as PromptProfile ?? throw new InvalidOperationException("Selecciona el modo de retroalimentación.");
        var generated = await _runtime.GenerateAsync(exercise, text, ct, profile.Id);
        var parsed = FeedbackParser.Parse(generated.Content, text);
        _raw.Text = generated.Content.ReplaceLineEndings(Environment.NewLine);
        _format.Text = parsed.Status switch { "STRICT" => "JSON válido y contrato correcto.", "RECOVERED" => "JSON recuperado de una envoltura · no fue JSON estricto.", "INCONSISTENT" => "JSON interpretado, pero sus campos se contradicen.", "INVALID_SCHEMA" => "Se recibió JSON, pero no cumple el contrato esperado.", _ => "No se pudo interpretar un único JSON válido." };
        if (parsed.Error is not null) _format.Text += " " + parsed.Error;
        if (parsed.Value is { } result)
        {
            _corrected.Text = result.CorrectedText.ReplaceLineEndings(Environment.NewLine);
            _feedback.Text = string.IsNullOrWhiteSpace(result.Feedback) ? "El modelo no añadió comentarios en la retroalimentación." : result.Feedback.ReplaceLineEndings(Environment.NewLine);
            _feedback.ForeColor = string.IsNullOrWhiteSpace(result.Feedback) ? Color.DimGray : Ink;
            foreach (var edit in result.Errors) _edits.Rows.Add(edit.Original, edit.Correction, edit.Type, edit.Explanation);
            if (parsed.Status is "STRICT" or "RECOVERED") { _verdict.Text = result.IsCorrect ? "✓ El modelo indica: correcto" : "✕ El modelo indica: con errores"; _verdict.ForeColor = result.IsCorrect ? Teal : Color.Firebrick; }
            else { _verdict.Text = "⚠ Respuesta incoherente"; _verdict.ForeColor = Color.DarkOrange; }
        }
        else { _verdict.Text = "⚠ Problema al interpretar el JSON"; _verdict.ForeColor = Color.DarkOrange; }
        var backend = _runtime.ActiveBackend;
        _stats.Text = $"{generated.ElapsedSeconds:F2} s · fin: {generated.FinishReason} · {backend?.ActualBackend ?? "sin motor"}";
        if (generated.FinishReason == "length") _format.Text += " Se alcanzó el límite de salida: la respuesta puede estar truncada.";
        _lastSession = new { schema_version = "writing_local_demo/1.2", kind = "INTERACTIVE_DEMONSTRATION_NOT_BENCHMARK", date_utc = DateTimeOffset.UtcNow, model_id = model.Id, model.ExpectedSha256, model.Quantization, runtime_backend = new { requested = backend?.Requested.ToString(), actual = backend?.ActualBackend, device = backend?.Device, offloaded_layers = backend?.OffloadedLayers, fallback_reason = backend?.FallbackReason, build = backend?.RuntimeBuild, commit = backend?.RuntimeCommit, server_path = backend?.ServerPath }, prompt_profile = generated.PromptProfileId, system_prompt_sha256 = generated.SystemPromptSha256, prompt_validation_status = profile.Id == "benchmark-base" ? "EXPERIMENTAL_BASELINE" : "PROPOSED_NOT_EMPIRICALLY_VALIDATED", exercise_id = exercise.Id, exercise.Level, task = exercise.Task, student_text = text, input_kind = _inputKind, generation = model.Generation, thinking = "disabled", output = generated, interpretation = parsed, automatic_verdict_is_model_claim = true };
        _state.Text = $"Evaluación terminada · {BackendSummary(backend)}. La marca muestra el juicio del modelo.";
        Directory.CreateDirectory(_paths.SessionDirectory);
        var name = $"session_{DateTime.UtcNow:yyyyMMdd_HHmmss_fff}_{Guid.NewGuid():N}.json";
        await File.WriteAllTextAsync(Path.Combine(_paths.SessionDirectory, name), JsonSerializer.Serialize(_lastSession, PrettyJson), ct);
    }
    private void ClearResult()
    {
        _lastSession = null; _verdict.Text = "Esperando una respuesta"; _verdict.ForeColor = Ink; _format.Text = "La salida original estará disponible en la pestaña JSON generado."; _corrected.Clear(); _feedback.Clear(); _raw.Clear(); _edits.Rows.Clear(); _stats.Text = ""; _export.Enabled = false;
    }
    private void ExportSession()
    {
        if (_lastSession is null) return;
        using var dialog = new SaveFileDialog { Filter = "Sesión de demostración (*.json)|*.json", FileName = $"writing_demo_{DateTime.Now:yyyyMMdd_HHmmss}.json" };
        if (dialog.ShowDialog(this) == DialogResult.OK)
        {
            try { File.WriteAllText(dialog.FileName, JsonSerializer.Serialize(_lastSession, PrettyJson)); }
            catch (Exception ex) when (ex is IOException or UnauthorizedAccessException)
            { _state.Text = "No se pudo guardar la sesión: " + ex.Message; }
        }
    }
    private async void OnClosing(object? sender, FormClosingEventArgs e)
    {
        if (_shutdownComplete) return;
        e.Cancel = true;
        if (_closing) return;
        _closing = true; _operation?.Cancel(); SetBusy(_busy);
        if (_operationFinished is { } completion) await completion.Task;
        await _runtime.DisposeAsync(); _assets.Dispose(); _shutdownComplete = true; Close();
    }
    private sealed record Choice(string Id, string Caption) { public override string ToString() => Caption; }
}
