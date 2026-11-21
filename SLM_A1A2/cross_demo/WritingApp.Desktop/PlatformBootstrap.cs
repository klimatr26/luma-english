using System.Runtime.InteropServices;
using WritingApp.Native;
using WritingApp.Shared;

namespace WritingApp.Desktop;

public static partial class BootstrapDesktop
{
    public static AppServices CreateServices()
    {
        var appRoot = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
            "WritingApp");
        var cacheFolder = Path.Combine(appRoot, "Models");
        var sessionFolder = Path.Combine(appRoot, "Sessions");
        Directory.CreateDirectory(cacheFolder);
        Directory.CreateDirectory(sessionFolder);

        var modelStore = new ModelStore(cacheFolder, FindExternalModelRoots());
        var sessions = new SessionStore(sessionFolder);
        var device = ReadDeviceProfile(cacheFolder);
        var engine = new AdaptiveInferenceEngine(
            _ => new IsolatedInferenceEngine(AppContext.BaseDirectory, Path.Combine(appRoot, "RuntimeLogs")),
            Path.Combine(appRoot, "adaptive-profiles"),
            () => $"{Environment.MachineName}|{RuntimeInformation.OSDescription}|{RuntimeInformation.ProcessArchitecture}|" +
                $"{Environment.GetEnvironmentVariable("PROCESSOR_IDENTIFIER")}|{ReadPowerMode()}");
        return new AppServices(device, modelStore, engine, sessions);
    }

    private static string[] FindExternalModelRoots()
    {
        foreach (var start in new[] { AppContext.BaseDirectory, Environment.CurrentDirectory })
        {
            for (var directory = new DirectoryInfo(Path.GetFullPath(start)); directory is not null; directory = directory.Parent)
            {
                var directManifest = Path.Combine(directory.FullName, "manifests", "experiment_manifest_120.json");
                var nestedLab = Path.Combine(directory.FullName, "SLM_A1A2");
                var nestedManifest = Path.Combine(nestedLab, "manifests", "experiment_manifest_120.json");
                var labRoot = File.Exists(directManifest)
                    ? directory.FullName
                    : File.Exists(nestedManifest)
                        ? nestedLab
                        : null;
                if (labRoot is null) continue;

                var models = Path.Combine(labRoot, "models");
                return Directory.Exists(models) ? [models] : [];
            }
        }

        return [];
    }

    private static DeviceProfile ReadDeviceProfile(string storagePath)
    {
        long totalMemory = 0;
        long availableMemory = 0;
        var status = new MemoryStatusEx { Length = (uint)Marshal.SizeOf<MemoryStatusEx>() };
        if (GlobalMemoryStatusEx(ref status))
        {
            totalMemory = ToLong(status.TotalPhysical);
            availableMemory = ToLong(status.AvailablePhysical);
        }
        else if (GetPhysicallyInstalledSystemMemory(out var totalKilobytes))
        {
            totalMemory = totalKilobytes > long.MaxValue / 1024 ? long.MaxValue : (long)totalKilobytes * 1024;
            availableMemory = totalMemory / 3;
        }
        else
        {
            var gcLimit = GC.GetGCMemoryInfo().TotalAvailableMemoryBytes;
            if (gcLimit > 0)
            {
                totalMemory = gcLimit;
                availableMemory = gcLimit / 2;
            }
        }

        long freeStorage = 0;
        var volume = Path.GetPathRoot(Path.GetFullPath(storagePath));
        if (!string.IsNullOrEmpty(volume))
        {
            try
            {
                var drive = new DriveInfo(volume);
                if (drive.IsReady) freeStorage = drive.AvailableFreeSpace;
            }
            catch (IOException)
            {
                freeStorage = 0;
            }
            catch (UnauthorizedAccessException)
            {
                freeStorage = 0;
            }
        }

        return new DeviceProfile("Windows", RuntimeInformation.ProcessArchitecture.ToString(),
            totalMemory, availableMemory, freeStorage);
    }

    private static long ToLong(ulong value) => value > long.MaxValue ? long.MaxValue : (long)value;

    private static string ReadPowerMode()
    {
        return OperatingSystem.IsWindows() && GetSystemPowerStatus(out var p)
            ? $"ac={p.AcLineStatus};saver={p.SystemStatusFlag}" : "power-unknown";
    }
    [LibraryImport("kernel32.dll")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetSystemPowerStatus(out SystemPowerStatus status);
    [StructLayout(LayoutKind.Sequential)]
    private struct SystemPowerStatus
    {
        public byte AcLineStatus, BatteryFlag, BatteryLifePercent, SystemStatusFlag;
        public uint BatteryLifeTime, BatteryFullLifeTime;
    }

    [LibraryImport("kernel32.dll", EntryPoint = "GlobalMemoryStatusEx")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GlobalMemoryStatusEx(ref MemoryStatusEx status);

    [LibraryImport("kernel32.dll", EntryPoint = "GetPhysicallyInstalledSystemMemory")]
    [return: MarshalAs(UnmanagedType.Bool)]
    private static partial bool GetPhysicallyInstalledSystemMemory(out ulong totalMemoryInKilobytes);

    [StructLayout(LayoutKind.Sequential)]
    private struct MemoryStatusEx
    {
        public uint Length;
        public uint MemoryLoad;
        public ulong TotalPhysical;
        public ulong AvailablePhysical;
        public ulong TotalPageFile;
        public ulong AvailablePageFile;
        public ulong TotalVirtual;
        public ulong AvailableVirtual;
        public ulong AvailableExtendedVirtual;
    }
}
