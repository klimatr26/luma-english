using System.Text.Json;
using WritingApp.Shared;

namespace Course.Core;

/// <summary>Extends the product catalog without changing the catalog frozen by the 200-case experiment.</summary>
public static class CourseModelCatalog
{
    public static IReadOnlyList<ModelEntry> All { get; } = Load();
    private static IReadOnlyList<ModelEntry> Load()
    {
        using var source = typeof(CourseModelCatalog).Assembly.GetManifestResourceStream("Course.Core.Assets.extra-models.json")
            ?? throw new InvalidDataException("Falta el catálogo adicional de la aplicación final.");
        var extra = JsonSerializer.Deserialize(source, AppJsonContext.Default.ModelEntryArray) ?? throw new InvalidDataException("Catálogo adicional vacío.");
        var all = PortableCatalog.All.Concat(extra).ToArray();
        if (all.Length != 18 || all.Select(m => m.Id).Distinct(StringComparer.Ordinal).Count() != all.Length)
            throw new InvalidDataException("Identidades del catálogo final inválidas.");
        foreach (var model in extra)
        {
            ModelStore.SafePath(Path.GetTempPath(), model.RelativePath);
            if (model.SizeBytes <= 0 || model.Sha256.Length != 64 || !model.Sha256.All(Uri.IsHexDigit) ||
                !Uri.TryCreate(model.DownloadUrl, UriKind.Absolute, out var uri) || uri.Scheme != "https" || uri.Host != "huggingface.co" || uri.AbsolutePath.Contains("/main/", StringComparison.Ordinal))
                throw new InvalidDataException("Procedencia de modelo adicional inválida.");
        }
        return Array.AsReadOnly(all);
    }
}
