using Android.App;
using Android.Content;
using Android.OS;
using Android.Runtime;
using Avalonia.Android;
using WritingApp.Native;
using WritingApp.Shared;
using WritingApp.UI;

namespace WritingApp.Android;

[Application]
public sealed class AndroidApplication : AvaloniaAndroidApplication<App>, IModelDownloadHost
{
    public BackgroundModelDownloads Downloads { get; private set; } = null!;

    public AndroidApplication(IntPtr javaReference, JniHandleOwnership transfer)
        : base(javaReference, transfer) { }

    public override void OnCreate()
    {
        App.Configure(CreateServices(this));
        base.OnCreate();
    }

    internal AppServices CreateServices(Context context)
    {
        var root = context.FilesDir?.AbsolutePath
            ?? throw new InvalidOperationException("Android no proporcionó el directorio privado de la aplicación.");
        var modelDirectory = Path.Combine(root, "models");
        var sessionDirectory = Path.Combine(root, "sessions");
        Directory.CreateDirectory(modelDirectory);
        Directory.CreateDirectory(sessionDirectory);

        var memory = new ActivityManager.MemoryInfo();
        var activityManager = context.GetSystemService(Context.ActivityService) as ActivityManager
            ?? throw new InvalidOperationException("No se pudo consultar la memoria del dispositivo.");
        activityManager.GetMemoryInfo(memory);
        var storage = new StatFs(root);
        var architecture = Build.SupportedAbis?.FirstOrDefault()
            ?? System.Runtime.InteropServices.RuntimeInformation.ProcessArchitecture.ToString();
        var device = new DeviceProfile(
            "Android",
            architecture,
            memory.TotalMem,
            memory.AvailMem,
            storage.AvailableBytes,
            IsEmulator(),
            null);

        var nativeLibraryDirectory = context.ApplicationInfo?.NativeLibraryDir
            ?? throw new InvalidOperationException("Android no proporcionó el directorio de bibliotecas nativas.");

        var store = new ModelStore(modelDirectory);
        Downloads = new BackgroundModelDownloads(store, new AndroidDownloadTransport(context));
        return new AppServices(
            device,
            store,
            architecture == "arm64-v8a" && Build.VERSION.SdkInt >= BuildVersionCodes.P
                ? new AndroidMeasuredEngine(nativeLibraryDirectory, root,
                    (PowerManager)context.GetSystemService(Context.PowerService)!)
                : new NativeInferenceEngine(nativeLibraryDirectory),
            new SessionStore(sessionDirectory),
            Downloads);
    }

    private static bool IsEmulator()
    {
        var fingerprint = Build.Fingerprint ?? string.Empty;
        var hardware = Build.Hardware ?? string.Empty;
        var product = Build.Product ?? string.Empty;
        return fingerprint.Contains("generic", StringComparison.OrdinalIgnoreCase)
            || hardware.Contains("goldfish", StringComparison.OrdinalIgnoreCase)
            || hardware.Contains("ranchu", StringComparison.OrdinalIgnoreCase)
            || product.Contains("sdk", StringComparison.OrdinalIgnoreCase)
            || product.Contains("emulator", StringComparison.OrdinalIgnoreCase);
    }
}
