using WritingDemo.Core;

namespace WritingApp.Shared;

public sealed record BackendTrial(string Backend, double Seconds, int Tokens, string FinishReason,
    string ParserStatus, string? Failure);

public sealed record BackendCalibration(string Key, string ModelId, DateTimeOffset DateUtc,
    string Driver, string SelectedBackend, string Reason, BackendTrial[] Cpu, BackendTrial[] Vulkan);

public static class BackendCalibrationPolicy
{
    public const string Version = "paired-writing-v1";
    public const int Samples = 3;
    public const double RequiredSpeedup = 1.15;

    public static (bool UseVulkan, string Reason) Decide(IReadOnlyList<BackendTrial> cpu, IReadOnlyList<BackendTrial> vulkan)
    {
        if (cpu.Count != Samples || vulkan.Count != Samples ||
            cpu.Any(t => !Completed(t)) || vulkan.Any(t => !Completed(t)))
            return (false, "CPU seleccionada. La comparación requiere tres evaluaciones completas por backend.");
        if (vulkan.Count(Usable) < cpu.Count(Usable) || !vulkan.All(Usable))
            return (false, "CPU seleccionada. Vulkan no completó las tres evaluaciones con JSON utilizable.");
        var cpuMedian = Median(cpu.Select(t => t.Seconds));
        var vkMedian = Median(vulkan.Select(t => t.Seconds));
        if (cpuMedian < vkMedian * RequiredSpeedup)
            return (false, $"CPU seleccionada. Mediana CPU {cpuMedian:F1} s y Vulkan {vkMedian:F1} s, mejora inferior al 15 %.");
        return (true, $"Vulkan medido. Mediana {vkMedian:F1} s frente a {cpuMedian:F1} s en CPU.");
    }

    private static bool Completed(BackendTrial trial) =>
        trial.Failure is null && trial.FinishReason == "stop" && double.IsFinite(trial.Seconds) &&
        trial.Seconds > 0 && trial.Tokens > 0;

    private static bool Usable(BackendTrial trial) => trial.ParserStatus is "STRICT" or "RECOVERED";

    public static double Median(IEnumerable<double> values)
    {
        var sorted = values.Order().ToArray();
        return sorted.Length == 0 ? 0 : sorted[sorted.Length / 2];
    }

    public static readonly WritingExercise Exercise = new("backend-calibration-v1", "A1",
        "Daily routine", "Write two short sentences about your morning routine.",
        "I wake up at seven. I eat breakfast at home.",
        "I wakes up at seven. I eat breakfast at home.");
}
