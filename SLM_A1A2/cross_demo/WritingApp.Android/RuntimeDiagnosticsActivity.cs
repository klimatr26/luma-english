#if WRITING_DIAGNOSTICS
using Android.App;
using Android.OS;
using Android.Widget;
using System.Text.Json.Nodes;
using WritingApp.Shared;

namespace WritingApp.Android;

[Activity(Name = "org.kevinlima.writinglab.RuntimeDiagnosticsActivity",
    Exported = true, Label = "Writing runtime verification")]
public sealed class RuntimeDiagnosticsActivity : Activity
{
    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        Window?.AddFlags(global::Android.Views.WindowManagerFlags.KeepScreenOn);
        if (Build.VERSION.SdkInt >= BuildVersionCodes.OMr1)
        {
            SetShowWhenLocked(true);
            SetTurnScreenOn(true);
        }
        SetContentView(new TextView(this) { Text = "Comprobación de motor local en curso." });
        var modelId = Intent?.GetStringExtra("model") ?? "09-lfm25-12b-q4-k-m";
        var mode = Intent?.GetStringExtra("mode") ?? "measure";
        _ = Task.Run(async () =>
        {
            await Task.Delay(750);
            var result = new JsonObject { ["model"] = modelId, ["mode"] = mode };
            var folder = Path.Combine(GetExternalFilesDir(null)!.AbsolutePath, "runtime-tests");
            Directory.CreateDirectory(folder);
            var name = $"{modelId}-{mode}-{DateTime.UtcNow:yyyyMMddTHHmmss}";
            try
            {
                var model = PortableCatalog.All.Single(m => m.Id == modelId);
                var root = FilesDir!.AbsolutePath;
                using var store = new ModelStore(Path.Combine(root, "models"));
                var path = await store.FindVerifiedAsync(model, CancellationToken.None);
                // Host-side staged diagnostic models are copied into the private verified store.
                if (path is null)
                {
                    var staging = Path.Combine(GetExternalFilesDir(null)!.AbsolutePath, "diagnostic-models", Path.GetFileName(model.RelativePath));
                    await using var input = File.OpenRead(staging);
                    path = await store.ImportAsync(model, input, null, CancellationToken.None);
                }
                var native = ApplicationInfo!.NativeLibraryDir!;
                var power = (PowerManager)GetSystemService(PowerService)!;
                if (mode is "timeout" or "cancel")
                {
                    await using var worker = new AndroidWorkerEngine(native, "", Path.Combine(root, "driver-cache"), false);
                    await worker.LoadAsync(model, path, BackendPreference.Cpu, 2048, CancellationToken.None);
                    worker.GenerationTimeout = mode == "timeout" ? TimeSpan.FromMilliseconds(1) : TimeSpan.FromSeconds(120);
                    using var cancellation = new CancellationTokenSource();
                    if (mode == "cancel") cancellation.CancelAfter(100);
                    try
                    {
                        await worker.GenerateAsync(BackendCalibrationPolicy.Exercise,
                            BackendCalibrationPolicy.Exercise.IncorrectExample, 42, cancellation.Token);
                        throw new InvalidOperationException("Expected interruption was not observed.");
                    }
                    catch (TimeoutException) when (mode == "timeout") { result["interruption_observed"] = true; }
                    catch (System.OperationCanceledException) when (mode == "cancel") { result["interruption_observed"] = true; }
                    worker.GenerationTimeout = TimeSpan.FromSeconds(120);
                    await worker.LoadAsync(model, path, BackendPreference.Cpu, 2048, CancellationToken.None);
                    var recovered = await worker.GenerateAsync(BackendCalibrationPolicy.Exercise,
                        BackendCalibrationPolicy.Exercise.IncorrectExample, 42, CancellationToken.None);
                    result["reloaded_after_interruption"] = true;
                    result["finish"] = recovered.FinishReason;
                    result["success"] = true;
                    return;
                }
                await using var engine = new AndroidMeasuredEngine(native, root, power);
                var requested = mode == "cpu" ? BackendPreference.Cpu : BackendPreference.AutoVulkanCpu;
                var state = await engine.LoadAsync(model, path, requested, 2048, CancellationToken.None);
                result["backend"] = state.Backend;
                result["device"] = state.Device;
                result["reason"] = state.FallbackReason;
                result["calibration"] = engine.LastCalibration is { } cal
                    ? JsonNode.Parse(System.Text.Json.JsonSerializer.Serialize(cal, AppJsonContext.Default.AdaptiveProfile)) : null;
                var exercise = BackendCalibrationPolicy.Exercise;
                var response = await engine.GenerateAsync(exercise, exercise.IncorrectExample, 42, CancellationToken.None);
                result["raw"] = response.Content;
                result["seconds"] = response.Seconds;
                result["finish"] = response.FinishReason;
                result["parser"] = WritingDemo.Core.FeedbackParser.Parse(response.Content, exercise.IncorrectExample).Status;
                result["success"] = true;
                var profiles = Path.Combine(root, "adaptive-profiles");
                if (Directory.Exists(profiles))
                    foreach (var file in Directory.EnumerateFiles(profiles, "*.json"))
                    {
                        var destination = Path.Combine(folder, Path.GetFileName(file));
                        File.Delete(destination);
                        await File.WriteAllTextAsync(destination, await File.ReadAllTextAsync(file));
                    }
            }
            catch (Exception e)
            {
                result["success"] = false;
                result["exception"] = e.ToString();
            }
            finally
            {
                await File.WriteAllTextAsync(Path.Combine(folder, name + ".json"), result.ToJsonString());
                global::Android.Util.Log.Info("WritingDiagnostics", $"{name} success={result["success"]}");
                RunOnUiThread(Finish);
            }
        });
    }
}
#endif
