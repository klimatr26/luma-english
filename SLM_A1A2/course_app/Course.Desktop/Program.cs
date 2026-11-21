using Avalonia;
using Course.Core;
using Course.UI;

namespace Course.Desktop;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        var dataIndex = Array.IndexOf(args, "--data-dir");
        var dataRoot = dataIndex >= 0 && dataIndex + 1 < args.Length ? Path.GetFullPath(args[dataIndex + 1]) : Path.Combine(WindowsHost.AppRoot, "Course");
        Directory.CreateDirectory(dataRoot);
        using var mutex = new Mutex(true, "Local\\WritingLocalCourse-" + BalancedModelAdvisor.ProfileKey(dataRoot)[..20], out var created);
        if (!created) return 1;
        var services = WindowsHost.CreateServices();
        using var store = new CourseStore(Path.Combine(dataRoot, "course.db"));
        var runtime = new CourseRuntime(services, WindowsHost.Worker, () => WindowsHost.RefreshDevice(services),
            WindowsHost.ProbeAsync, Path.Combine(WindowsHost.AppRoot, "adaptive-profiles", "course-auto-advice.json"));
        App.ViewModel = new(new EmbeddedCourse(), store, runtime);
        try
        {
            BuildAvaloniaApp().StartWithClassicDesktopLifetime(args);
            return 0;
        }
        catch (Exception error)
        {
            File.WriteAllText(Path.Combine(dataRoot, "startup-error.txt"), error.ToString()); return 2;
        }
        finally { services.ModelStore.Dispose(); }
    }
    public static AppBuilder BuildAvaloniaApp() => AppBuilder.Configure<App>().UsePlatformDetect().LogToTrace();
}
