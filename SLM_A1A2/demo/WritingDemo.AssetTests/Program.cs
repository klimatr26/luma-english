using System.Net;
using System.Security.Cryptography;
using System.Text.Json;
using WritingDemo.Core;

var workspace = DemoPaths.Locate();
await TestCatalogAsync(workspace);
await TestVerifyAndResolveAsync(workspace);
await TestDownloadAsync(workspace);
await TestFailedDownloadKeepsPartialAsync(workspace);
Console.WriteLine("AssetTests: todos los casos pasaron.");

static Task TestCatalogAsync(DemoPaths paths)
{
    using var scratch = new ScratchDirectory();
    Directory.CreateDirectory(Path.Combine(scratch.Path, "manifests"));
    Directory.CreateDirectory(Path.Combine(scratch.Path, "demo"));
    File.Copy(paths.ManifestPath, Path.Combine(scratch.Path, "manifests", "experiment_manifest_120.json"));
    File.Copy(Path.Combine(paths.LabDirectory, "demo", "model_sources.json"), Path.Combine(scratch.Path, "demo", "model_sources.json"));
    var models = ModelCatalog.Load(new DemoPaths(scratch.Path));
    Assert(!Directory.Exists(Path.Combine(scratch.Path, "models")), "El catálogo no debe requerir la caché ni los archivos de modelos para arrancar.");
    Assert(models.Count == 13, $"Se esperaban 13 modelos, se encontraron {models.Count}.");
    Assert(!models.Any(model => model.Id.Contains("qwen35-2b", StringComparison.Ordinal)), "El catálogo no debe incluir Qwen 2B.");

    var qwenQ4 = models.Single(model => model.Id == "11-qwen35-4b-q4-k-m");
    Assert(qwenQ4.FamilyKey == "Qwen 3.5 · 4B", "La familia Qwen debe estar en formato humano.");
    Assert(qwenQ4.DisplayName == qwenQ4.FamilyKey, "DisplayName debe ser la familia; la cuantización se selecciona aparte.");
    Assert(qwenQ4.Quantization == "Q4_K_M", "Se perdió la cuantización de Qwen.");
    Assert(qwenQ4.DownloadUrl is null, "El GGUF de Qwen es una conversión local y no tiene URL directa.");
    Assert(qwenQ4.SourcePage.Contains("851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a", StringComparison.Ordinal), "La fuente Qwen debe fijar la revisión de HF.");
    Assert(qwenQ4.RelativePath.Replace('\\', '/') == "qwen_converted/Qwen3.5-4B-Q4_K_M.gguf", "La ruta convertida de Qwen no coincide.");
    Assert(qwenQ4.ExpectedSha256 == "2438d070b090e52606c5f35b538aea92653bd3439046452ddfb736748b63e313", "El hash de Qwen debe venir del manifiesto.");
    Assert(qwenQ4.Note == "Preparado con la conversión local verificada.", "La nota debe ser una frase humana corta.");
    Assert(qwenQ4.Note.Length < 100, "La nota visible no debe incluir el runtime completo.");
    Assert(qwenQ4.Generation.GetProperty("temperature").GetDouble() == 0.7, "Se perdieron los valores de generación.");
    Assert(qwenQ4.TemplateThinkingToggle, "Debe mantenerse el soporte de enable_thinking del manifiesto.");
    Assert(models.Any(model => model.Id == "04-minicpm5-2b-f16" && model.DownloadUrl?.Contains("/resolve/2079a22f3beaa4e306449978533478fe0522f4b3/MiniCPM5-2B-F16.gguf", StringComparison.Ordinal) == true),
        "La URL de MiniCPM debe usar la revisión fijada y la ruta raíz declarada por el árbol HF.");
    Assert(models.Any(model => model.Id == "12-gemma4-e2b-qat-q4-0" && model.RelativePath.Replace('\\', '/') == "gemma4_e2b/google_qat_q4_0/gemma-4-E2B_q4_0-it.gguf"),
        "Debe conservarse la ruta de Gemma del manifiesto.");
    return Task.CompletedTask;
}

static async Task TestVerifyAndResolveAsync(DemoPaths paths)
{
    using var scratch = new ScratchDirectory();
    var payload = MakeTinyGguf();
    var model = MakeSpec(payload, "small/valid.gguf");
    var file = Path.Combine(scratch.Path, "valid.gguf");
    await File.WriteAllBytesAsync(file, payload);

    using var assets = new ModelAssets(paths);
    Assert(await assets.VerifyAsync(model, file), "Un GGUF pequeño con hash correcto debe verificarse.");
    Assert(assets.ResolvePath(model, scratch.Path) == Path.Combine(scratch.Path, "small", "valid.gguf"), "ResolvePath debe respetar la ruta relativa.");

    var wrongSize = model with { ExpectedSize = model.ExpectedSize + 1 };
    Assert(!await assets.VerifyAsync(wrongSize, file), "Un tamaño incorrecto debe fallar la verificación.");

    var wrongMagicFile = Path.Combine(scratch.Path, "bad-magic.gguf");
    await File.WriteAllBytesAsync(wrongMagicFile, "NOPE"u8.ToArray().Concat(payload[4..]).ToArray());
    Assert(!await assets.VerifyAsync(model with { RelativePath = "bad-magic.gguf" }, wrongMagicFile), "Un archivo sin cabecera GGUF debe fallar.");

    var traversal = model with { RelativePath = Path.Combine("..", "outside.gguf") };
    AssertThrows<ArgumentException>(() => assets.ResolvePath(traversal, scratch.Path), "ResolvePath debe impedir salir de la carpeta.");
}

static async Task TestDownloadAsync(DemoPaths paths)
{
    using var scratch = new ScratchDirectory();
    var payload = MakeTinyGguf();
    var handler = new FixtureHandler(payload);
    using var assets = new ModelAssets(paths, handler);
    var spec = MakeSpec(payload, "tiny/model.gguf");
    var destination = await assets.DownloadAsync(spec, scratch.Path, token: "fixture-token");

    Assert(File.ReadAllBytes(destination).SequenceEqual(payload), "El helper debe guardar el cuerpo recibido.");
    Assert(handler.RequestCount == 1, "Debe hacerse exactamente una petición HTTP.");
    Assert(handler.Authorization == "Bearer fixture-token", "El token debe enviarse como cabecera sin persistirlo.");
    Assert(await assets.VerifyAsync(spec, destination), "El archivo publicado debe validarse.");

    var again = await assets.DownloadAsync(spec, scratch.Path);
    Assert(again == destination && handler.RequestCount == 1, "Un GGUF correcto debe reutilizarse sin nueva descarga.");
}

static async Task TestFailedDownloadKeepsPartialAsync(DemoPaths paths)
{
    using var scratch = new ScratchDirectory();
    var payload = MakeTinyGguf();
    using var assets = new ModelAssets(paths, new FixtureHandler(payload));
    var wrongHash = new string('0', 64);
    var spec = MakeSpec(payload, "tiny/bad-hash.gguf") with { ExpectedSha256 = wrongHash };

    await AssertThrowsAsync<InvalidDataException>(
        () => assets.DownloadAsync(spec, scratch.Path),
        "Un archivo que no coincide con el hash debe rechazarse.");
    Assert(!File.Exists(Path.Combine(scratch.Path, "tiny", "bad-hash.gguf")), "No se debe publicar un GGUF incorrecto.");
    Assert(Directory.GetFiles(Path.Combine(scratch.Path, "tiny"), "*.partial-*").Length == 1,
        "El parcial propio debe quedar disponible para inspección y no reutilizarse automáticamente.");
}

static ModelSpec MakeSpec(byte[] payload, string relativePath)
{
    using var generation = JsonDocument.Parse("{}");
    return new ModelSpec(
        "fixture-model",
        "Fixture",
        "Fixture",
        "Q4_K_M",
        relativePath,
        Convert.ToHexString(SHA256.HashData(payload)).ToLowerInvariant(),
        payload.Length,
        "https://fixture.invalid/model.gguf",
        "https://fixture.invalid/tree/revision",
        "Apache-2.0",
        generation.RootElement.Clone(),
        false,
        "Fixture model");
}

static byte[] MakeTinyGguf() => "GGUF"u8.ToArray().Concat(Enumerable.Range(0, 96).Select(value => (byte)value)).ToArray();

static void Assert(bool condition, string message)
{
    if (!condition)
        throw new InvalidOperationException(message);
}

static void AssertThrows<TException>(Action action, string message) where TException : Exception
{
    try { action(); }
    catch (TException) { return; }
    throw new InvalidOperationException(message);
}

static async Task AssertThrowsAsync<TException>(Func<Task> action, string message) where TException : Exception
{
    try { await action(); }
    catch (TException) { return; }
    throw new InvalidOperationException(message);
}

sealed class FixtureHandler(byte[] payload) : HttpMessageHandler
{
    public int RequestCount { get; private set; }
    public string? Authorization { get; private set; }

    protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        cancellationToken.ThrowIfCancellationRequested();
        RequestCount++;
        Authorization = request.Headers.Authorization?.ToString();
        return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new ByteArrayContent(payload)
        });
    }
}

sealed class ScratchDirectory : IDisposable
{
    public string Path { get; } = System.IO.Path.Combine(System.IO.Path.GetTempPath(), "WritingDemo.AssetTests", Guid.NewGuid().ToString("N"));

    public ScratchDirectory() => Directory.CreateDirectory(Path);

    public void Dispose()
    {
        if (Directory.Exists(Path))
            Directory.Delete(Path, recursive: true);
    }
}
