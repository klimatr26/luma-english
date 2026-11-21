using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using Avalonia.Markup.Xaml;
using WritingApp.Shared;

namespace WritingApp.UI;

public partial class App : Application
{
    private static AppServices? _services;
    internal static AppServices ConfiguredServices => _services ?? throw new InvalidOperationException("Configura App.Configure(AppServices) antes de crear la vista.");

    public static void Configure(AppServices services)
    {
        _services = services ?? throw new ArgumentNullException(nameof(services));
    }

    public override void Initialize() => AvaloniaXamlLoader.Load(this);

    public override void OnFrameworkInitializationCompleted()
    {
        if (ApplicationLifetime is IClassicDesktopStyleApplicationLifetime desktop)
        {
            var services = _services ?? throw new InvalidOperationException("Configura App.Configure(AppServices) antes de iniciar Avalonia.");
            desktop.MainWindow = new MainWindow(services);
        }
        else if (ApplicationLifetime is IActivityApplicationLifetime activity)
        {
            var services = _services ?? throw new InvalidOperationException("Configura App.Configure(AppServices) antes de iniciar Avalonia.");
            activity.MainViewFactory = () => new MainView(services);
        }
        else if (ApplicationLifetime is ISingleViewApplicationLifetime singleView)
        {
            var services = _services ?? throw new InvalidOperationException("Configura App.Configure(AppServices) antes de iniciar Avalonia.");
            singleView.MainView = new MainView(services);
        }

        base.OnFrameworkInitializationCompleted();
    }
}
