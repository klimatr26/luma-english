using Avalonia;
using Avalonia.Controls;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;

namespace Course.UI;

public partial class App : Application
{
    public static CourseViewModel? ViewModel { get; set; }
    public MainView? ActiveView { get; private set; }
    private MainView CreateView(CourseViewModel vm) => ActiveView = new MainView(vm);
    public override void Initialize() => AvaloniaXamlLoader.Load(this);
    public override void OnFrameworkInitializationCompleted()
    {
        var vm = ViewModel ?? throw new InvalidOperationException("Faltan los servicios de la aplicación.");
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var window = new Window
            {
                Title = "Luma English · Inglés a tu ritmo", Width = 1320, Height = 900, MinWidth = 430, MinHeight = 560,
                WindowStartupLocation = WindowStartupLocation.CenterScreen, Content = CreateView(vm)
            };
            var closing = false;
            window.Closing += async (_, e) =>
            {
                if (closing) return;
                e.Cancel = true;
                try { await vm.DisposeAsync(); }
                finally { closing = true; window.Close(); }
            };
            desktop.MainWindow = window;
        }
        else if (ApplicationLifetime is IActivityApplicationLifetime activity) activity.MainViewFactory = () => CreateView(vm);
        else if (ApplicationLifetime is ISingleViewApplicationLifetime single) single.MainView = CreateView(vm);
        base.OnFrameworkInitializationCompleted();
    }
}
