using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace WritingDemo.Core;

public sealed record PromptProfile(string Id, string Label, string SystemPrompt, string Sha256, string? EvidenceSha256);

public static class PromptCatalog
{
    private const string RevisionSchemaVersion = "writing_demo.prompt_revision/1.0";
    private const string RevisionId = "human-review-20261109";
    private const string RevisionStatus = "PROPOSED_NOT_EMPIRICALLY_VALIDATED";
    private const string SourceBackupSha256 = "91a638c9725894144a0b1307af9441c9eca2e40b6423263ab71a454e2b4dd24e";
    private const string BaselineId = "benchmark-base";
    private const string BaselineLabel = "Base experimental";
    private const string RevisionLabel = "Revisión humana · pendiente de validar";

    public static IReadOnlyList<PromptProfile> Load(DemoPaths paths, ModelSpec model)
    {
        ArgumentNullException.ThrowIfNull(paths);
        ArgumentNullException.ThrowIfNull(model);

        var baselinePrompt = LoadBaselineSystemPrompt(paths);
        var revision = LoadRevision(paths, baselinePrompt);
        var baseline = new PromptProfile(BaselineId, BaselineLabel, baselinePrompt, Sha256(baselinePrompt), null);
        var profiles = new List<PromptProfile> { baseline };

        var family = SelectReviewedFamily(model.Id);
        if (family is not null)
        {
            var prompt = string.Concat(baselinePrompt, "\n\n", revision.CommonAppendix, "\n\n", revision.FamilyAppendices[family]);
            profiles.Add(new PromptProfile(RevisionId, RevisionLabel, prompt, Sha256(prompt), null));
        }

        return profiles.AsReadOnly();
    }

    private static string LoadBaselineSystemPrompt(DemoPaths paths)
    {
        var benchmarkPath = Path.Combine(paths.LabDirectory, "benchmark_smoke_test_v2.json");
        using var document = JsonDocument.Parse(File.ReadAllText(benchmarkPath));
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object
            || !root.TryGetProperty("system_prompt", out var promptElement)
            || promptElement.ValueKind != JsonValueKind.String)
            throw new InvalidDataException($"El benchmark no contiene un campo de texto 'system_prompt': {benchmarkPath}.");

        var prompt = promptElement.GetString();
        if (string.IsNullOrWhiteSpace(prompt))
            throw new InvalidDataException($"El 'system_prompt' del benchmark está vacío: {benchmarkPath}.");
        return prompt;
    }

    private static PromptRevision LoadRevision(DemoPaths paths, string baselinePrompt)
    {
        var revisionPath = Path.Combine(paths.LabDirectory, "demo", "prompts", "human_review_20261109.json");
        using var document = JsonDocument.Parse(File.ReadAllText(revisionPath));
        var root = document.RootElement;
        if (root.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException($"La revisión de prompts debe ser un objeto JSON: {revisionPath}.");

        RequireEqual(root, "schema_version", RevisionSchemaVersion, revisionPath);
        RequireEqual(root, "id", RevisionId, revisionPath);
        RequireEqual(root, "status", RevisionStatus, revisionPath);
        RequireSha256(root, "source_backup_sha256", SourceBackupSha256, revisionPath);
        RequireSha256(root, "baseline_system_prompt_sha256", Sha256(baselinePrompt), revisionPath);

        var commonAppendix = RequiredNonemptyString(root, "common_appendix", revisionPath);
        if (!root.TryGetProperty("family_appendices", out var familyElement)
            || familyElement.ValueKind != JsonValueKind.Object)
            throw new InvalidDataException($"Falta el objeto 'family_appendices' en {revisionPath}.");

        var familyAppendices = new Dictionary<string, string>(StringComparer.Ordinal);
        foreach (var family in new[] { "qwen", "minicpm", "gemma" })
            familyAppendices.Add(family, RequiredNonemptyString(familyElement, family, revisionPath));

        return new PromptRevision(commonAppendix, familyAppendices);
    }

    private static string? SelectReviewedFamily(string modelId)
    {
        var matches = new List<string>(capacity: 3);
        if (modelId.Contains("qwen35-4b", StringComparison.OrdinalIgnoreCase))
            matches.Add("qwen");
        if (modelId.Contains("minicpm5", StringComparison.OrdinalIgnoreCase))
            matches.Add("minicpm");
        if (modelId.Contains("gemma4", StringComparison.OrdinalIgnoreCase))
            matches.Add("gemma");

        if (matches.Count > 1)
            throw new InvalidDataException($"El identificador de modelo '{modelId}' coincide con más de una familia de revisión.");
        return matches.Count == 1 ? matches[0] : null;
    }

    private static void RequireEqual(JsonElement element, string property, string expected, string path)
    {
        var actual = RequiredNonemptyString(element, property, path);
        if (!string.Equals(actual, expected, StringComparison.Ordinal))
            throw new InvalidDataException($"El campo '{property}' de la revisión no coincide con el valor esperado: {path}.");
    }

    private static void RequireSha256(JsonElement element, string property, string expected, string path)
    {
        var actual = RequiredNonemptyString(element, property, path);
        if (actual.Length != 64 || !actual.All(Uri.IsHexDigit)
            || !string.Equals(actual, expected, StringComparison.OrdinalIgnoreCase))
            throw new InvalidDataException($"El SHA-256 '{property}' de la revisión no es válido o no coincide: {path}.");
    }

    private static string RequiredNonemptyString(JsonElement element, string property, string path)
    {
        if (!element.TryGetProperty(property, out var value) || value.ValueKind != JsonValueKind.String)
            throw new InvalidDataException($"Falta el campo de texto '{property}' en {path}.");

        var result = value.GetString();
        if (string.IsNullOrWhiteSpace(result))
            throw new InvalidDataException($"El campo de texto '{property}' está vacío en {path}.");
        return result;
    }

    private static string Sha256(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value))).ToLowerInvariant();

    private sealed record PromptRevision(string CommonAppendix, IReadOnlyDictionary<string, string> FamilyAppendices);
}
