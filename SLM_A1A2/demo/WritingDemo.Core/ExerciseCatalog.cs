namespace WritingDemo.Core;

public static class ExerciseCatalog
{
    // These are short, hand-written demo prompts. The examples are visible to
    // learners as practice models; they are not benchmark gold labels and must
    // not be included in an inference request unless a learner selects that
    // exact example as their own text.
    private static readonly IReadOnlyList<WritingExercise> Exercises = Array.AsReadOnly(new WritingExercise[]
    {
        new WritingExercise(
            "demo-a1-my-day",
            "A1",
            "My day",
            "Write two short sentences about your morning routine.",
            "I wake up at seven. I eat breakfast at home.",
            "I wakes up at seven. I eat breakfast at home."),
        new WritingExercise(
            "demo-a1-friend-weekend",
            "A1",
            "A friend’s weekend",
            "Write two short sentences about what a friend does at the weekend.",
            "My friend plays soccer on Saturday. He watches a film at night.",
            "My friend play soccer on Saturday. He watches a film at night."),
        new WritingExercise(
            "demo-a2-weekend-with-a-friend",
            "A2",
            "A weekend with a friend",
            "Write three short sentences about what you did last weekend with a friend. Use the past tense.",
            "I met my friend on Saturday. We went to the park and played football. We ate lunch together.",
            "I met my friend on Saturday. We goed to the park and played football. We ate lunch together."),
        new WritingExercise(
            "demo-a2-day-out",
            "A2",
            "A day out",
            "Write three short sentences about a day out you enjoyed. Say where you went and what you did.",
            "Last Sunday, I visited a museum with my cousin. We saw interesting paintings and had lunch nearby. The weather was warm, so we walked home.",
            "Last Sunday, I visited a museum with my cousin. We saw interesting paintings and eated lunch nearby. The weather was warm, so we walked home.")
    });

    public static IReadOnlyList<WritingExercise> All => Exercises;
}
