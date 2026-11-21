using Android.App;
using Android.App.Job;
using Android.Content;
using Android.Util;

namespace WritingApp.Android;

public interface IModelDownloadHost
{
    WritingApp.Shared.BackgroundModelDownloads Downloads { get; }
}

[BroadcastReceiver(Exported = true, Permission = "android.permission.SEND_DOWNLOAD_COMPLETED_INTENTS")]
[IntentFilter([DownloadManager.ActionDownloadComplete])]
public sealed class ModelDownloadCompletedReceiver : BroadcastReceiver
{
    public override void OnReceive(Context? context, Intent? intent)
    {
        if (context is not null && intent?.Action == DownloadManager.ActionDownloadComplete)
            ModelDownloadFinalizer.Schedule(context);
    }
}

[Service(Exported = true, Permission = "android.permission.BIND_JOB_SERVICE")]
public sealed class ModelDownloadFinalizer : JobService
{
    private const int JobId = 1;
    private const string Tag = "WritingDownload";
    private readonly global::Android.OS.Handler _mainThread = new(global::Android.OS.Looper.MainLooper!);
    private CancellationTokenSource? _running;

    internal static void Schedule(Context context)
    {
        if (context.GetSystemService(Context.JobSchedulerService) is not JobScheduler scheduler)
            return;
        using var service = Java.Lang.Class.FromType(typeof(ModelDownloadFinalizer));
        using var component = new ComponentName(context, service);
        using var builder = new JobInfo.Builder(JobId, component);
        builder.SetRequiresStorageNotLow(true);
        using var job = builder.Build();
        using var intent = new Intent();
        using var request = new JobWorkItem(intent);
        if (job is null || scheduler.Enqueue(job, request) != JobScheduler.ResultSuccess)
            Log.Warn(Tag, "Could not schedule model download finalization.");
    }

    public override bool OnStartJob(JobParameters? parameters)
    {
        if (parameters is null || Application is not IModelDownloadHost app)
            return false;
        var cancellation = new CancellationTokenSource();
        _running = cancellation;
        _ = Task.Run(() => CompleteDownloadsAsync(app, parameters, cancellation));
        return true;
    }

    private async Task CompleteDownloadsAsync(IModelDownloadHost app, JobParameters parameters,
        CancellationTokenSource cancellation)
    {
        bool retry = false;
        try
        {
            while (!cancellation.IsCancellationRequested && parameters.DequeueWork() is { } item)
            {
                using (item)
                {
                    await app.Downloads.FinalizeCompletedAsync(
                        (model, ex) => Log.Warn(Tag, $"Rejected download of {model.Id}. {ex.Message}"),
                        cancellation.Token).ConfigureAwait(false);
                    cancellation.Token.ThrowIfCancellationRequested();
                    parameters.CompleteWork(item);
                }
            }
        }
        catch (OperationCanceledException) when (cancellation.IsCancellationRequested) { }
        catch (Exception ex)
        {
            Log.Warn(Tag, $"Could not finish publishing completed models. {ex.Message}");
            retry = true;
        }
        finally
        {
            _mainThread.Post(() =>
            {
                if (_running == cancellation)
                {
                    _running = null;
                    // DequeueWork() returning null finishes the job atomically
                    // with the queue check. Only report failure here.
                    if (retry) JobFinished(parameters, true);
                }
                cancellation.Dispose();
            });
        }
    }

    public override bool OnStopJob(JobParameters? parameters)
    {
        var running = _running;
        _running = null;
        running?.Cancel();
        return true;
    }
}
