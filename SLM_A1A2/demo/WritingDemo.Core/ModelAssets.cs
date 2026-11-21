using System.Diagnostics;
using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace WritingDemo.Core;

public static class ModelCatalog
{
    private static readonly string[] DemoModelIds =
    [
        "minicpm5_2b_f16", "minicpm5_2b_q8_0", "minicpm5_2b_q4_k_m",
        "qwen35_4b_q8_0", "qwen35_4b_q4_k_m",
        "gemma4_e2b_qat_q4_0", "gemma4_e2b_ud_q4_k_xl", "gemma4_e2b_ud_q2_k_xl",
        "lfm25_12b_bf16", "lfm25_12b_q8_0", "lfm25_12b_q4_k_m",
        "lfm25_26b_q8_0", "lfm25_26b_q4_k_m"
    ];

    public static IReadOnlyList<ModelSpec> Load(DemoPaths paths)
    {
        ArgumentNullException.ThrowIfNull(paths);
        using var document = JsonDocument.Parse(File.ReadAllText(paths.ManifestPath));
        var sourcesPath = Path.Combine(paths.LabDirectory, "demo", "model_sources.json");
        using var sourceDocument = JsonDocument.Parse(File.ReadAllText(sourcesPath));
        var sourcePins = sourceDocument.RootElement.GetProperty("models")
            .EnumerateArray()
            .ToDictionary(item => RequiredString(item, "config_id"), StringComparer.Ordinal);
        var configurations = document.RootElement.GetProperty("configurations")
            .EnumerateArray()
            .ToDictionary(item => RequiredString(item, "id"), StringComparer.Ordinal);

        var models = new List<ModelSpec>(DemoModelIds.Length);
        foreach (var id in DemoModelIds)
        {
            if (!configurations.TryGetValue(id, out var config))
                throw new InvalidDataException($"La configuración '{id}' no aparece en {paths.ManifestPath}.");

            var configId = RequiredString(config, "config_id");
            var source = config.GetProperty("source");
            var repo = RequiredString(source, "repo");
            var revision = RequiredString(source, "revision");
            if (!sourcePins.TryGetValue(configId, out var sourcePin))
                throw new InvalidDataException($"No hay una fuente fijada para '{configId}' en {sourcesPath}.");
            if (RequiredString(sourcePin, "repo") != repo || RequiredString(sourcePin, "revision") != revision)
                throw new InvalidDataException($"La fuente fijada de '{configId}' no coincide con el manifiesto experimental.");
            var sourcePage = RequiredString(sourcePin, "source_page");
            if (sourcePage != $"https://huggingface.co/{repo}/tree/{revision}")
                throw new InvalidDataException($"La página de fuente de '{configId}' no está fijada a la revisión del manifiesto.");
            var license = RequiredString(sourcePin, "license");
            if (license != RequiredString(source, "license"))
                throw new InvalidDataException($"La etiqueta de licencia de '{configId}' no coincide con el manifiesto.");
            var modelPath = RequiredString(config, "model_path");
            var filename = modelPath.Replace('\\', '/').Split('/').Last();
            var relativePath = id.StartsWith("qwen35_4b_", StringComparison.Ordinal)
                ? Path.Combine("qwen_converted", filename)
                : Path.Combine(modelPath.Replace('\\', '/').Split('/').Skip(1).ToArray());
            var quant = RequiredString(config, "quant");
            var gguf = config.GetProperty("gguf");
            var expectedSize = gguf.GetProperty("bytes").GetInt64();
            var expectedSha256 = RequiredString(config, "model_sha256").ToLowerInvariant();
            if (sourcePin.GetProperty("size_bytes").GetInt64() != expectedSize
                || !string.Equals(RequiredString(sourcePin, "sha256"), expectedSha256, StringComparison.OrdinalIgnoreCase))
                throw new InvalidDataException($"El tamaño o SHA-256 fijado de '{configId}' no coincide con el manifiesto experimental.");
            var generation = config.GetProperty("generation").Clone();
            var isLocalQwenConversion = id.StartsWith("qwen35_4b_", StringComparison.Ordinal);
            var sourceKind = RequiredString(sourcePin, "kind");
            var downloadUrl = sourcePin.GetProperty("download_url").ValueKind == JsonValueKind.Null
                ? null
                : sourcePin.GetProperty("download_url").GetString();
            if (isLocalQwenConversion)
            {
                if (sourceKind != "local-conversion" || downloadUrl is not null
                    || sourcePin.GetProperty("remote_file").ValueKind != JsonValueKind.Null)
                    throw new InvalidDataException($"Qwen 4B '{configId}' debe permanecer como conversión local, sin URL GGUF directa.");
            }
            else
            {
                var remoteFile = RequiredString(sourcePin, "remote_file");
                var expectedPrefix = $"https://huggingface.co/{repo}/resolve/{revision}/";
                if (sourceKind != "huggingface-gguf"
                    || !string.Equals(remoteFile, filename, StringComparison.Ordinal)
                    || downloadUrl is null
                    || !downloadUrl.StartsWith(expectedPrefix, StringComparison.Ordinal))
                    throw new InvalidDataException($"La URL del archivo de '{configId}' no coincide con el árbol HF fijado.");
            }
            var familyKey = FamilyName(id);
            var templateThinkingToggle = config.TryGetProperty("chat_template_kwargs", out var templateOptions)
                && templateOptions.ValueKind == JsonValueKind.Object
                && templateOptions.TryGetProperty("enable_thinking", out _);
            var note = BuildNote(id);

            models.Add(new ModelSpec(
                configId,
                familyKey,
                familyKey,
                quant,
                relativePath,
                expectedSha256,
                expectedSize,
                downloadUrl,
                sourcePage,
                license,
                generation,
                templateThinkingToggle,
                note));
        }

        return models.AsReadOnly();
    }

    private static string FamilyName(string id) => id switch
    {
        var value when value.StartsWith("minicpm5_", StringComparison.Ordinal) => "MiniCPM 5 · 2B",
        var value when value.StartsWith("qwen35_4b_", StringComparison.Ordinal) => "Qwen 3.5 · 4B",
        var value when value.StartsWith("gemma4_", StringComparison.Ordinal) => "Gemma 4 · E2B",
        var value when value.StartsWith("lfm25_12b_", StringComparison.Ordinal) => "LFM 2.5 · 1.2B",
        var value when value.StartsWith("lfm25_26b_", StringComparison.Ordinal) => "LFM 2.5 · 2.6B",
        _ => throw new InvalidDataException($"Familia no reconocida para '{id}'.")
    };

    private static string BuildNote(string id) => id switch
    {
        var value when value.StartsWith("qwen35_4b_", StringComparison.Ordinal) => "Preparado con la conversión local verificada.",
        var value when value.StartsWith("minicpm5_", StringComparison.Ordinal) => "Modelo compacto para comparar correcciones.",
        "gemma4_e2b_qat_q4_0" => "Variante ajustada para comparar correcciones.",
        var value when value.StartsWith("gemma4_e2b_ud_", StringComparison.Ordinal) =>
            "Variante dinámica; el formato de salida puede requerir recuperación.",
        _ => "Familia adicional de comparación; revisar coherencia del JSON."
    };

    private static string RequiredString(JsonElement element, string property)
    {
        if (!element.TryGetProperty(property, out var value) || value.ValueKind != JsonValueKind.String)
            throw new InvalidDataException($"El manifiesto no tiene el campo de texto '{property}'.");
        return value.GetString()!;
    }
}

public sealed class ModelAssets : IDisposable
{
    private readonly DemoPaths _paths;
    private readonly HttpClient _httpClient;

    public ModelAssets(DemoPaths paths)
        : this(paths, handler: null)
    {
    }

    /// <summary>Allows deterministic transfer tests using a local HTTP handler.</summary>
    public ModelAssets(DemoPaths paths, HttpMessageHandler? handler)
    {
        _paths = paths ?? throw new ArgumentNullException(nameof(paths));
        _httpClient = new HttpClient(handler ?? new HttpClientHandler(), disposeHandler: handler is null)
        {
            Timeout = Timeout.InfiniteTimeSpan
        };
    }

    public string ResolvePath(ModelSpec spec, string modelDirectory)
    {
        ArgumentNullException.ThrowIfNull(spec);
        ArgumentException.ThrowIfNullOrWhiteSpace(modelDirectory);
        var pathParts = spec.RelativePath.Split(
            [Path.DirectorySeparatorChar, Path.AltDirectorySeparatorChar],
            StringSplitOptions.RemoveEmptyEntries);
        if (Path.IsPathRooted(spec.RelativePath) || pathParts.Any(part => part == ".."))
            throw new ArgumentException("RelativePath debe estar dentro de la carpeta de modelos.", nameof(spec));

        var root = Path.GetFullPath(modelDirectory);
        var resolved = Path.GetFullPath(Path.Combine(root, spec.RelativePath));
        var relativeToRoot = Path.GetRelativePath(root, resolved);
        if (Path.IsPathRooted(relativeToRoot) || relativeToRoot == ".."
            || relativeToRoot.StartsWith($"..{Path.DirectorySeparatorChar}", OperatingSystem.IsWindows()
                ? StringComparison.OrdinalIgnoreCase
                : StringComparison.Ordinal))
            throw new ArgumentException("RelativePath no puede salir de la carpeta de modelos.", nameof(spec));
        return resolved;
    }

    public async Task<bool> VerifyAsync(ModelSpec spec, string path,
        IProgress<TransferProgress>? progress = null, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(spec);
        ArgumentException.ThrowIfNullOrWhiteSpace(path);
        cancellationToken.ThrowIfCancellationRequested();
        if (!File.Exists(path))
            return false;

        progress?.Report(new TransferProgress("Comprobando tamaño del modelo", 0, spec.ExpectedSize));
        var before = new FileInfo(path);
        if (before.Length != spec.ExpectedSize)
            return false;

        await using var stream = new FileStream(path, FileMode.Open, FileAccess.Read, FileShare.Read,
            bufferSize: 1024 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan);
        var magic = new byte[4];
        var read = await stream.ReadAsync(magic.AsMemory(), cancellationToken).ConfigureAwait(false);
        if (read != 4 || !magic.AsSpan().SequenceEqual("GGUF"u8))
            return false;

        stream.Position = 0;
        progress?.Report(new TransferProgress("Calculando SHA-256", 0, spec.ExpectedSize));
        var actualHash = Convert.ToHexString(await SHA256.HashDataAsync(stream, cancellationToken).ConfigureAwait(false));
        var after = new FileInfo(path);
        if (before.Length != after.Length || before.LastWriteTimeUtc != after.LastWriteTimeUtc)
            return false;

        progress?.Report(new TransferProgress("Verificación terminada", spec.ExpectedSize, spec.ExpectedSize));
        return string.Equals(actualHash, spec.ExpectedSha256, StringComparison.OrdinalIgnoreCase);
    }

    public async Task<string> DownloadAsync(ModelSpec spec, string modelDirectory,
        IProgress<TransferProgress>? progress = null, CancellationToken cancellationToken = default,
        string? token = null)
    {
        ArgumentNullException.ThrowIfNull(spec);
        var destination = ResolvePath(spec, modelDirectory);
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);

        if (File.Exists(destination))
        {
            if (await VerifyAsync(spec, destination, progress, cancellationToken).ConfigureAwait(false))
                return destination;
            throw new IOException($"Ya existe un archivo en '{destination}', pero no coincide con el tamaño, el SHA-256 o el formato esperado. Se conserva sin reemplazarlo.");
        }

        if (spec.FamilyKey == "Qwen 3.5 · 4B")
            return await PrepareQwenAsync(spec, modelDirectory, destination, progress, cancellationToken, token).ConfigureAwait(false);
        if (string.IsNullOrWhiteSpace(spec.DownloadUrl))
            throw new InvalidOperationException($"No hay una descarga directa configurada para {spec.DisplayName}.");

        return await DownloadDirectAsync(spec, destination, progress, cancellationToken, token).ConfigureAwait(false);
    }

    private async Task<string> DownloadDirectAsync(ModelSpec spec, string destination,
        IProgress<TransferProgress>? progress, CancellationToken cancellationToken, string? token)
    {
        var partialPath = destination + ".partial-" + Guid.NewGuid().ToString("N");
        progress?.Report(new TransferProgress("Conectando con el repositorio del modelo", 0, spec.ExpectedSize));

        using var request = new HttpRequestMessage(HttpMethod.Get, spec.DownloadUrl);
        if (!string.IsNullOrWhiteSpace(token))
            request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token.Trim());

        using var response = await _httpClient.SendAsync(request, HttpCompletionOption.ResponseHeadersRead,
            cancellationToken).ConfigureAwait(false);
        if (response.StatusCode == HttpStatusCode.TooManyRequests)
            throw new HttpRequestException("Hugging Face respondió HTTP 429. La descarga se detuvo sin reintentos; espera antes de volver a intentarlo.", null, response.StatusCode);
        response.EnsureSuccessStatusCode();

        await using (var input = await response.Content.ReadAsStreamAsync(cancellationToken).ConfigureAwait(false))
        await using (var output = new FileStream(partialPath, FileMode.CreateNew, FileAccess.Write, FileShare.None,
                         bufferSize: 1024 * 1024, FileOptions.Asynchronous | FileOptions.SequentialScan))
        {
            var buffer = new byte[1024 * 1024];
            long received = 0;
            var lastReport = 0L;
            while (true)
            {
                var read = await input.ReadAsync(buffer.AsMemory(), cancellationToken).ConfigureAwait(false);
                if (read == 0)
                    break;
                await output.WriteAsync(buffer.AsMemory(0, read), cancellationToken).ConfigureAwait(false);
                received += read;
                if (received - lastReport >= 4 * 1024 * 1024 || received == spec.ExpectedSize)
                {
                    progress?.Report(new TransferProgress("Descargando modelo", received, spec.ExpectedSize));
                    lastReport = received;
                }
            }
            await output.FlushAsync(cancellationToken).ConfigureAwait(false);
        }

        progress?.Report(new TransferProgress("Verificando archivo descargado", spec.ExpectedSize, spec.ExpectedSize));
        if (!await VerifyAsync(spec, partialPath, progress, cancellationToken).ConfigureAwait(false))
            throw new InvalidDataException($"El archivo descargado no coincide con el tamaño, el SHA-256 o la cabecera GGUF esperados. Se conserva para inspección en '{partialPath}'.");

        try
        {
            File.Move(partialPath, destination, overwrite: false);
        }
        catch (IOException) when (File.Exists(destination))
        {
            if (await VerifyAsync(spec, destination, progress, cancellationToken).ConfigureAwait(false))
                return destination;
            throw new IOException($"Otro proceso creó '{destination}' con contenido no válido. El archivo no se reemplazó.");
        }

        progress?.Report(new TransferProgress("Descarga lista", spec.ExpectedSize, spec.ExpectedSize));
        return destination;
    }

    private async Task<string> PrepareQwenAsync(ModelSpec spec, string modelDirectory, string destination,
        IProgress<TransferProgress>? progress, CancellationToken cancellationToken, string? token)
    {
        var scriptPath = Path.Combine(_paths.LabDirectory, "demo", "scripts", "prepare_qwen_demo.py");
        var pythonPath = Path.Combine(_paths.LabDirectory, ".venv", "Scripts", "python.exe");
        if (!File.Exists(scriptPath))
            throw new FileNotFoundException("Falta el helper local para preparar Qwen 3.5 4B.", scriptPath);
        if (!File.Exists(pythonPath))
            throw new FileNotFoundException("Falta el Python del entorno de conversión local requerido (.venv). El helper no instala runtimes ni herramientas automáticamente.", pythonPath);

        var quant = spec.Quantization switch
        {
            "Q8_0" => "Q8_0",
            "Q4_K_M" => "Q4_K_M",
            _ => throw new InvalidOperationException($"La conversión local de Qwen 4B no admite '{spec.Quantization}'.")
        };
        progress?.Report(new TransferProgress("Preparando Qwen 3.5 4B con el conversor local fijado"));

        using var process = new Process
        {
            StartInfo = new ProcessStartInfo
            {
                FileName = pythonPath,
                WorkingDirectory = _paths.LabDirectory,
                UseShellExecute = false,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                CreateNoWindow = true
            },
            EnableRaisingEvents = true
        };
        process.StartInfo.ArgumentList.Add(scriptPath);
        process.StartInfo.ArgumentList.Add("--models-dir");
        process.StartInfo.ArgumentList.Add(Path.GetFullPath(modelDirectory));
        process.StartInfo.ArgumentList.Add("--quant");
        process.StartInfo.ArgumentList.Add(quant);
        if (!string.IsNullOrWhiteSpace(token))
            process.StartInfo.Environment["HF_TOKEN"] = token;

        var standardError = new StringBuilder();
        process.OutputDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data is not null)
                progress?.Report(new TransferProgress(eventArgs.Data));
        };
        process.ErrorDataReceived += (_, eventArgs) =>
        {
            if (eventArgs.Data is not null)
                lock (standardError) standardError.AppendLine(eventArgs.Data);
        };

        if (!process.Start())
            throw new InvalidOperationException("No se pudo iniciar el helper local de Qwen.");
        process.BeginOutputReadLine();
        process.BeginErrorReadLine();
        try
        {
            await process.WaitForExitAsync(cancellationToken).ConfigureAwait(false);
        }
        catch (OperationCanceledException)
        {
            try { process.Kill(entireProcessTree: true); }
            catch (InvalidOperationException) { }
            catch (System.ComponentModel.Win32Exception) { }
            await process.WaitForExitAsync(CancellationToken.None).ConfigureAwait(false);
            throw;
        }

        if (process.ExitCode != 0)
        {
            string errorText;
            lock (standardError) errorText = standardError.ToString().Trim();
            throw new InvalidOperationException(string.IsNullOrWhiteSpace(errorText)
                ? $"El helper de Qwen terminó con código {process.ExitCode}."
                : $"El helper de Qwen terminó con código {process.ExitCode}: {errorText}");
        }

        if (!await VerifyAsync(spec, destination, progress, cancellationToken).ConfigureAwait(false))
            throw new InvalidDataException($"El helper terminó, pero el GGUF resultante no pasó la verificación esperada: '{destination}'.");
        return destination;
    }

    public void Dispose() => _httpClient.Dispose();
}
