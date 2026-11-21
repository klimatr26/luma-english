using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using WritingDemo.Core;
namespace WritingApp.Shared;

public static class PortableCatalog
{
    public static IReadOnlyList<ModelEntry> All { get; } = Load();
    internal static Stream Resource(string name) => typeof(PortableCatalog).Assembly.GetManifestResourceStream("WritingApp.Shared.Assets." + name)
        ?? throw new InvalidDataException("Missing embedded app resource: " + name);
    private static IReadOnlyList<ModelEntry> Load()
    {
        using var stream = Resource("catalog.json");
        var result = JsonSerializer.Deserialize(stream, AppJsonContext.Default.ModelEntryArray) ?? throw new InvalidDataException("Empty catalog.");
        if (result.Length == 0 || result.Select(m => m.Id).Distinct().Count() != result.Length) throw new InvalidDataException("Invalid catalog identities.");
        foreach (var model in result)
        {
            if (model.SizeBytes <= 0 || model.Sha256.Length != 64 || !model.Sha256.All(Uri.IsHexDigit)) throw new InvalidDataException("Invalid model pin.");
            ModelStore.SafePath(Path.GetTempPath(), model.RelativePath);
            if (model.DownloadUrl is { } url && (!Uri.TryCreate(url,UriKind.Absolute,out var uri) || uri.Scheme != "https" || uri.Host != "huggingface.co")) throw new InvalidDataException("Invalid model source.");
        }
        return Array.AsReadOnly(result);
    }
}

public static class PortablePrompt
{
    private static readonly Dictionary<string,string> Prompts = Read();
    private static Dictionary<string,string> Read()
    {
        using var stream=PortableCatalog.Resource("prompts.json");
        return JsonSerializer.Deserialize(stream,AppJsonContext.Default.DictionaryStringString) ?? throw new InvalidDataException("Missing prompts.");
    }
    public static string For(ModelEntry model) => Prompts.TryGetValue(model.Family,out var prompt) ? prompt : Prompts["baseline"];
    public static string Hash(ModelEntry model) => Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(For(model))));
    public static string BuildUser(WritingExercise exercise,string text) => $"Level: {exercise.Level}\nTask: {exercise.Task}\nStudent text: {text}";
}
