using Avalonia;
using Avalonia.Controls.ApplicationLifetimes;
using WritingApp.UI;

namespace WritingApp.Desktop;

internal static class Program
{
    [STAThread]
    public static void Main(string[] args)
    {
        App.Configure(BootstrapDesktop.CreateServices());
        BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
    }

    public static AppBuilder BuildAvaloniaApp() =>
        AppBuilder.Configure<App>()
            .UsePlatformDetect()
            .LogToTrace();
}
