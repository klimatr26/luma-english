using System.ComponentModel;
using System.Text;
using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.Platform;
using Avalonia.Controls.Presenters;
using Avalonia.Layout;
using Avalonia.Markup.Xaml;
using Avalonia.Platform.Storage;
using Avalonia.Threading;
using Avalonia.VisualTree;
using WritingApp.Shared;

namespace Course.UI;

public partial class MainView : UserControl
{
    private CourseViewModel? _vm;
    private IInputPane? _inputPane;
    private bool _keyboardOpen;
    private bool? _summaryStacked;
    public MainView()
    {
        AvaloniaXamlLoader.Load(this);
        TopLevel.SetAutoSafeAreaPadding(this, true);
        this.FindControl<Grid>("SummaryMetrics")!.SizeChanged += (_, _) => AdaptSummary();
        SizeChanged += (_, _) => { Adapt(); RefreshInputPane(); };
        AttachedToVisualTree += (_, _) =>
        {
            _inputPane = TopLevel.GetTopLevel(this)?.InputPane;
            if (_inputPane is not null) _inputPane.StateChanged += InputPaneChanged;
            RefreshInputPane();
        };
        DetachedFromVisualTree += (_, _) => { if (_inputPane is not null) _inputPane.StateChanged -= InputPaneChanged; _inputPane = null; };
    }
    private void InputPaneChanged(object? sender, InputPaneStateEventArgs e) => ApplyInputPane(e.NewState == InputPaneState.Open, e.EndRect);
    private void RefreshInputPane() => ApplyInputPane(_inputPane?.State == InputPaneState.Open, _inputPane?.OccludedRect ?? default);
    public void ApplyInputPane(bool open, Rect occluded)
    {
        var top = TopLevel.GetTopLevel(this);
        var bottom = top is null ? Bounds.Height : this.TranslatePoint(new(0, Bounds.Height - Padding.Bottom), top)?.Y ?? Bounds.Height;
        // Account only for overlap: systems that already resize the window need no second inset.
        var overlap = open && occluded.Height > 0 && occluded.Bottom >= bottom - 1 ? Math.Max(0, bottom - occluded.Top) : 0;
        _keyboardOpen = overlap > 0;
        this.FindControl<Grid>("Shell")!.Margin = new Thickness(0, 0, 0, overlap);
        this.FindControl<Border>("BrandHeader")!.IsVisible = !_keyboardOpen;
        this.FindControl<Border>("StatusBar")!.IsVisible = !_keyboardOpen;
        this.FindControl<Border>("BottomNavigation")!.IsVisible = Bounds.Width < 760 && !_keyboardOpen;
        if (overlap > 0)
            Dispatcher.UIThread.Post(() =>
            {
                UpdateLayout();
                if (top?.FocusManager.GetFocusedElement() is TextBox text && text.GetVisualDescendants().OfType<TextPresenter>().FirstOrDefault() is { } presenter)
                {
                    var caret = presenter.CursorRectangle.Inflate(8);
                    presenter.BringIntoView(caret); UpdateLayout();
                    var page = this.FindControl<ScrollViewer>("PageScroll")!;
                    if (presenter.TranslatePoint(caret.Position, page) is { } position)
                    {
                        var shift = position.Y < 0 ? position.Y : Math.Max(0, position.Y + caret.Height - page.Viewport.Height);
                        page.Offset = new(page.Offset.X, Math.Max(0, page.Offset.Y + shift));
                    }
                }
            }, DispatcherPriority.Loaded);
    }
    public MainView(CourseViewModel vm, bool initialize = true) : this()
    {
        _vm = vm; DataContext = vm;
        AddHandler(TopLevel.BackRequestedEvent, (_, e) => e.Handled = vm.GoBack());
        AttachedToVisualTree += (_, _) => { vm.FileRequested = HandleFileAsync; vm.PropertyChanged += ViewModelChanged; };
        DetachedFromVisualTree += (_, _) => { vm.PropertyChanged -= ViewModelChanged; if (vm.FileRequested == HandleFileAsync) vm.FileRequested = null; };
        if (initialize)
        {
            var loaded = false;
            Loaded += async (_, _) => { if (loaded) return; loaded = true; await vm.InitializeAsync(); };
        }
    }
    private void ViewModelChanged(object? sender, PropertyChangedEventArgs args)
    {
        if (args.PropertyName is nameof(CourseViewModel.PageTitle) or nameof(CourseViewModel.ShowLesson) or nameof(CourseViewModel.ActivityNumber))
            this.FindControl<ScrollViewer>("PageScroll")!.Offset = default;
    }
    public void Adapt()
    {
        if (_vm is null) return;
        var width = Bounds.Width;
        var compact = width < 760;
        _vm.Adapt(width);
        this.FindControl<Grid>("Shell")!.ColumnDefinitions[0].Width = new(compact ? 0 : 220);
        this.FindControl<Border>("Sidebar")!.IsVisible = !compact;
        this.FindControl<Border>("BottomNavigation")!.IsVisible = compact && !_keyboardOpen;
        this.FindControl<StackPanel>("PageBody")!.Margin = new Thickness(compact ? 16 : 28, 24, compact ? 16 : 28, 32);
        var writing = this.FindControl<Grid>("WritingGrid")!;
        var editor = this.FindControl<Border>("WritingEditor")!;
        var result = this.FindControl<Border>("WritingResult")!;
        var sideBySide = width >= 1100;
        writing.ColumnDefinitions = ColumnDefinitions.Parse(sideBySide ? "*,*" : "*");
        Grid.SetColumn(result, sideBySide ? 1 : 0); Grid.SetRow(result, sideBySide ? 0 : 1);
        editor.Margin = sideBySide ? new Thickness(0, 0, 16, 0) : new Thickness(0, 0, 0, 16);
        this.FindControl<Grid>("HeroGrid")!.ColumnDefinitions[1].Width = compact ? new GridLength(0) : new GridLength(220);
    }
    private void AdaptSummary()
    {
        var summary = this.FindControl<Grid>("SummaryMetrics")!;
        if (summary.Bounds.Width <= 0) return;
        // The sidebar and page padding reduce usable space: use the card area, not the window.
        var stacked = summary.Bounds.Width < 900;
        if (_summaryStacked == stacked) return;
        _summaryStacked = stacked;
        summary.ColumnDefinitions = ColumnDefinitions.Parse(stacked ? "*" : "*,*,*");
        summary.RowDefinitions = RowDefinitions.Parse(stacked ? "Auto,Auto,Auto" : "Auto");
        var cards = new[] { "PracticeSummary", "AccuracySummary", "WritingSummary" };
        for (var i = 0; i < cards.Length; i++)
        {
            var card = this.FindControl<Border>(cards[i])!;
            Grid.SetRow(card, stacked ? i : 0);
            Grid.SetColumn(card, stacked ? 0 : i);
            card.Margin = stacked ? new Thickness(0, 0, 0, i < 2 ? 10 : 0) : new Thickness(0, 0, i < 2 ? 12 : 0, 0);
        }
    }
    private async Task HandleFileAsync(FileAction action)
    {
        var vm = _vm!;
        var storage = TopLevel.GetTopLevel(this)?.StorageProvider ?? throw new InvalidOperationException("No está disponible el selector de archivos del sistema.");
        if (action is FileAction.Restore or FileAction.ImportModel)
        {
            var isModel = action == FileAction.ImportModel;
            var files = await storage.OpenFilePickerAsync(new()
            {
                Title = isModel ? "Importar GGUF exacto del modelo seleccionado" : "Seleccionar respaldo del curso",
                AllowMultiple = false,
                FileTypeFilter = [new(isModel ? "Modelo GGUF" : "Respaldo del curso") { Patterns = [isModel ? "*.gguf" : "*.zip"] }]
            });
            if (files.Count == 0) return;
            if (!isModel && !await ConfirmRestoreAsync()) return;
            await using var stream = await files[0].OpenReadAsync();
            if (isModel) await vm.ImportAsync(stream); else await vm.RestoreAsync(stream);
            return;
        }
        var extension = action == FileAction.Backup ? "zip" : action == FileAction.HistoryCsv ? "csv" : "json";
        var file = await storage.SaveFilePickerAsync(new()
        {
            Title = action == FileAction.Backup ? "Guardar respaldo del curso" : "Exportar resultados locales",
            SuggestedFileName = $"luma-english-{action.ToString().ToLowerInvariant()}-{DateTime.Now:yyyyMMdd-HHmmss}.{extension}",
            DefaultExtension = extension,
            FileTypeChoices = [new(extension.ToUpperInvariant()) { Patterns = [$"*.{extension}"] }]
        });
        if (file is null) return;
        await using var output = await file.OpenWriteAsync();
        if (output.CanSeek) { output.SetLength(0); output.Position = 0; }
        switch (action)
        {
            case FileAction.Backup: await vm.ExportBackupAsync(output); break;
            case FileAction.HistoryCsv: await vm.ExportHistoryAsync(output, true); break;
            case FileAction.HistoryJson: await vm.ExportHistoryAsync(output, false); break;
            case FileAction.SessionJson:
                if (vm.LastSession is not { } session) throw new InvalidOperationException("La simulación no es una sesión de evaluación real.");
                await output.WriteAsync(Encoding.UTF8.GetBytes(SessionStore.Serialize(session))); break;
        }
    }
    private async Task<bool> ConfirmRestoreAsync()
    {
        var complete = new TaskCompletionSource<bool>();
        var confirm = new Button { Content = "Restaurar respaldo", Classes = { "primary" } };
        var cancel = new Button { Content = "Cancelar", Classes = { "secondary" } };
        var actions = new WrapPanel { Orientation = Orientation.Horizontal, Children = { confirm, cancel } };
        confirm.Margin = new(0, 0, 12, 8);
        var panel = new Border
        {
            Background = Avalonia.Media.Brushes.White, CornerRadius = new(18), Padding = new(26), MaxWidth = 460,
            HorizontalAlignment = HorizontalAlignment.Center, VerticalAlignment = VerticalAlignment.Center,
            Child = new StackPanel { Spacing = 18, Children =
            {
                new TextBlock { Text = "¿Restaurar tu progreso?", FontSize = 24, FontWeight = Avalonia.Media.FontWeight.SemiBold },
                new TextBlock { Text = "El respaldo reemplazará el progreso, los borradores y el historial actuales. Antes se guardará una copia automática del estado de este dispositivo. Los modelos descargados se conservan.", TextWrapping = Avalonia.Media.TextWrapping.Wrap }, actions
            } }
        };
        var overlay = new Border { Background = Avalonia.Media.Brush.Parse("#9915363C"), Padding = new(20), Child = panel };
        var shell = this.FindControl<Grid>("Shell")!;
        Grid.SetColumnSpan(overlay, 2); Grid.SetRowSpan(overlay, 2); overlay.ZIndex = 100; shell.Children.Add(overlay);
        confirm.Click += (_, _) => complete.TrySetResult(true); cancel.Click += (_, _) => complete.TrySetResult(false);
        try { return await complete.Task; }
        finally { shell.Children.Remove(overlay); }
    }
}
