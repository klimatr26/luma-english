using WritingDemo.Core;
using System.Text.Json;

var original = "I like to read.";
var valid = """
    {"is_correct":false,"corrected_text":"I like reading.","errors":[{"original":"to read","correction":"reading","type":"grammar","explanation":"Use a gerund here."}],"feedback":"Good start."}
    """;

var strict = FeedbackParser.Parse(valid, original);
Check.Equal("STRICT", strict.Status, "valid exact JSON is strict");
Check.True(strict.Value is { IsCorrect: false, Errors.Count: 1 }, "strict value is parsed");
Check.Equal(valid, strict.RawText, "raw response is preserved");
Check.Null(strict.ExtractedJson, "strict parse does not claim recovery");

var correct = """{"is_correct":true,"corrected_text":"I like to read.","errors":[],"feedback":"Correct."}""";
Check.Equal("STRICT", FeedbackParser.Parse(correct, original).Status, "coherent correct response is strict");

var duplicateRoot = """{"is_correct":false,"is_correct":true,"corrected_text":"x","errors":[],"feedback":"y"}""";
Check.Equal("INVALID_JSON", FeedbackParser.Parse(duplicateRoot, original).Status, "duplicate root keys are rejected");
var duplicateNested = """{"is_correct":false,"corrected_text":"x","errors":[{"original":"a","original":"b","correction":"b","type":"grammar","explanation":"e"}],"feedback":"y"}""";
Check.Equal("INVALID_JSON", FeedbackParser.Parse(duplicateNested, original).Status, "duplicate nested keys are rejected");
Check.Equal("INVALID_JSON", FeedbackParser.Parse($"```json\n{duplicateRoot}\n```", original).Status,
    "duplicate root keys are rejected during fenced recovery too");
Check.Equal("INVALID_JSON", FeedbackParser.Parse("Model output: " + duplicateNested, original).Status,
    "duplicate nested keys are rejected during prose recovery too");

var fencedRaw = $"```json\n{correct}\n```";
var fenced = FeedbackParser.Parse(fencedRaw, original);
Check.Equal("RECOVERED", fenced.Status, "one surrounding JSON fence is recovered");
Check.Equal(fencedRaw, fenced.RawText, "fenced raw response is preserved");
Check.Equal(correct, fenced.ExtractedJson, "fenced JSON is exposed as extracted text");

var proseRaw = "Here is the result: {\"is_correct\":false,\"corrected_text\":\"I like reading.\",\"errors\":[{\"original\":\"to read\",\"correction\":\"reading\",\"type\":\"grammar\",\"explanation\":\"Use a gerund here. A } inside a string is not a delimiter.\"}],\"feedback\":\"Good start.\"} Thank you.";
var prose = FeedbackParser.Parse(proseRaw, original);
Check.Equal("RECOVERED", prose.Status, "single object with surrounding prose is recovered");
Check.Equal(proseRaw, prose.RawText, "prose raw response is preserved");
Check.True(prose.ExtractedJson?.Contains("A } inside a string", StringComparison.Ordinal) == true,
    "recovery scanner respects braces inside quoted strings");

var quotedOriginal = "He said \"go {now}\" and used a \\ mark.";
var escapedJson = JsonSerializer.Serialize(new Dictionary<string, object?>
{
    ["is_correct"] = true,
    ["corrected_text"] = quotedOriginal,
    ["errors"] = Array.Empty<object>(),
    ["feedback"] = "The braces }{ and quotation marks \"stay\" in this feedback."
});
var escapedStrict = FeedbackParser.Parse(" \r\n\t" + escapedJson + " \n", quotedOriginal);
Check.Equal("STRICT", escapedStrict.Status, "valid whitespace-wrapped JSON with escaped braces and quotes stays strict");
Check.Equal(quotedOriginal, escapedStrict.Value?.CorrectedText, "escaped text round-trips without trimming or alteration");
var escapedRecovered = FeedbackParser.Parse("Result: " + escapedJson + " end.", quotedOriginal);
Check.Equal("RECOVERED", escapedRecovered.Status, "recovery handles escaped quotes, backslashes and braces");
Check.Equal(escapedJson, escapedRecovered.ExtractedJson, "recovery extracts only the complete JSON object");

var multiple = $"First: {correct} Second: {correct}";
Check.Equal("INVALID_JSON", FeedbackParser.Parse(multiple, original).Status, "multiple objects are never selected between");
var unmatchedThenNested = "prefix { broken {" + correct + "}";
Check.Equal("INVALID_JSON", FeedbackParser.Parse(unmatchedThenNested, original).Status,
    "an unmatched outer brace cannot hide a later nested candidate");

var stringBoolean = """{"is_correct":"false","corrected_text":"x","errors":[],"feedback":"y"}""";
Check.Equal("INVALID_SCHEMA", FeedbackParser.Parse(stringBoolean, original).Status, "boolean strings are not booleans");
var extraKey = """{"is_correct":false,"corrected_text":"x","errors":[],"feedback":"y","score":1}""";
Check.Equal("INVALID_SCHEMA", FeedbackParser.Parse(extraKey, original).Status, "extra root keys are rejected");
var missingKey = """{"is_correct":false,"corrected_text":"x","errors":[]}""";
Check.Equal("INVALID_SCHEMA", FeedbackParser.Parse(missingKey, original).Status, "missing root keys are rejected");
var wrongErrorKey = """{"is_correct":false,"corrected_text":"x","errors":[{"original":"a","correction":"b","type":"grammar","explanation":"e","confidence":"high"}],"feedback":"y"}""";
Check.Equal("INVALID_SCHEMA", FeedbackParser.Parse(wrongErrorKey, original).Status, "extra error keys are rejected");
var nonFinite = """{"is_correct":false,"corrected_text":"x","errors":[],"feedback":"y","n":NaN}""";
Check.Equal("INVALID_JSON", FeedbackParser.Parse(nonFinite, original).Status, "non-finite JSON numbers are rejected");

var contradiction = """{"is_correct":true,"corrected_text":"I like reading.","errors":[{"original":"to read","correction":"reading","type":"grammar","explanation":"Use a gerund here."}],"feedback":"Correct."}""";
var inconsistent = FeedbackParser.Parse(contradiction, original);
Check.Equal("INCONSISTENT", inconsistent.Status, "contradictory correctness decisions are flagged");
Check.True(inconsistent.Value is { IsCorrect: true, Errors.Count: 1 }, "inconsistent decision is preserved for display");

var falseWithoutErrors = """{"is_correct":false,"corrected_text":"I changed it.","errors":[],"feedback":"Needs work."}""";
Check.Equal("INCONSISTENT", FeedbackParser.Parse(falseWithoutErrors, original).Status,
    "incorrect response without any listed errors is flagged");

foreach (var sample in new[] { "", " ", "{}", "}", "{ nested }", "quote: \"x\"", "slash: \\ end", "line 1\r\nline 2", "café ☃" })
{
    var sampleJson = JsonSerializer.Serialize(new Dictionary<string, object?>
    {
        ["is_correct"] = true,
        ["corrected_text"] = sample,
        ["errors"] = Array.Empty<object>(),
        ["feedback"] = "Literal braces { } and quotes \" in a JSON string."
    });

    var parsedStrict = FeedbackParser.Parse("\t" + sampleJson + "\r\n", sample);
    Check.Equal("STRICT", parsedStrict.Status, "generated valid JSON remains strict for escaped sample text");
    Check.Equal(sample, parsedStrict.Value?.CorrectedText, "generated sample text round-trips exactly");

    var parsedRecovered = FeedbackParser.Parse("Prefix: " + sampleJson + " Suffix.", sample);
    Check.Equal("RECOVERED", parsedRecovered.Status, "single generated object is recovered from surrounding prose");
    Check.Equal(sampleJson, parsedRecovered.ExtractedJson, "recovery preserves the generated JSON object exactly");
}

Check.Equal(4, ExerciseCatalog.All.Count, "catalog contains four demo-only exercises");
Check.Equal(2, ExerciseCatalog.All.Count(exercise => exercise.Level == "A1"), "catalog has two A1 exercises");
Check.Equal(2, ExerciseCatalog.All.Count(exercise => exercise.Level == "A2"), "catalog has two A2 exercises");

Console.WriteLine("Feedback parser and exercise catalog checks passed.");

static class Check
{
    public static void True(bool condition, string description)
    {
        if (!condition)
        {
            throw new InvalidOperationException($"FAIL: {description}");
        }
    }

    public static void Equal<T>(T expected, T actual, string description)
    {
        if (!EqualityComparer<T>.Default.Equals(expected, actual))
        {
            throw new InvalidOperationException($"FAIL: {description}; expected '{expected}', got '{actual}'.");
        }
    }

    public static void Null(object? value, string description)
    {
        if (value is not null)
        {
            throw new InvalidOperationException($"FAIL: {description}; expected null.");
        }
    }
}
