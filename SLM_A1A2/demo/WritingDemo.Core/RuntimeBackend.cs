using System.Diagnostics;
using System.Security.Cryptography;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace WritingDemo.Core;

/// <summary>Chooses which verified llama.cpp runtime package to start.</summary>
public enum RuntimePreference
{
    AutoVulkanCpu,
    Vulkan,
    Cpu,
    ExistingCuda
}

/// <summary>Describes the runtime which is currently serving requests.</summary>
public sealed record RuntimeSelection(
    RuntimePreference Requested,
    string ActualBackend,
    string? Device,
    string? FallbackReason,
    string RuntimeBuild,
    string RuntimeCommit,
    string ServerPath,
    int? OffloadedLayers = null);

internal sealed record BackendSelectionDecision(string ActualBackend, string? Device, string? FallbackReason);

internal sealed class VulkanProbeFailureException(string message, Exception? innerException = null)
    : Exception(message, innerException);

internal sealed class VulkanStartupFailureException(string message, Exception? innerException = null)
    : Exception(message, innerException);

/// <summary>
/// Keeps probe/startup fallback policy separate from process management so the
/// policy can be checked with fake probes and launches.
/// </summary>
internal static class BackendSelectionPolicy
{
    private static readonly Regex VulkanDeviceLine = new(
        @"^\s*(?<device>Vulkan[0-9]+):\s+\S.*$",
        RegexOptions.Multiline | RegexOptions.CultureInvariant | RegexOptions.Compiled);

    public static bool TryParsePreference(string? value, out RuntimePreference preference)
    {
        preference = default;
        if (string.IsNullOrWhiteSpace(value)) return false;
        return Enum.TryParse(value.Trim(), ignoreCase: true, out preference)
            && Enum.IsDefined(preference);
    }

    public static IReadOnlyList<string> ParseVulkanDevices(string output)
    {
        ArgumentNullException.ThrowIfNull(output);
        return VulkanDeviceLine.Matches(output)
            .Select(match => match.Groups["device"].Value)
            .Distinct(StringComparer.Ordinal)
            .ToArray();
    }

    public static async Task<BackendSelectionDecision> StartAsync(
        RuntimePreference preference,
        Func<CancellationToken, Task<string>> probeVulkanDevices,
        Func<string, CancellationToken, Task> startVulkan,
        Func<CancellationToken, Task> startCpu,
        CancellationToken cancellationToken)
    {
        ArgumentNullException.ThrowIfNull(probeVulkanDevices);
        ArgumentNullException.ThrowIfNull(startVulkan);
        ArgumentNullException.ThrowIfNull(startCpu);
        cancellationToken.ThrowIfCancellationRequested();

        if (preference == RuntimePreference.Cpu)
        {
            await startCpu(cancellationToken).ConfigureAwait(false);
            return new BackendSelectionDecision("CPU", null, null);
        }

        if (preference is not (RuntimePreference.AutoVulkanCpu or RuntimePreference.Vulkan))
            throw new ArgumentOutOfRangeException(nameof(preference), "Este selector acepta Vulkan/CPU, no el runtime CUDA heredado.");

        string probeOutput;
        try
        {
            probeOutput = await probeVulkanDevices(cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (VulkanProbeFailureException ex) when (preference == RuntimePreference.AutoVulkanCpu)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var reason = $"No se pudo consultar Vulkan: {ex.Message}";
            await startCpu(cancellationToken).ConfigureAwait(false);
            return new BackendSelectionDecision("CPU", null, reason);
        }

        var devices = ParseVulkanDevices(probeOutput);
        if (devices.Count == 0)
        {
            if (preference == RuntimePreference.Vulkan)
                throw new InvalidOperationException("El runtime Vulkan verificado no informó ningún dispositivo Vulkan disponible.");

            const string noDeviceReason = "El runtime Vulkan verificado no informó ningún dispositivo Vulkan; se usará CPU.";
            await startCpu(cancellationToken).ConfigureAwait(false);
            return new BackendSelectionDecision("CPU", null, noDeviceReason);
        }

        var selectedDevice = devices[0];
        try
        {
            await startVulkan(selectedDevice, cancellationToken).ConfigureAwait(false);
            return new BackendSelectionDecision("Vulkan", selectedDevice, null);
        }
        catch (OperationCanceledException) when (cancellationToken.IsCancellationRequested)
        {
            throw;
        }
        catch (LlamaRateLimitException)
        {
            throw;
        }
        catch (InvalidDataException)
        {
            throw;
        }
        catch (VulkanStartupFailureException ex) when (preference == RuntimePreference.AutoVulkanCpu)
        {
            cancellationToken.ThrowIfCancellationRequested();
            var reason = $"No se pudo iniciar Vulkan en {selectedDevice}: {ex.Message}";
            await startCpu(cancellationToken).ConfigureAwait(false);
            return new BackendSelectionDecision("CPU", null, reason);
        }
        catch (VulkanStartupFailureException ex)
        {
            throw new InvalidOperationException($"Vulkan no pudo demostrar offload GPU para {selectedDevice}: {ex.Message}", ex);
        }
    }
}

internal static class RuntimePackageVerifier
{
    public const string ManifestRelativePath = "manifests/demo_vulkan_runtime_20261109.json";
    public const string ExpectedManifestSha256 = "0a88187f51d3d37ce6337372740d0911bca177690073fce48f2e917382e3bec2";
    public const string ExpectedServerRelativePath = "tools/llama.cpp/b11457-vulkan/llama-server.exe";
    public const string ExpectedBuild = "b11457";
    public const string ExpectedCommit = "5ad1c5da0ad7f6176256b823925aad19134f0263";
    private const string ExpectedSchema = "writing_demo.runtime_package/1.0";
    private const string ExpectedBackend = "vulkan";

    public static async Task<string> VerifyVulkanPackageAsync(DemoPaths paths, CancellationToken cancellationToken)
    {
        var manifestPath = Path.Combine(paths.LabDirectory, ManifestRelativePath.Replace('/', Path.DirectorySeparatorChar));
        if (!File.Exists(manifestPath))
            throw new FileNotFoundException("No se encontró el manifiesto fijado del runtime Vulkan.", manifestPath);

        EnsureNoReparsePointBetween(paths.LabDirectory, manifestPath);
        await using var manifestStream = new FileStream(manifestPath, FileMode.Open, FileAccess.Read, FileShare.Read,
            64 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
        var manifestHash = Convert.ToHexString(await SHA256.HashDataAsync(manifestStream, cancellationToken).ConfigureAwait(false)).ToLowerInvariant();
        if (!string.Equals(manifestHash, ExpectedManifestSha256, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException("El manifiesto del runtime Vulkan no coincide con la versión fijada.");
        manifestStream.Position = 0;
        using var manifest = await JsonDocument.ParseAsync(manifestStream, cancellationToken: cancellationToken).ConfigureAwait(false);
        var root = manifest.RootElement;
        if (root.ValueKind != JsonValueKind.Object
            || GetRequiredString(root, "schema_version") != ExpectedSchema
            || GetRequiredString(root, "backend") != ExpectedBackend
            || GetRequiredString(root, "build") != ExpectedBuild
            || GetRequiredString(root, "commit") != ExpectedCommit
            || NormalizeRelativePath(GetRequiredString(root, "server_path")) != ExpectedServerRelativePath)
            throw new InvalidDataException("Los metadatos del manifiesto Vulkan no coinciden con el paquete b11457 fijado.");

        if (!root.TryGetProperty("files", out var files) || files.ValueKind != JsonValueKind.Array || files.GetArrayLength() == 0)
            throw new InvalidDataException("El manifiesto Vulkan no contiene una lista files válida.");

        var packageRoot = ResolveLabPath(paths.LabDirectory, "tools/llama.cpp/b11457-vulkan");
        EnsureNoReparsePointBetween(paths.LabDirectory, packageRoot);
        if (!Directory.Exists(packageRoot))
            throw new DirectoryNotFoundException("No se encontró el directorio del paquete Vulkan verificado.");
        var seen = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var serverPath = ResolveLabPath(paths.LabDirectory, ExpectedServerRelativePath);
        var sawServer = false;

        foreach (var record in files.EnumerateArray())
        {
            cancellationToken.ThrowIfCancellationRequested();
            if (record.ValueKind != JsonValueKind.Object)
                throw new InvalidDataException("El manifiesto Vulkan contiene un registro de archivo inválido.");
            var relative = NormalizeRelativePath(GetRequiredString(record, "path"));
            var fullPath = ResolveLabPath(paths.LabDirectory, relative);
            if (!IsWithinDirectory(packageRoot, fullPath))
                throw new InvalidDataException($"El archivo Vulkan {relative} sale del directorio del paquete fijado.");
            if (!seen.Add(fullPath))
                throw new InvalidDataException($"El manifiesto Vulkan repite el archivo {relative}.");

            var expectedSize = record.TryGetProperty("size_bytes", out var sizeElement)
                && sizeElement.TryGetInt64(out var size) ? size : -1;
            var expectedHash = GetRequiredString(record, "sha256");
            if (expectedSize < 0 || expectedHash.Length != 64 || !expectedHash.All(Uri.IsHexDigit))
                throw new InvalidDataException($"El registro de {relative} no contiene tamaño o SHA-256 válido.");

            EnsureNoReparsePointBetween(paths.LabDirectory, fullPath);
            if (!File.Exists(fullPath))
                throw new FileNotFoundException($"No se encontró el archivo Vulkan {relative}.", fullPath);
            var info = new FileInfo(fullPath);
            if (info.Length != expectedSize)
                throw new InvalidDataException($"El tamaño de {relative} no coincide con el manifiesto ({info.Length} != {expectedSize}).");
            await using var stream = new FileStream(fullPath, FileMode.Open, FileAccess.Read, FileShare.Read,
                1024 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
            var actualHash = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken).ConfigureAwait(false)).ToLowerInvariant();
            if (!string.Equals(actualHash, expectedHash, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"El SHA-256 de {relative} no coincide con el manifiesto Vulkan.");
            if (string.Equals(fullPath, serverPath, StringComparison.OrdinalIgnoreCase)) sawServer = true;
        }

        if (!sawServer)
            throw new InvalidDataException("El manifiesto Vulkan no incluye el llama-server fijado.");
        ValidateBinaryInventory(packageRoot, seen);
        return serverPath;
    }

    internal static void ValidateBinaryInventory(string packageRoot, IEnumerable<string> manifestPaths)
    {
        var manifestSet = new HashSet<string>(manifestPaths
            .Where(IsBinaryPath)
            .Select(Path.GetFullPath), StringComparer.OrdinalIgnoreCase);
        var actualSet = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var pending = new Stack<string>();
        pending.Push(Path.GetFullPath(packageRoot));
        while (pending.TryPop(out var directory))
        {
            foreach (var entry in Directory.EnumerateFileSystemEntries(directory))
            {
                var attributes = File.GetAttributes(entry);
                if ((attributes & FileAttributes.ReparsePoint) != 0)
                    throw new InvalidDataException($"El paquete Vulkan no puede contener enlaces o reparse points: {entry}.");
                if ((attributes & FileAttributes.Directory) != 0)
                {
                    pending.Push(entry);
                    continue;
                }

                var extension = Path.GetExtension(entry);
                if (string.Equals(extension, ".dll", StringComparison.OrdinalIgnoreCase)
                    || string.Equals(extension, ".exe", StringComparison.OrdinalIgnoreCase))
                    actualSet.Add(Path.GetFullPath(entry));
            }
        }

        var unlisted = actualSet.Except(manifestSet, StringComparer.OrdinalIgnoreCase).ToArray();
        if (unlisted.Length > 0)
            throw new InvalidDataException($"El directorio del paquete contiene binarios fuera del manifiesto: {string.Join(", ", unlisted.Select(Path.GetFileName))}.");
        var missing = manifestSet.Except(actualSet, StringComparer.OrdinalIgnoreCase).ToArray();
        if (missing.Length > 0)
            throw new InvalidDataException($"El manifiesto incluye binarios que no están en el paquete: {string.Join(", ", missing.Select(Path.GetFileName))}.");
    }

    private static bool IsBinaryPath(string path) =>
        string.Equals(Path.GetExtension(path), ".dll", StringComparison.OrdinalIgnoreCase)
        || string.Equals(Path.GetExtension(path), ".exe", StringComparison.OrdinalIgnoreCase);

    internal static string NormalizeRelativePath(string path)
    {
        if (string.IsNullOrWhiteSpace(path) || Path.IsPathRooted(path))
            throw new InvalidDataException("El manifiesto contiene una ruta vacía o absoluta.");
        var normalized = path.Replace('\\', '/');
        if (normalized.StartsWith("/", StringComparison.Ordinal)
            || normalized.Split('/').Any(segment => segment is "" or "." or ".."))
            throw new InvalidDataException("El manifiesto contiene una ruta relativa insegura.");
        return normalized;
    }

    internal static string ResolveLabPath(string labDirectory, string relativePath)
    {
        var normalized = NormalizeRelativePath(relativePath);
        var fullLab = Path.GetFullPath(labDirectory);
        var fullPath = Path.GetFullPath(Path.Combine(fullLab, normalized.Replace('/', Path.DirectorySeparatorChar)));
        if (!IsWithinDirectory(fullLab, fullPath))
            throw new InvalidDataException("La ruta de archivo sale del directorio LAB.");
        return fullPath;
    }

    private static string GetRequiredString(JsonElement parent, string name)
    {
        if (!parent.TryGetProperty(name, out var value) || value.ValueKind != JsonValueKind.String
            || string.IsNullOrWhiteSpace(value.GetString()))
            throw new InvalidDataException($"El manifiesto Vulkan no contiene {name} válido.");
        return value.GetString()!;
    }

    private static bool IsWithinDirectory(string directory, string path)
    {
        var relative = Path.GetRelativePath(Path.GetFullPath(directory), Path.GetFullPath(path));
        return !Path.IsPathRooted(relative) && relative != ".."
            && !relative.StartsWith(".." + Path.DirectorySeparatorChar, StringComparison.Ordinal)
            && !relative.StartsWith(".." + Path.AltDirectorySeparatorChar, StringComparison.Ordinal);
    }

    private static void EnsureNoReparsePointBetween(string baseDirectory, string targetPath)
    {
        var fullBase = Path.GetFullPath(baseDirectory);
        var fullTarget = Path.GetFullPath(targetPath);
        if (!IsWithinDirectory(fullBase, fullTarget))
            throw new InvalidDataException("La ruta del paquete sale del directorio LAB.");

        var current = fullBase;
        foreach (var segment in Path.GetRelativePath(fullBase, fullTarget)
                     .Split([Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar], StringSplitOptions.RemoveEmptyEntries))
        {
            current = Path.Combine(current, segment);
            if (!File.Exists(current) && !Directory.Exists(current)) continue;
            if ((File.GetAttributes(current) & FileAttributes.ReparsePoint) != 0)
                throw new InvalidDataException($"El paquete Vulkan no puede atravesar un enlace o reparse point: {current}.");
        }
    }
}

internal static class VulkanProbeProcess
{
    public static readonly TimeSpan ProbeTimeout = TimeSpan.FromSeconds(15);

    public static ProcessStartInfo CreateStartInfo(string serverPath, string workingDirectory)
    {
        var info = new ProcessStartInfo
        {
            FileName = Path.GetFullPath(serverPath),
            WorkingDirectory = Path.GetFullPath(workingDirectory),
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };
        info.ArgumentList.Add("--list-devices");
        return info;
    }
}
