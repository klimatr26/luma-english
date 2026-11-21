using System.Text.Json;
using System.Text.Json.Serialization;
using WritingDemo.Core;

namespace Course.Core;

public sealed record LessonBlock(string Kind, string Text, string[][] Rows);
public sealed record ChoiceOption(string Id, string Text);
public sealed record CourseActivity(string Id, string Type, string Prompt,
    ChoiceOption[]? Options = null, string? Answer = null, string? Explanation = null, string Level = "A1",
    [property: JsonPropertyName("correct_example")] string? CorrectExample = null,
    [property: JsonPropertyName("incorrect_example")] string? IncorrectExample = null,
    [property: JsonPropertyName("reference_correction")] string? ReferenceCorrection = null)
{
    public bool IsWriting => Type == "writing";
    public string TypeLabel => Type switch { "single_choice" => "Elige una opción", "one_word" => "Completa una palabra", _ => "Writing · evaluación local" };
    public WritingExercise ToExercise() => IsWriting
        ? new(Id, Level, "Writing del curso", Prompt, CorrectExample ?? "", IncorrectExample ?? "")
        : throw new InvalidOperationException("Esta actividad se corrige con una clave, sin IA.");
}
public sealed record CourseUnit(string Id, string Title, string Subtitle, string Summary, string Label,
    int Minutes, LessonBlock[] Lessons, CourseActivity[] Activities);
public sealed record CourseDefinition(string Id, string Version, string Title, string Level,
    [property: JsonPropertyName("source_sha256")] string SourceSha256, CourseUnit[] Units);

public interface ICourseRepository
{
    CourseDefinition Course { get; }
    CourseActivity Activity(string id);
}

public sealed class EmbeddedCourse : ICourseRepository
{
    public CourseDefinition Course { get; }
    public EmbeddedCourse()
    {
        using var source = typeof(EmbeddedCourse).Assembly.GetManifestResourceStream("Course.Core.Assets.course-a1.json")
            ?? throw new InvalidDataException("No se encontró el contenido del curso.");
        Course = JsonSerializer.Deserialize(source, CourseJsonContext.Default.CourseDefinition)
            ?? throw new InvalidDataException("El curso está vacío.");
        Validate(Course);
    }
    public CourseActivity Activity(string id) => Course.Units.SelectMany(u => u.Activities).First(a => a.Id == id);
    public static void Validate(CourseDefinition course)
    {
        if (course.Version != "1.0.0" || course.Units.Length != 3 || course.Level != "A1") throw new InvalidDataException("Versión de curso incompatible.");
        var allIds = new HashSet<string>(StringComparer.Ordinal);
        foreach (var unit in course.Units)
        {
            if (!allIds.Add(unit.Id) || string.IsNullOrWhiteSpace(unit.Title) || unit.Lessons.Length < 5 || unit.Minutes <= 0)
                throw new InvalidDataException("Unidad incompleta.");
            if (unit.Activities.Count(a => a.Type == "single_choice") != 5 || unit.Activities.Count(a => a.Type == "one_word") != 5 ||
                unit.Activities.Count(a => a.Type == "writing") != 1 || unit.Activities.Length != 11) throw new InvalidDataException("Cuotas del curso incorrectas.");
            foreach (var block in unit.Lessons)
                if (block.Kind is not ("heading" or "paragraph" or "bullet" or "table" or "example") ||
                    (block.Kind == "table" ? block.Rows.Length < 2 || block.Rows.Any(r => r.Length != block.Rows[0].Length) : string.IsNullOrWhiteSpace(block.Text)))
                    throw new InvalidDataException("Bloque de lección inválido.");
            foreach (var activity in unit.Activities)
            {
                if (!allIds.Add(activity.Id) || !activity.Id.StartsWith(unit.Id + "-", StringComparison.Ordinal) || string.IsNullOrWhiteSpace(activity.Prompt))
                    throw new InvalidDataException("Identidad o consigna de actividad inválida.");
                if (activity.Type == "single_choice" && (activity.Options is not { Length: >= 2 } options ||
                    options.Select(o => o.Id).Distinct().Count() != options.Length || options.Count(o => o.Id == activity.Answer) != 1))
                    throw new InvalidDataException("Clave de opción inválida.");
                if (activity.Type == "one_word" && (activity.Prompt.Split("____").Length != 2 || string.IsNullOrWhiteSpace(activity.Answer) ||
                    activity.Answer.Any(c => !char.IsLetter(c)) || activity.Answer != activity.Answer.ToLowerInvariant()))
                    throw new InvalidDataException("Clave o hueco inválido.");
                if (activity.IsWriting && (activity.Level != "A1" || string.IsNullOrWhiteSpace(activity.CorrectExample) ||
                    string.IsNullOrWhiteSpace(activity.IncorrectExample) || activity.CorrectExample == activity.IncorrectExample ||
                    activity.ReferenceCorrection != activity.CorrectExample)) throw new InvalidDataException("Ejemplo de Writing incompleto.");
            }
        }
    }
}

public sealed record ClosedResult(bool Correct, string Explanation, string Expected);
public static class ClosedExercise
{
    public static ClosedResult Check(CourseActivity activity, string answer)
    {
        if (activity.IsWriting) throw new ArgumentException("Writing no tiene una clave cerrada.");
        if (string.IsNullOrWhiteSpace(answer)) throw new ArgumentException("Elige una opción o escribe una palabra antes de comprobar.");
        var normalized = answer.Trim();
        if (activity.Type == "single_choice" && !activity.Options!.Any(o => o.Id == normalized)) throw new ArgumentException("Elige una de las opciones disponibles.");
        return new(string.Equals(normalized, activity.Answer, activity.Type == "one_word" ? StringComparison.OrdinalIgnoreCase : StringComparison.Ordinal),
            activity.Explanation ?? "", activity.Type == "single_choice" ? activity.Options!.First(o => o.Id == activity.Answer).Text : activity.Answer!);
    }
}

[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase, WriteIndented = true, UseStringEnumConverter = true)]
[JsonSerializable(typeof(CourseDefinition))]
[JsonSerializable(typeof(CourseSettings))]
[JsonSerializable(typeof(BackupManifest))]
[JsonSerializable(typeof(HistoryEntry[]))]
[JsonSerializable(typeof(AutoAdviceProfile))]
[JsonSerializable(typeof(PreparationFailureTrace))]
public partial class CourseJsonContext : JsonSerializerContext;
