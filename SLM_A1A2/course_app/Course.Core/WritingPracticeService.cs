using WritingApp.Shared;
using WritingDemo.Core;

namespace Course.Core;

public sealed class WritingPracticeService(CourseStore store, CourseRuntime runtime)
{
    public async Task<ReviewSession> EvaluateAsync(WritingExercise exercise, string text, bool laboratory,
        int maximumAttempts, IProgress<EvaluationAttempt>? progress, CancellationToken ct)
    {
        if (string.IsNullOrWhiteSpace(text) || text.Length > 4000 || string.IsNullOrWhiteSpace(exercise.Task) || exercise.Task.Length > 1000)
            throw new ArgumentException("Escribe una respuesta de 1 a 4000 caracteres y una consigna de 1 a 1000. El contexto también debe permitir procesarlas completas.");
        if (maximumAttempts is < 1 or > 3) throw new ArgumentOutOfRangeException(nameof(maximumAttempts));
        var model = runtime.LoadedModel ?? throw new InvalidOperationException("Prepara un modelo para evaluar tu Writing.");
        var engine = runtime.State ?? throw new InvalidOperationException("El motor no está preparado.");
        var id = Guid.NewGuid().ToString("N");
        var attempts = new List<EvaluationAttempt>();
        var date = DateTimeOffset.UtcNow;
        await store.StartWritingAsync(id, exercise.Id, laboratory, text).ConfigureAwait(false);
        try
        {
            for (int index = 0; index < maximumAttempts; index++)
            {
                ct.ThrowIfCancellationRequested();
                var output = await runtime.GenerateAsync(exercise, text, 42 + index, ct).ConfigureAwait(false);
                // Durable RAW precedes parsing and the decision to retry.
                await store.AppendRawAsync(id, index + 1, 42 + index, output).ConfigureAwait(false);
                var parsed = FeedbackParser.Parse(output.Content, text);
                var attempt = new EvaluationAttempt(index + 1, 42 + index, output, parsed);
                attempts.Add(attempt);
                await store.UpdateAttemptAsync(id, attempt.Number, parsed.Status).ConfigureAwait(false);
                progress?.Report(attempt);
                var usable = parsed.Status is "STRICT" or "RECOVERED";
                var checkpoint = new ReviewSession("writing_course/1.0", laboratory ? "WRITING_LAB_NOT_BENCHMARK" : "COURSE_PRACTICE_NOT_BENCHMARK",
                    date, model, runtime.Device, engine, exercise.Id, exercise.Level, exercise.Task, text,
                    PortablePrompt.Hash(model), maximumAttempts, attempts.ToArray(), usable, usable ? "usable_envelope" : "unusable_envelope");
                await store.FinishWritingAsync(id, usable ? "usable" : index + 1 == maximumAttempts ? "unusable" : "running",
                    usable ? "Retroalimentación recibida. El juicio lingüístico pertenece al modelo." : "El modelo no devolvió una evaluación interpretable.", checkpoint).ConfigureAwait(false);
                if (usable || index + 1 == maximumAttempts) return checkpoint;
            }
            throw new InvalidOperationException("No hubo una tentativa de evaluación.");
        }
        catch (OperationCanceledException)
        {
            await store.FinishWritingAsync(id, "cancelled", "Evaluación cancelada. Se conservan los intentos recibidos y el borrador.", null).ConfigureAwait(false); throw;
        }
        catch (Exception error)
        {
            await store.FinishWritingAsync(id, "technical_error", error.Message, null).ConfigureAwait(false); throw;
        }
    }
}
