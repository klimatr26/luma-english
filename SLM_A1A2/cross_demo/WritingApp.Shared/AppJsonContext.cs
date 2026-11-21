using System.Text.Json.Serialization;
namespace WritingApp.Shared;

[JsonSourceGenerationOptions(WriteIndented=true,UseStringEnumConverter=true)]
[JsonSerializable(typeof(ModelEntry[]))]
[JsonSerializable(typeof(ReviewSession))]
[JsonSerializable(typeof(Dictionary<string,string>))]
[JsonSerializable(typeof(DownloadTicket))]
[JsonSerializable(typeof(BackendCalibration))]
[JsonSerializable(typeof(RuntimeInventory))]
[JsonSerializable(typeof(AdaptiveProfile))]
[JsonSerializable(typeof(CalibrationTrace))]
public partial class AppJsonContext : JsonSerializerContext { }
