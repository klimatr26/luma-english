using System.Text.Json;
using WritingDemo.Core;
namespace WritingApp.Shared;

public static class EvaluationService
{
    public static async Task<ReviewSession> EvaluateAsync(AppServices services,ModelEntry model,EngineState engine,
        WritingExercise exercise,string studentText,int maxAttempts,IProgress<EvaluationAttempt>? progress,CancellationToken ct)
    {
        if(maxAttempts is <1 or >3) throw new ArgumentOutOfRangeException(nameof(maxAttempts));
        if(string.IsNullOrWhiteSpace(studentText)||studentText.Length>4000||string.IsNullOrWhiteSpace(exercise.Task)||exercise.Task.Length>1000) throw new ArgumentException("Usa una consigna de 1–1000 caracteres y una respuesta de 1–4000.");
        var attempts=new List<EvaluationAttempt>();
        for(int index=0;index<maxAttempts;index++)
        {
            ct.ThrowIfCancellationRequested();
            // Retry only unusable envelopes. No linguistic quality test or hidden answer is consulted.
            var output=await services.Engine.GenerateAsync(exercise,studentText,42+index,ct);
            var parsed=FeedbackParser.Parse(output.Content,studentText);
            var attempt=new EvaluationAttempt(index+1,42+index,output,parsed);
            attempts.Add(attempt); progress?.Report(attempt);
            var usable=parsed.Status is "STRICT" or "RECOVERED";
            var checkpoint=new ReviewSession("writing_cross_demo/1.1","INTERACTIVE_DEMO_NOT_BENCHMARK",DateTimeOffset.UtcNow,
                model,services.Device,engine,exercise.Id,exercise.Level,exercise.Task,studentText,PortablePrompt.Hash(model),maxAttempts,
                attempts.ToArray(),usable,usable?"usable_envelope":"unusable_envelope");
            // Write every returned attempt before deciding to try another; never discard the first response.
            await services.Sessions.SaveAsync(checkpoint,CancellationToken.None);
            if(usable || index+1==maxAttempts) return checkpoint;
        }
        throw new InvalidOperationException("No evaluation attempt.");
    }
}

public sealed class SessionStore(string directory)
{
    public string DirectoryPath { get; }=Path.GetFullPath(directory);
    public static string Serialize(ReviewSession session)=>JsonSerializer.Serialize(session,AppJsonContext.Default.ReviewSession);
    public async Task<string> SaveAsync(ReviewSession session,CancellationToken ct)
    {
        Directory.CreateDirectory(DirectoryPath);
        var name=$"session-{DateTime.UtcNow:yyyyMMddTHHmmssfffZ}-{Guid.NewGuid():N}.json";
        var path=Path.Combine(DirectoryPath,name);
        await using var file=new FileStream(path,FileMode.CreateNew,FileAccess.Write,FileShare.Read);
        await JsonSerializer.SerializeAsync(file,session,AppJsonContext.Default.ReviewSession,ct);
        await file.FlushAsync(ct);return path;
    }
}
