using Android.App;
using Android.Content;
using Android.Database;
using WritingApp.Shared;

namespace WritingApp.Android;

/// <summary>Android's system service owns sockets, resumption, wakefulness and notifications.</summary>
public sealed class AndroidDownloadTransport(Context context, IReadOnlyList<ModelEntry>? catalog = null,
    string applicationTitle = "Writing Lab") : ISystemDownloadTransport
{
    private readonly DownloadManager _manager = context.GetSystemService(Context.DownloadService) as DownloadManager
        ?? throw new InvalidOperationException("Android no ofrece un gestor de descargas.");
    private static string Description(ModelEntry model) => "Writing Lab GGUF SHA-256: " + model.Sha256;

    public Task<long> StartOrFindAsync(ModelEntry model) => Task.Run(() =>
    {
        // Recover a system job even if the app died just after enqueue and before journaling its ID.
        using(var query=new DownloadManager.Query())
        using(var cursor=_manager.InvokeQuery(query))
        {
            if(cursor is not null)
                while(cursor.MoveToNext())
                {
                    if(Text(cursor,DownloadManager.ColumnUri)!=model.DownloadUrl ||
                        Text(cursor,DownloadManager.ColumnDescription)!=Description(model)) continue;
                    var id=Number(cursor,DownloadManager.ColumnId);
                    if(Number(cursor,DownloadManager.ColumnStatus)!=16) return id;
                    // This is our own failed job, not an unrelated user download.
                    _manager.Remove(id);
                }
        }
        var uri=global::Android.Net.Uri.Parse(model.DownloadUrl!)
            ?? throw new InvalidOperationException("URL de descarga inválida.");
        using var request=new DownloadManager.Request(uri);
        request.SetTitle(applicationTitle + " · " + model.Name + " · " + model.Quantization);
        request.SetDescription(Description(model));
        request.SetNotificationVisibility(DownloadVisibility.VisibleNotifyCompleted);
        request.SetAllowedOverRoaming(false);
        request.AddRequestHeader("Accept-Encoding","identity");
        // App-scoped external storage: no broad storage permission or public Downloads file.
        request.SetDestinationInExternalFilesDir(context,global::Android.OS.Environment.DirectoryDownloads,
            "writing-model-"+model.Sha256+"-"+Guid.NewGuid().ToString("N")+".download");
        var job=_manager.Enqueue(request);
        global::Android.Util.Log.Info("WritingDownload",$"Enqueued pinned model {model.Id}; system job {job}");
        return job;
    });

    private static string Text(ICursor cursor,string column) => cursor.GetString(cursor.GetColumnIndexOrThrow(column)) ?? "";
    private static long Number(ICursor cursor,string column) => cursor.GetLong(cursor.GetColumnIndexOrThrow(column));

    public Task<IReadOnlyList<SystemDownloadJob>> FindCompletedAsync(CancellationToken ct) => Task.Run<IReadOnlyList<SystemDownloadJob>>(() =>
    {
        using var query = new DownloadManager.Query();
        query.SetFilterByStatus(DownloadStatus.Successful);
        using var cursor = _manager.InvokeQuery(query);
        var completed = new List<SystemDownloadJob>();
        if (cursor is null) return completed;
        while (cursor.MoveToNext())
        {
            ct.ThrowIfCancellationRequested();
            var url = Text(cursor, DownloadManager.ColumnUri);
            var description = Text(cursor, DownloadManager.ColumnDescription);
            var model = (catalog ?? PortableCatalog.All).FirstOrDefault(m => m.DownloadUrl == url && description == Description(m));
            if (model is not null)
                completed.Add(new(Number(cursor, DownloadManager.ColumnId), model));
        }
        return completed;
    }, ct);

    public Task<SystemDownloadSnapshot> QueryAsync(long id) => Task.Run(() =>
    {
        using var query=new DownloadManager.Query(); query.SetFilterById(id);
        using var cursor=_manager.InvokeQuery(query);
        if(cursor is null || !cursor.MoveToFirst())
            return new SystemDownloadSnapshot(SystemDownloadState.Missing,0,0,"El trabajo de descarga ya no existe en Android.");
        long bytes=Number(cursor,DownloadManager.ColumnBytesDownloadedSoFar);
        long total=Number(cursor,DownloadManager.ColumnTotalSizeBytes);
        int status=(int)Number(cursor,DownloadManager.ColumnStatus);
        int reason=(int)Number(cursor,DownloadManager.ColumnReason);
        var state=status switch {
            1=>SystemDownloadState.Pending,2=>SystemDownloadState.Running,4=>SystemDownloadState.Paused,
            8=>SystemDownloadState.Complete,16=>SystemDownloadState.Failed,_=>SystemDownloadState.Missing
        };
        var message=state switch {
            SystemDownloadState.Pending=>"En cola en el gestor de Android…",
            SystemDownloadState.Running=>"Descargando en el sistema de Android…",
            SystemDownloadState.Paused=>reason switch {
                1=>"Android espera para reintentar la conexión…",2=>"Android espera una conexión de red…",
                3=>"Android espera una red Wi-Fi para este archivo…",_=>"Descarga pausada por Android; se conserva su progreso."
            },
            SystemDownloadState.Complete=>"Descarga del sistema completa.",
            SystemDownloadState.Failed=>reason is 401 or 403 ? "El proveedor exige acceso; importa el GGUF exacto tras gestionarlo con el proveedor."
                : $"Android informó un fallo de descarga (código {reason}).",
            _=>"Estado de descarga desconocido."
        };
        return new SystemDownloadSnapshot(state,bytes,total,message);
    });

    public Task<Stream> OpenReadAsync(long id) => Task.Run(() =>
    {
        var uri=_manager.GetUriForDownloadedFile(id) ?? throw new IOException("Android no ofrece el archivo completado.");
        return context.ContentResolver?.OpenInputStream(uri) ?? throw new IOException("No se pudo abrir la descarga del sistema.");
    });
    public Task RemoveAsync(long id) => Task.Run(() => { _manager.Remove(id); });
}

[BroadcastReceiver(Enabled=true,Exported=true)]
[IntentFilter(new[]{DownloadManager.ActionNotificationClicked})]
public sealed class DownloadNotificationReceiver : BroadcastReceiver
{
    public override void OnReceive(Context? context,Intent? intent)
    {
        if(context is null || intent?.Action!=DownloadManager.ActionNotificationClicked) return;
        var launch=context.PackageManager?.GetLaunchIntentForPackage(context.PackageName!);
        if(launch is not null) {launch.AddFlags(ActivityFlags.NewTask|ActivityFlags.ClearTop);context.StartActivity(launch);}
    }
}
