using WritingDemo.Core;
namespace WritingApp.Shared;

public enum BackendPreference { AutoVulkanCpu, Vulkan, Cpu }
public sealed record SamplingOptions(double Temperature, double TopP, int TopK, double MinP,
    double RepeatPenalty, double PresencePenalty, double FrequencyPenalty, int MaxTokens = 512);
public sealed record ModelEntry(string Id, string Name, string Family, string Quantization,
    string RelativePath, long SizeBytes, string Sha256, string? DownloadUrl, string SourceUrl,
    string License, SamplingOptions Sampling, bool ThinkingToggle)
{
    public string Label => $"{Name} · {Quantization} · {SizeBytes / 1e9:F2} GB";
    public override string ToString() => Label;
}
public sealed record DeviceProfile(string Platform, string Architecture, long TotalMemoryBytes,
    long AvailableMemoryBytes, long FreeStorageBytes, bool IsEmulator = false, string? GpuDescription = null);
public sealed record ModelRecommendation(string ModelId, long EstimatedMemoryBytes, bool FitsEstimate, string Reason);
public sealed record DownloadProgress(string Message, long ReceivedBytes, long TotalBytes,
    double BytesPerSecond = 0, double? RemainingSeconds = null);

public interface IModelDownloads
{
    bool ContinuesInBackground { get; }
    string? PendingModelId => null;
    Task<string> EnsureAsync(ModelEntry model, IProgress<DownloadProgress>? progress, CancellationToken ct);
    Task<string?> RecoverCompletedAsync(ModelEntry model, IProgress<DownloadProgress>? progress, CancellationToken ct)
        => Task.FromResult<string?>(null);
    Task CancelAsync(ModelEntry model);
}
public sealed record EngineState(BackendPreference Requested, string Backend, string? Device,
    int OffloadedLayers, string? FallbackReason, int ContextTokens, string ResponseFormat = "unconstrained",
    int? TotalLayers = null, string? AdapterId = null);
public sealed record InferenceMetrics(int PromptTokens, int OutputTokens, int DecodedTokens,
    double PromptSeconds, double DecodeSeconds, bool ClosedThinkingPrefill)
{
    public double? DecodeTokensPerSecond => DecodeSeconds > 0 ? DecodedTokens / DecodeSeconds : null;
}
public sealed record EngineOutput(string Content, string FinishReason, double Seconds, string? Diagnostics = null,
    InferenceMetrics? Metrics = null);

public interface IInferenceEngine : IAsyncDisposable
{
    Task<EngineState> LoadAsync(ModelEntry model, string modelPath, BackendPreference backend, int context, CancellationToken ct);
    Task<EngineOutput> GenerateAsync(WritingExercise exercise, string studentText, int seed, CancellationToken ct);
    Task UnloadAsync();
}

public sealed record EvaluationAttempt(int Number, int Seed, EngineOutput Output, FeedbackParseResult Parsed);
public sealed record ReviewSession(string SchemaVersion, string Purpose, DateTimeOffset DateUtc,
    ModelEntry Model, DeviceProfile Device, EngineState Engine, string ExerciseId, string Level,
    string Task, string StudentText, string SystemPromptSha256, int MaximumAttempts,
    EvaluationAttempt[] Attempts, bool Usable, string StopReason);

public sealed class AppServices(DeviceProfile device, ModelStore models, IInferenceEngine engine, SessionStore sessions,
    IModelDownloads? downloads = null)
{
    public DeviceProfile Device { get; } = device;
    public ModelStore ModelStore { get; } = models;
    public IInferenceEngine Engine { get; } = engine;
    public SessionStore Sessions { get; } = sessions;
    public IModelDownloads Downloads { get; } = downloads ?? models;
    public IReadOnlyList<ModelEntry> Models => PortableCatalog.All;
    public ModelRecommendation Recommendation => ModelRecommender.Recommend(Models, Device);
    public int DefaultContext => Device.Platform == "Android" ? 2048 : 4096;
}
