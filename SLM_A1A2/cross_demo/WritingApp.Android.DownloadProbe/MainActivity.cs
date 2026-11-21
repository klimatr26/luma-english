using Android.App;
using Android.Content;
using Android.OS;
using Android.Widget;
using System.Text.Json;
using WritingApp.Shared;

namespace WritingApp.Android.DownloadProbe;

[Activity(Label="Writing download validation",MainLauncher=true,Exported=true)]
public sealed class MainActivity : Activity
{
    private const string Tag="WritingDownloadProbe";
    protected override void OnCreate(Bundle? savedInstanceState)
    {
        base.OnCreate(savedInstanceState);
        var mode=Intent?.GetStringExtra("mode")??"status";
        SetContentView(new TextView(this){Text="Validación técnica de descarga del sistema.\nPaquete separado; no usa la caché de Writing Lab."});
        _=Task.Run(async()=>{
            try {await RunAsync(mode);}
            catch(Exception e){global::Android.Util.Log.Error(Tag,e.ToString());}
            finally{RunOnUiThread(Finish);}
        });
    }
    private async Task RunAsync(string mode)
    {
        var context=ApplicationContext??this;
        using var store=new ModelStore(Path.Combine(FilesDir!.AbsolutePath,"probe-models"));
        var transport=new AndroidDownloadTransport(context);
        var downloader=new BackgroundModelDownloads(store,transport);
        // Bounded to one existing public 730895168-byte GGUF. Never inference.
        var model=PortableCatalog.All.Single(m=>m.Id=="09-lfm25-12b-q4-k-m");
        if(mode=="start")
        {
            using var monitor=new CancellationTokenSource(TimeSpan.FromSeconds(2));
            try{await downloader.EnsureAsync(model,new ProgressSink(),monitor.Token);global::Android.Util.Log.Info(Tag,"COMPLETED_AND_VERIFIED");}
            catch(System.OperationCanceledException){global::Android.Util.Log.Info(Tag,"MONITOR_DETACHED_SYSTEM_JOB_RETAINED");}
        }
        var ticketFile=Path.Combine(store.CacheDirectory,".download-jobs",model.Sha256+".json");
        if(File.Exists(ticketFile))
        {
            var ticket=JsonSerializer.Deserialize(await File.ReadAllTextAsync(ticketFile),AppJsonContext.Default.DownloadTicket)!;
            var status=await transport.QueryAsync(ticket.Id);
            global::Android.Util.Log.Info(Tag,$"STATE mode={mode} id={ticket.Id} status={status.State} bytes={status.ReceivedBytes} total={status.TotalBytes}");
            if(mode=="cleanup") {await downloader.CancelAsync(model);global::Android.Util.Log.Info(Tag,"OWN_SYSTEM_JOB_REMOVED");}
        }
        else global::Android.Util.Log.Info(Tag,"NO_TICKET cache_verified="+(await store.FindVerifiedAsync(model,CancellationToken.None) is not null));
    }
    private sealed class ProgressSink:IProgress<DownloadProgress>
    {public void Report(DownloadProgress p)=>global::Android.Util.Log.Info(Tag,$"PROGRESS bytes={p.ReceivedBytes} total={p.TotalBytes} message={p.Message}");}
}
