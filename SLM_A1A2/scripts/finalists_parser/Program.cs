using System.Text;
using System.Text.Json;
using System.Security.Cryptography;
using WritingDemo.Core;

if (args.Length != 2) throw new ArgumentException("Pass input/output JSONL paths.");
using var output = new StreamWriter(new FileStream(args[1], FileMode.CreateNew), new UTF8Encoding(false));
var assemblySha = Convert.ToHexStringLower(SHA256.HashData(File.ReadAllBytes(typeof(FeedbackParser).Assembly.Location)));
foreach (var line in File.ReadLines(args[0]))
{
    using var document = JsonDocument.Parse(line);
    var row = document.RootElement;
    var parsed = FeedbackParser.Parse(row.GetProperty("raw_response").GetString()!,
                                     row.GetProperty("student_text").GetString()!);
    using var stream = new MemoryStream();
    using (var writer = new Utf8JsonWriter(stream))
    {
        writer.WriteStartObject();
        writer.WriteString("config_id", row.GetProperty("config_id").GetString());
        writer.WriteString("case_id", row.GetProperty("case_id").GetString());
        writer.WriteString("status", parsed.Status);
        writer.WriteString("error", parsed.Error);
        writer.WriteString("manifest_sha256", row.GetProperty("manifest_sha256").GetString());
        writer.WriteString("response_sha256", Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(row.GetProperty("raw_response").GetString()!))));
        writer.WriteString("student_text_sha256", Convert.ToHexStringLower(SHA256.HashData(Encoding.UTF8.GetBytes(row.GetProperty("student_text").GetString()!))));
        writer.WriteString("parser_assembly_sha256", assemblySha);
        writer.WriteEndObject();
    }
    output.WriteLine(Encoding.UTF8.GetString(stream.ToArray()));
}
