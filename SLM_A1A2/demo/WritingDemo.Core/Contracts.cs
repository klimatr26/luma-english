using System.Text.Json;

namespace WritingDemo.Core;

public sealed record ModelSpec(string Id, string DisplayName, string FamilyKey, string Quantization,
    string RelativePath, string ExpectedSha256, long ExpectedSize, string? DownloadUrl,
    string SourcePage, string LicenseLabel, JsonElement Generation, bool TemplateThinkingToggle,
    string Note);

public sealed record TransferProgress(string Status, long BytesReceived = 0, long? TotalBytes = null);
public sealed record WritingExercise(string Id, string Level, string Title, string Task,
    string CorrectExample, string IncorrectExample);
public sealed record FeedbackEdit(string Original, string Correction, string Type, string Explanation);
public sealed record ParsedFeedback(bool IsCorrect, string CorrectedText, IReadOnlyList<FeedbackEdit> Errors, string Feedback);
public sealed record FeedbackParseResult(string Status, ParsedFeedback? Value, string? Error, string RawText, string? ExtractedJson);
public sealed record GenerationResult(string Content, string ApiJson, string FinishReason, double ElapsedSeconds,
    string? ReasoningContent = null, string? PromptProfileId = null, string? SystemPromptSha256 = null);

public sealed class DemoPaths(string labDirectory)
{
    public string LabDirectory { get; } = Path.GetFullPath(labDirectory);
    public string ManifestPath => Path.Combine(LabDirectory, "manifests", "experiment_manifest_120.json");
    public string DefaultModelDirectory => Path.Combine(LabDirectory, "models");
    public string DefaultServerPath => Path.Combine(LabDirectory, "tools", "llama.cpp", "b11457", "llama-server.exe");
    public string SessionDirectory => Path.Combine(LabDirectory, "logs", "writing_demo");
    public static DemoPaths Locate(string? workspace = null)
    {
        if (!string.IsNullOrWhiteSpace(workspace))
        {
            var candidate = Directory.Exists(Path.Combine(workspace, "SLM_A1A2")) ? Path.Combine(workspace, "SLM_A1A2") : workspace;
            if (File.Exists(Path.Combine(candidate, "manifests", "experiment_manifest_120.json"))) return new(candidate);
            throw new DirectoryNotFoundException("No se encontró el proyecto SLM_A1A2 en la carpeta indicada.");
        }
        foreach (var start in new[] { AppContext.BaseDirectory, Environment.CurrentDirectory })
            for (var dir = new DirectoryInfo(start); dir != null; dir = dir.Parent)
            {
                if (File.Exists(Path.Combine(dir.FullName, "manifests", "experiment_manifest_120.json"))) return new(dir.FullName);
                if (File.Exists(Path.Combine(dir.FullName, "SLM_A1A2", "manifests", "experiment_manifest_120.json"))) return new(Path.Combine(dir.FullName, "SLM_A1A2"));
            }
        throw new DirectoryNotFoundException("Abre la aplicación desde el proyecto o usa --workspace RUTA.");
    }
}
