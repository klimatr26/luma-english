using System.Text.Json;

namespace WritingDemo.Core;

/// <summary>
/// Parses the model's feedback envelope without trying to decide whether the
/// linguistic feedback itself is correct. Only an unambiguous, valid envelope
/// is returned; callers must still treat INCONSISTENT as a warning, not a pass.
/// </summary>
public static class FeedbackParser
{
    private static readonly JsonDocumentOptions DocumentOptions = new()
    {
        AllowTrailingCommas = false,
        CommentHandling = JsonCommentHandling.Disallow,
        MaxDepth = 64
    };

    public static FeedbackParseResult Parse(string raw, string originalStudentText)
    {
        ArgumentNullException.ThrowIfNull(raw);
        ArgumentNullException.ThrowIfNull(originalStudentText);

        var strict = TryParseCandidate(raw, originalStudentText);
        if (strict.Status != ParseStatus.InvalidJson)
        {
            return ToResult(strict, raw, extractedJson: null, recovered: false);
        }

        var trimmed = raw.Trim();
        if (TryUnwrapJsonFence(trimmed, out var fencedJson))
        {
            var fenced = TryParseCandidate(fencedJson, originalStudentText);
            return ToResult(fenced, raw, fencedJson, recovered: fenced.Status is ParseStatus.Valid or ParseStatus.Inconsistent);
        }

        var scan = FindSingleObject(raw);
        if (scan.Error is not null)
        {
            return new FeedbackParseResult("INVALID_JSON", null, scan.Error, raw, null);
        }

        if (scan.ObjectText is null)
        {
            return new FeedbackParseResult("INVALID_JSON", null,
                "No se encontró un objeto JSON completo en la respuesta del modelo.", raw, null);
        }

        var recovered = TryParseCandidate(scan.ObjectText, originalStudentText);
        return ToResult(recovered, raw, scan.ObjectText,
            recovered: recovered.Status is ParseStatus.Valid or ParseStatus.Inconsistent);
    }

    private static FeedbackParseResult ToResult(ParseAttempt attempt, string raw, string? extractedJson, bool recovered)
    {
        var status = attempt.Status switch
        {
            ParseStatus.Valid => recovered ? "RECOVERED" : "STRICT",
            ParseStatus.Inconsistent => "INCONSISTENT",
            ParseStatus.InvalidSchema => "INVALID_SCHEMA",
            _ => "INVALID_JSON"
        };

        return new FeedbackParseResult(status, attempt.Value, attempt.Error, raw, extractedJson);
    }

    private static ParseAttempt TryParseCandidate(string json, string originalStudentText)
    {
        JsonDocument document;
        try
        {
            document = JsonDocument.Parse(json, DocumentOptions);
        }
        catch (JsonException exception)
        {
            return ParseAttempt.InvalidJson($"JSON inválido: {exception.Message}");
        }

        using (document)
        {
            if (ContainsDuplicateProperty(document.RootElement))
            {
                return ParseAttempt.InvalidJson("JSON inválido: hay claves duplicadas en uno o más objetos.");
            }

            if (document.RootElement.ValueKind != JsonValueKind.Object)
            {
                return ParseAttempt.InvalidSchema("La raíz debe ser un objeto JSON.");
            }

            var root = document.RootElement;
            if (!HasExactProperties(root, "is_correct", "corrected_text", "errors", "feedback"))
            {
                return ParseAttempt.InvalidSchema("El objeto raíz debe contener exactamente is_correct, corrected_text, errors y feedback.");
            }

            var correctElement = root.GetProperty("is_correct");
            var correctedTextElement = root.GetProperty("corrected_text");
            var errorsElement = root.GetProperty("errors");
            var feedbackElement = root.GetProperty("feedback");

            if (correctElement.ValueKind is not (JsonValueKind.True or JsonValueKind.False) ||
                correctedTextElement.ValueKind != JsonValueKind.String ||
                errorsElement.ValueKind != JsonValueKind.Array ||
                feedbackElement.ValueKind != JsonValueKind.String)
            {
                return ParseAttempt.InvalidSchema("is_correct debe ser booleano, corrected_text y feedback deben ser cadenas, y errors debe ser una lista.");
            }

            var edits = new List<FeedbackEdit>();
            foreach (var error in errorsElement.EnumerateArray())
            {
                if (error.ValueKind != JsonValueKind.Object ||
                    !HasExactProperties(error, "original", "correction", "type", "explanation"))
                {
                    return ParseAttempt.InvalidSchema("Cada elemento de errors debe contener exactamente original, correction, type y explanation.");
                }

                var original = error.GetProperty("original");
                var correction = error.GetProperty("correction");
                var type = error.GetProperty("type");
                var explanation = error.GetProperty("explanation");
                if (original.ValueKind != JsonValueKind.String ||
                    correction.ValueKind != JsonValueKind.String ||
                    type.ValueKind != JsonValueKind.String ||
                    explanation.ValueKind != JsonValueKind.String)
                {
                    return ParseAttempt.InvalidSchema("Los cuatro campos de cada error deben ser cadenas.");
                }

                edits.Add(new FeedbackEdit(
                    original.GetString()!, correction.GetString()!, type.GetString()!, explanation.GetString()!));
            }

            var value = new ParsedFeedback(
                correctElement.GetBoolean(),
                correctedTextElement.GetString()!,
                edits,
                feedbackElement.GetString()!);

            var consistencyProblem = FindConsistencyProblem(value, originalStudentText);
            return consistencyProblem is null
                ? ParseAttempt.Valid(value)
                : ParseAttempt.Inconsistent(value, consistencyProblem);
        }
    }

    private static string? FindConsistencyProblem(ParsedFeedback value, string originalStudentText)
    {
        var correctionMatchesInput = string.Equals(value.CorrectedText, originalStudentText, StringComparison.Ordinal);
        if (value.IsCorrect)
        {
            if (!correctionMatchesInput || value.Errors.Count != 0)
            {
                return "El modelo marcó el texto como correcto, pero corrected_text no coincide exactamente con el original o errors no está vacío.";
            }

            return null;
        }

        if (value.Errors.Count == 0)
        {
            return "El modelo marcó el texto como incorrecto, pero no proporcionó errores.";
        }

        if (correctionMatchesInput)
        {
            return "El modelo marcó el texto como incorrecto, pero corrected_text no cambia el texto original.";
        }

        return null;
    }

    private static bool HasExactProperties(JsonElement element, params string[] expectedNames)
    {
        if (element.EnumerateObject().Count() != expectedNames.Length)
        {
            return false;
        }

        foreach (var expectedName in expectedNames)
        {
            if (!element.TryGetProperty(expectedName, out _))
            {
                return false;
            }
        }

        return true;
    }

    private static bool ContainsDuplicateProperty(JsonElement element)
    {
        switch (element.ValueKind)
        {
            case JsonValueKind.Object:
            {
                var names = new HashSet<string>(StringComparer.Ordinal);
                foreach (var property in element.EnumerateObject())
                {
                    if (!names.Add(property.Name) || ContainsDuplicateProperty(property.Value))
                    {
                        return true;
                    }
                }

                return false;
            }
            case JsonValueKind.Array:
                return element.EnumerateArray().Any(ContainsDuplicateProperty);
            default:
                return false;
        }
    }

    private static bool TryUnwrapJsonFence(string text, out string json)
    {
        json = string.Empty;
        if (!text.StartsWith("```", StringComparison.Ordinal) || !text.EndsWith("```", StringComparison.Ordinal))
        {
            return false;
        }

        var firstLineEnd = text.IndexOf('\n');
        if (firstLineEnd < 0)
        {
            return false;
        }

        var language = text[3..firstLineEnd].Trim();
        if (language.Length != 0 && !string.Equals(language, "json", StringComparison.OrdinalIgnoreCase))
        {
            return false;
        }

        var closingStart = text.LastIndexOf("```", StringComparison.Ordinal);
        if (closingStart <= firstLineEnd || closingStart + 3 != text.Length)
        {
            return false;
        }

        var body = text[(firstLineEnd + 1)..closingStart];
        json = body.Trim();
        return json.Length > 0;
    }

    private static ObjectScan FindSingleObject(string raw)
    {
        string? candidate = null;
        for (var i = 0; i < raw.Length; i++)
        {
            if (raw[i] != '{')
            {
                continue;
            }

            var end = FindMatchingObjectEnd(raw, i);
            if (end < 0)
            {
                return new ObjectScan(null, "No se pudo delimitar un único objeto JSON completo.");
            }

            if (candidate is not null)
            {
                return new ObjectScan(null, "La respuesta contiene más de un objeto JSON; no se eligió uno de ellos.");
            }

            candidate = raw[i..(end + 1)];
            i = end;
        }

        return new ObjectScan(candidate, null);
    }

    private static int FindMatchingObjectEnd(string text, int start)
    {
        var depth = 0;
        var inString = false;
        var escaped = false;

        for (var i = start; i < text.Length; i++)
        {
            var ch = text[i];
            if (inString)
            {
                if (escaped)
                {
                    escaped = false;
                }
                else if (ch == '\\')
                {
                    escaped = true;
                }
                else if (ch == '"')
                {
                    inString = false;
                }

                continue;
            }

            if (ch == '"')
            {
                inString = true;
            }
            else if (ch == '{')
            {
                depth++;
            }
            else if (ch == '}' && --depth == 0)
            {
                return i;
            }
        }

        return -1;
    }

    private enum ParseStatus
    {
        Valid,
        Inconsistent,
        InvalidJson,
        InvalidSchema
    }

    private sealed record ParseAttempt(ParseStatus Status, ParsedFeedback? Value, string? Error)
    {
        public static ParseAttempt Valid(ParsedFeedback value) => new(ParseStatus.Valid, value, null);
        public static ParseAttempt Inconsistent(ParsedFeedback value, string error) => new(ParseStatus.Inconsistent, value, error);
        public static ParseAttempt InvalidJson(string error) => new(ParseStatus.InvalidJson, null, error);
        public static ParseAttempt InvalidSchema(string error) => new(ParseStatus.InvalidSchema, null, error);
    }

    private sealed record ObjectScan(string? ObjectText, string? Error);
}
