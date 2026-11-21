using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using WritingDemo.Core;

await TestReviewedFamilyProfilesAsync();
await TestLfmUsesBaselineOnlyAsync();
await TestRevisionTamperingIsRejectedAsync();
TestPromptCatalogApiHasNoTextParameters();
Console.WriteLine("PromptTests: todos los casos pasaron.");

static Task TestReviewedFamilyProfilesAsync()
{
    using var fixture = new PromptFixture();
    var profiles = PromptCatalog.Load(fixture.Paths, MakeModel("10-qwen35-4b-q8-0"));
    var baseline = profiles[0];
    var revised = profiles[1];

    Assert(profiles.Count == 2, "Una familia revisada debe recibir el baseline y la propuesta.");
    Assert(baseline.Id == "benchmark-base", "El perfil base debe tener el identificador estable.");
    Assert(baseline.Label == "Base experimental", "El perfil base debe conservar la etiqueta experimental.");
    Assert(baseline.SystemPrompt == fixture.BaselinePrompt, "El baseline debe salir solo de system_prompt del benchmark.");
    Assert(baseline.Sha256 == Hash(fixture.BaselinePrompt), "El SHA-256 del baseline debe cubrir el texto UTF-8 exacto.");
    Assert(baseline.EvidenceSha256 is null, "No hay evidencia empírica asociada al baseline en el catálogo de revisión.");
    Assert(revised.Id == "human-review-20261109", "La propuesta debe exponer el identificador de revisión.");
    Assert(revised.Label == "Revisión humana · pendiente de validar", "La etiqueta debe dejar claro que falta validar.");
    Assert(revised.SystemPrompt == fixture.BaselinePrompt + "\n\n" + fixture.CommonAppendix + "\n\n" + fixture.QwenAppendix,
        "La propuesta debe anexar el texto común y el de su familia con separadores exactos.");
    Assert(revised.Sha256 == Hash(revised.SystemPrompt), "El SHA-256 de la propuesta debe cubrir su texto UTF-8 exacto.");
    Assert(revised.EvidenceSha256 is null, "La propuesta sin validar no debe declarar evidencia empírica.");
    Assert(profiles.All(profile => !profile.SystemPrompt.Contains(fixture.GoldSentinel, StringComparison.Ordinal)),
        "El texto gold del benchmark no debe llegar a ningún perfil de sistema.");

    var mini = PromptCatalog.Load(fixture.Paths, MakeModel("06-minicpm5-2b-q4-k-m"));
    Assert(mini[1].SystemPrompt.EndsWith(fixture.MiniCpmAppendix, StringComparison.Ordinal), "MiniCPM debe usar solo su apéndice.");
    var gemma = PromptCatalog.Load(fixture.Paths, MakeModel("12-gemma4-e2b-qat-q4-0"));
    Assert(gemma[1].SystemPrompt.EndsWith(fixture.GemmaAppendix, StringComparison.Ordinal), "Gemma debe usar solo su apéndice.");
    return Task.CompletedTask;
}

static Task TestLfmUsesBaselineOnlyAsync()
{
    using var fixture = new PromptFixture();
    var profiles = PromptCatalog.Load(fixture.Paths, MakeModel("07-lfm25-12b-bf16"));

    Assert(profiles.Count == 1, "LFM debe recibir únicamente el baseline, ya que no tiene revisión humana.");
    Assert(profiles[0].Id == "benchmark-base" && profiles[0].SystemPrompt == fixture.BaselinePrompt,
        "El perfil de LFM debe ser el baseline experimental sin cambios.");
    return Task.CompletedTask;
}

static Task TestRevisionTamperingIsRejectedAsync()
{
    using var fixture = new PromptFixture();
    var revisionPath = Path.Combine(fixture.Paths.LabDirectory, "demo", "prompts", "human_review_20261109.json");
    using (var document = JsonDocument.Parse(File.ReadAllText(revisionPath)))
    {
        var revision = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(document.RootElement.GetRawText())!;
        revision["baseline_system_prompt_sha256"] = JsonSerializer.SerializeToElement(new string('0', 64));
        File.WriteAllText(revisionPath, JsonSerializer.Serialize(revision), new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
    }

    AssertThrows<InvalidDataException>(() => PromptCatalog.Load(fixture.Paths, MakeModel("10-qwen35-4b-q8-0")),
        "Una revisión cuyo hash base no coincide debe rechazarse, no degradarse silenciosamente.");

    fixture.WriteValidRevision();
    using (var document = JsonDocument.Parse(File.ReadAllText(revisionPath)))
    {
        var revision = JsonSerializer.Deserialize<Dictionary<string, JsonElement>>(document.RootElement.GetRawText())!;
        revision["source_backup_sha256"] = JsonSerializer.SerializeToElement(new string('0', 64));
        File.WriteAllText(revisionPath, JsonSerializer.Serialize(revision), new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));
    }

    AssertThrows<InvalidDataException>(() => PromptCatalog.Load(fixture.Paths, MakeModel("10-qwen35-4b-q8-0")),
        "Una revisión con procedencia alterada debe rechazarse.");
    return Task.CompletedTask;
}

static void TestPromptCatalogApiHasNoTextParameters()
{
    var methods = typeof(PromptCatalog).GetMethods(BindingFlags.Public | BindingFlags.Static | BindingFlags.DeclaredOnly);
    Assert(methods.Length == 1 && methods[0].Name == "Load", "La API pública del catálogo debe contener solo Load.");
    var parameterTypes = methods[0].GetParameters().Select(parameter => parameter.ParameterType).ToArray();
    Assert(parameterTypes.SequenceEqual(new[] { typeof(DemoPaths), typeof(ModelSpec) }),
        "La API del catálogo no debe recibir ejemplos, tareas ni texto del estudiante.");
}

static ModelSpec MakeModel(string id)
{
    using var generation = JsonDocument.Parse("{}");
    return new ModelSpec(id, "Fixture", "Fixture", "Q4_K_M", "model.gguf", new string('a', 64), 1,
        null, "https://fixture.invalid/tree/revision", "Fixture", generation.RootElement.Clone(), false, "Fixture model");
}

static string Hash(string value) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

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

sealed class PromptFixture : IDisposable
{
    private const string SourceBackupSha256 = "91a638c9725894144a0b1307af9441c9eca2e40b6423263ab71a454e2b4dd24e";

    public string BaselinePrompt { get; } = "Fixture baseline system instructions.";
    public string CommonAppendix { get; } = "Fixture common appendix.";
    public string QwenAppendix { get; } = "Fixture Qwen appendix.";
    public string MiniCpmAppendix { get; } = "Fixture MiniCPM appendix.";
    public string GemmaAppendix { get; } = "Fixture Gemma appendix.";
    public string GoldSentinel { get; } = "GOLD_EXAMPLE_SENTINEL";
    public string Root { get; } = Path.Combine(Path.GetTempPath(), "WritingDemo.PromptTests", Guid.NewGuid().ToString("N"));
    public DemoPaths Paths => new(Root);

    public PromptFixture()
    {
        Directory.CreateDirectory(Path.Combine(Root, "demo", "prompts"));
        WriteBenchmark();
        WriteValidRevision();
    }

    public void WriteValidRevision()
    {
        var revision = new
        {
            schema_version = "writing_demo.prompt_revision/1.0",
            id = "human-review-20261109",
            status = "PROPOSED_NOT_EMPIRICALLY_VALIDATED",
            source_backup_sha256 = SourceBackupSha256,
            baseline_system_prompt_sha256 = Hash(BaselinePrompt),
            common_appendix = CommonAppendix,
            family_appendices = new { qwen = QwenAppendix, minicpm = MiniCpmAppendix, gemma = GemmaAppendix }
        };
        WriteUtf8(Path.Combine(Root, "demo", "prompts", "human_review_20261109.json"), JsonSerializer.Serialize(revision));
    }

    private void WriteBenchmark()
    {
        var benchmark = new
        {
            system_prompt = BaselinePrompt,
            cases = new[] { new { student_text = "This field is not an inference parameter.", gold = new { corrected_text = GoldSentinel } } }
        };
        WriteUtf8(Path.Combine(Root, "benchmark_smoke_test_v2.json"), JsonSerializer.Serialize(benchmark));
    }

    private static void WriteUtf8(string path, string text) =>
        File.WriteAllText(path, text, new UTF8Encoding(encoderShouldEmitUTF8Identifier: false));

    private static string Hash(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    public void Dispose()
    {
        if (Directory.Exists(Root))
            Directory.Delete(Root, recursive: true);
    }
}
