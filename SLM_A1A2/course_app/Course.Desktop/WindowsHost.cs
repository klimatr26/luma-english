using System.Runtime.InteropServices;
using System.Security.Cryptography;
using System.Text.Json;
using Course.Core;
using WritingApp.Desktop;
using WritingApp.Native;
using WritingApp.Shared;

namespace Course.Desktop;

public static partial class WindowsHost
{
    public static AppServices CreateServices() => BootstrapDesktop.CreateServices();
    public static string AppRoot => Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "WritingApp");
    public static DeviceProfile RefreshDevice(AppServices services)
    {
        var memory = new MemoryStatus { Length = (uint)Marshal.SizeOf<MemoryStatus>() };
        long freeDisk = services.Device.FreeStorageBytes;
        try { freeDisk = new DriveInfo(Path.GetPathRoot(services.ModelStore.CacheDirectory)!).AvailableFreeSpace; } catch (IOException) { }
        return GlobalMemoryStatusEx(ref memory)
            ? services.Device with { TotalMemoryBytes = (long)memory.TotalPhysical, AvailableMemoryBytes = (long)memory.AvailablePhysical, FreeStorageBytes = freeDisk }
            : services.Device with { FreeStorageBytes = freeDisk };
    }
    public static IsolatedInferenceEngine Worker() => new(AppContext.BaseDirectory, Path.Combine(AppRoot, "RuntimeLogs"));
    private static readonly Lazy<Task<string>> RuntimeHash = new(async () =>
    {
        using var hash = IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
        foreach (var file in Directory.EnumerateFiles(AppContext.BaseDirectory).Where(p => Path.GetFileName(p).StartsWith("ggml", StringComparison.Ordinal) ||
                     Path.GetFileName(p).StartsWith("llama", StringComparison.Ordinal) || Path.GetFileName(p).StartsWith("writing_", StringComparison.Ordinal)).Order(StringComparer.Ordinal))
        { await using var input = File.OpenRead(file); hash.AppendData(await SHA256.HashDataAsync(input)); }
        return Convert.ToHexStringLower(hash.GetHashAndReset());
    });
    public static async Task<HardwareCapabilities> ProbeAsync(CancellationToken ct)
    {
        var runtime = await RuntimeHash.Value.ConfigureAwait(false);
        var power = GetSystemPowerStatus(out var p) ? $"{p.AcLineStatus}/{p.SystemStatusFlag}" : "unknown";
        var catalog = string.Join('|', CourseModelCatalog.All.Select(m => $"{m.Id}/{m.Sha256}/{PortablePrompt.Hash(m)}/{JsonSerializer.Serialize(m.Sampling, AppJsonContext.Default.SamplingOptions)}"));
        var host = $"{BalancedModelAdvisor.Version}|{Environment.MachineName}|{RuntimeInformation.OSDescription}|{Environment.GetEnvironmentVariable("PROCESSOR_IDENTIFIER")}|{Environment.ProcessorCount}|{power}|{runtime}|{catalog}";
        try
        {
            await using var worker = Worker();
            var driver = await worker.DriverAsync(ct).ConfigureAwait(false);
            using var json = JsonDocument.Parse(driver);
            var name = json.RootElement.GetProperty("device").GetString();
            var fingerprint = json.RootElement.GetProperty("fingerprint").GetString();
            return new(true, $"Vulkan disponible: {name}. La carga parcial y la mejora real se confirman al calibrar.", BalancedModelAdvisor.ProfileKey(host + "|" + fingerprint));
        }
        catch (Exception e) when (e is not OperationCanceledException)
        { return new(false, "Vulkan no disponible en la sonda; se puede usar CPU. " + e.Message, BalancedModelAdvisor.ProfileKey(host + "|no-vulkan")); }
    }
    [StructLayout(LayoutKind.Sequential)] private struct MemoryStatus
    {
        public uint Length, Load;
        public ulong TotalPhysical, AvailablePhysical, TotalPage, AvailablePage, TotalVirtual, AvailableVirtual, AvailableExtended;
    }
    [LibraryImport("kernel32.dll")][return: MarshalAs(UnmanagedType.Bool)] private static partial bool GlobalMemoryStatusEx(ref MemoryStatus memory);
    [StructLayout(LayoutKind.Sequential)] private struct PowerStatus
    { public byte AcLineStatus, BatteryFlag, BatteryLifePercent, SystemStatusFlag; public uint BatteryLifeTime, BatteryFullLifeTime; }
    [LibraryImport("kernel32.dll")][return: MarshalAs(UnmanagedType.Bool)] private static partial bool GetSystemPowerStatus(out PowerStatus status);
}
