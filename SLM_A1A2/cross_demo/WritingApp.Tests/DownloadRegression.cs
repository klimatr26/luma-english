using System.Net;
using System.Net.Http.Headers;
using System.Security.Cryptography;
using WritingApp.Shared;

static class DownloadRegression
{
    public static (string,Func<Task>)[] Cases => [
        ("HTTP transfer and stream reads leave the calling synchronization context",Worker),
        ("interrupted HTTP download resumes exact bytes with a validated 206 range",Resume),
        ("server ignoring Range restarts safely without appending a full response",IgnoredRange),
        ("mismatched Content-Range is rejected without destroying the resumable prefix",WrongRange),
        ("UI monitor cancellation leaves the system job and reattaches without a duplicate",BackgroundReattach),
        ("explicit cancel removes only the recorded system job",BackgroundCancel),
        ("system completion still requires full pinned SHA verification",BackgroundBadHash),
        ("a failed system job is not retried in the monitoring loop",BackgroundFailure),
        ("verified private cache cleans a system ticket left by death after publication",PublishedCacheCleanup),
        ("completed system job is made durable without a local ticket or a new download",RecoverCompletedWithoutTicket),
        ("interrupted publication keeps the completed system job available",RecoverAfterPublicationCancellation),
        ("extended application catalogue recovers only exact matching pending tickets",ExtendedCatalogTicket)
    ];
    static byte[] Data => "GGUFfixture download payload"u8.ToArray();
    static async Task ExtendedCatalogTicket()
    {
        using var temp = new Folder(); using var store = new ModelStore(temp.Path);
        var jobs = System.IO.Path.Combine(temp.Path, ".download-jobs"); Directory.CreateDirectory(jobs);
        var path = System.IO.Path.Combine(jobs, "fixture.json");
        var ticket = new DownloadTicket(91, Model.Id, Model.Sha256, Model.SizeBytes);
        await File.WriteAllTextAsync(path, System.Text.Json.JsonSerializer.Serialize(ticket, AppJsonContext.Default.DownloadTicket));
        Check(new BackgroundModelDownloads(store, new Transport()).PendingModelId is null, "Legacy catalogue accepted an unknown model.");
        var extended = new BackgroundModelDownloads(store, new Transport(), [Model]);
        Check(extended.PendingModelId == Model.Id, "Extended catalogue lost a valid pending transfer.");
        await File.WriteAllTextAsync(path, System.Text.Json.JsonSerializer.Serialize(ticket with { Sha256 = "different" }, AppJsonContext.Default.DownloadTicket));
        Check(extended.PendingModelId is null, "Mismatched source hash was accepted.");
    }
    static ModelEntry Model => PortableCatalog.All[0] with {Id="download-fixture",RelativePath="fixture/test.gguf",
        SizeBytes=Data.Length,Sha256=Convert.ToHexStringLower(SHA256.HashData(Data)),DownloadUrl="https://huggingface.co/fixture/pinned.gguf"};
    static void Check(bool yes,string message){if(!yes) throw new Exception(message);}
    static string Prefix(string root)=>ModelStore.SafePath(root,Model.RelativePath)+".download-"+Model.Sha256+".partial";
    static async Task PrefixAsync(string root)
    {Directory.CreateDirectory(Path.GetDirectoryName(Prefix(root))!);await File.WriteAllBytesAsync(Prefix(root),Data[..5]);}
    static HttpResponseMessage Response(byte[] data,HttpStatusCode code=HttpStatusCode.OK)
        => new(code){Content=new ByteArrayContent(data)};
    static HttpResponseMessage RangeResponse(long from)
    {
        var result=Response(Data[(int)from..],HttpStatusCode.PartialContent);
        result.Content.Headers.ContentRange=new ContentRangeHeaderValue(from,Data.Length-1,Data.Length);
        return result;
    }
    static async Task Worker()
    {
        using var temp=new Folder(); bool worker=false;
        using var store=new ModelStore(temp.Path,handler:new Http(request=>{
            worker=SynchronizationContext.Current is null;
            return new(HttpStatusCode.OK){Content=new StreamContent(new WorkerStream(Data))};
        }));
        var previous=SynchronizationContext.Current; Task<string> transfer;
        try{SynchronizationContext.SetSynchronizationContext(new SynchronizationContext()); transfer=store.EnsureAsync(Model,null,CancellationToken.None);}
        finally{SynchronizationContext.SetSynchronizationContext(previous);}
        await transfer; Check(worker,"HTTP entered on the UI synchronization context");
    }
    static async Task Resume()
    {
        using var temp=new Folder(); int requests=0;
        using var store=new ModelStore(temp.Path,handler:new Http(request=>{
            requests++;
            if(requests==1){var shortResponse=Response(Data[..5]);shortResponse.Content.Headers.ContentLength=Data.Length;return shortResponse;}
            Check(request.Headers.Range?.Ranges.Single().From==5,"wrong resume offset");return RangeResponse(5);
        }));
        try{await store.EnsureAsync(Model,null,CancellationToken.None);throw new Exception("accepted truncated body");}catch(EndOfStreamException){}
        Check(File.Exists(Prefix(temp.Path)) && requests==1,"lost resumable prefix or silently retried");
        var path=await store.EnsureAsync(Model,null,CancellationToken.None);
        Check((await File.ReadAllBytesAsync(path)).SequenceEqual(Data) && requests==2,"resumed content differs");
    }
    static async Task IgnoredRange()
    {
        using var temp=new Folder(); await PrefixAsync(temp.Path);
        using var store=new ModelStore(temp.Path,handler:new Http(request=>Response(Data)));
        var path=await store.EnsureAsync(Model,null,CancellationToken.None);
        Check((await File.ReadAllBytesAsync(path)).SequenceEqual(Data),"appended full response to prefix");
    }
    static async Task WrongRange()
    {
        using var temp=new Folder(); await PrefixAsync(temp.Path);
        using var store=new ModelStore(temp.Path,handler:new Http(request=>RangeResponse(4)));
        try{await store.EnsureAsync(Model,null,CancellationToken.None);throw new Exception("accepted wrong range");}catch(InvalidDataException){}
        Check((await File.ReadAllBytesAsync(Prefix(temp.Path))).SequenceEqual(Data[..5]),"prefix damaged");
    }
    static async Task BackgroundReattach()
    {
        using var temp=new Folder(); using var store=new ModelStore(temp.Path);
        var system=new Transport(); var downloads=new BackgroundModelDownloads(store,system);
        using var monitor=new CancellationTokenSource();
        var progress=new ProgressInline<DownloadProgress>(_=>monitor.Cancel());
        try{await downloads.EnsureAsync(Model,progress,monitor.Token);throw new Exception("monitor ignored cancel");}catch(OperationCanceledException){}
        Check(system.Starts==1 && system.Removes==0,"monitor cancelled the real system job");
        system.Complete=true;
        // New coordinator simulates app recreation; only the small ticket survives.
        var recreated=new BackgroundModelDownloads(store,system);
        var path=await recreated.EnsureAsync(Model,null,CancellationToken.None);
        Check(system.Starts==1 && system.Removes==1 && await store.VerifyAsync(Model,path,CancellationToken.None),"did not reattach/verify");
    }
    static async Task BackgroundCancel()
    {
        using var temp=new Folder(); using var store=new ModelStore(temp.Path); var system=new Transport();
        var downloads=new BackgroundModelDownloads(store,system);using var monitor=new CancellationTokenSource();
        try{await downloads.EnsureAsync(Model,new ProgressInline<DownloadProgress>(_=>monitor.Cancel()),monitor.Token);}catch(OperationCanceledException){}
        await downloads.CancelAsync(Model);
        Check(system.Removes==1 && system.LastRemoved==91,"removed a different system job");
    }
    static async Task BackgroundBadHash()
    {
        using var temp=new Folder();using var store=new ModelStore(temp.Path);var system=new Transport{Complete=true,Bad=true};
        var downloads=new BackgroundModelDownloads(store,system);
        try{await downloads.EnsureAsync(Model,null,CancellationToken.None);throw new Exception("accepted corrupt system download");}catch(InvalidDataException){}
        Check(store.FindExisting(Model) is null && system.Removes==1,"published corrupt system bytes");
    }
    static async Task BackgroundFailure()
    {
        using var temp=new Folder();using var store=new ModelStore(temp.Path);var system=new Transport{Failed=true};
        try{await new BackgroundModelDownloads(store,system).EnsureAsync(Model,null,CancellationToken.None);throw new Exception("accepted failed system job");}catch(IOException){}
        Check(system.Starts==1 && system.Removes==0,"loop retried a failed system job");
    }
    static async Task PublishedCacheCleanup()
    {
        using var temp=new Folder();using var store=new ModelStore(temp.Path);var system=new Transport();
        var downloader=new BackgroundModelDownloads(store,system);using var monitor=new CancellationTokenSource();
        try{await downloader.EnsureAsync(Model,new ProgressInline<DownloadProgress>(_=>monitor.Cancel()),monitor.Token);}catch(OperationCanceledException){}
        var published=ModelStore.SafePath(temp.Path,Model.RelativePath);
        Directory.CreateDirectory(Path.GetDirectoryName(published)!);await File.WriteAllBytesAsync(published,Data);
        Check(await new BackgroundModelDownloads(store,system).EnsureAsync(Model,null,CancellationToken.None)==published,"verified cache not reused");
        Check(system.Starts==1 && system.Removes==1,"left redundant system job or downloaded again");
    }
    static async Task RecoverCompletedWithoutTicket()
    {
        using var temp = new Folder();
        var system = new Transport { Complete = true };
        using (var store = new ModelStore(temp.Path))
        {
            var downloads = new BackgroundModelDownloads(store, system);
            await downloads.FinalizeCompletedAsync((_, ex) => throw ex, CancellationToken.None);
        }
        using var reopened = new ModelStore(temp.Path);
        Check(await reopened.FindVerifiedAsync(Model, CancellationToken.None) is not null,
            "completed download was missing after reopening");
        Check(system.Starts == 0 && system.Removes == 1 && system.LastRemoved == 91,
            "recovery initiated a download or failed to retire the completed job");
    }
    static async Task RecoverAfterPublicationCancellation()
    {
        using var temp = new Folder();
        using var store = new ModelStore(temp.Path);
        var system = new Transport { Complete = true };
        var downloads = new BackgroundModelDownloads(store, system);
        using var cancellation = new CancellationTokenSource();
        var progress = new ProgressInline<DownloadProgress>(_ => cancellation.Cancel());
        try
        {
            await downloads.RecoverCompletedAsync(Model, progress, cancellation.Token);
            throw new Exception("publication was not cancelled");
        }
        catch (OperationCanceledException) { }
        Check(system.Removes == 0 && store.FindExisting(Model) is null, "completed job was lost on cancellation");
        Check(await downloads.RecoverCompletedAsync(Model, null, CancellationToken.None) is not null
            && system.Starts == 0 && system.Removes == 1, "load-time recovery did not reuse the completed job");
    }
    sealed class Http(Func<HttpRequestMessage,HttpResponseMessage> send):HttpMessageHandler
    {protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage r,CancellationToken ct)=>Task.FromResult(send(r));}
    sealed class WorkerStream(byte[] bytes):MemoryStream(bytes)
    {
        public override ValueTask<int> ReadAsync(Memory<byte> buffer,CancellationToken ct=default)
        {Check(SynchronizationContext.Current is null,"response stream was read on UI context");return base.ReadAsync(buffer,ct);}
    }
    sealed class Transport:ISystemDownloadTransport
    {
        public int Starts,Removes;public long LastRemoved;public bool Complete,Bad,Failed;
        public Task<long> StartOrFindAsync(ModelEntry m){Starts++;return Task.FromResult(91L);}
        public Task<IReadOnlyList<SystemDownloadJob>> FindCompletedAsync(CancellationToken ct) =>
            Task.FromResult<IReadOnlyList<SystemDownloadJob>>(Complete && Removes == 0 ? [new(91, Model)] : []);
        public Task<SystemDownloadSnapshot> QueryAsync(long id)=>Task.FromResult(new SystemDownloadSnapshot(Removes>0?SystemDownloadState.Missing:Failed?SystemDownloadState.Failed:Complete?SystemDownloadState.Complete:SystemDownloadState.Running,
            Complete?Data.Length:2,Data.Length,"fixture"));
        public Task<Stream> OpenReadAsync(long id)=>Task.FromResult<Stream>(new MemoryStream(Bad?new byte[Data.Length]:Data));
        public Task RemoveAsync(long id){Removes++;LastRemoved=id;return Task.CompletedTask;}
    }
    sealed class ProgressInline<T>(Action<T> report):IProgress<T>{public void Report(T value)=>report(value);}
    sealed class Folder:IDisposable
    {
        public string Path {get;}=System.IO.Path.Combine(System.IO.Path.GetTempPath(),"writing-download-fixture-"+Guid.NewGuid().ToString("N"));
        public Folder()=>Directory.CreateDirectory(Path);
        public void Dispose(){var resolved=System.IO.Path.GetFullPath(Path);if(!resolved.StartsWith(System.IO.Path.GetTempPath(),StringComparison.OrdinalIgnoreCase))throw new Exception("Unsafe cleanup");Directory.Delete(resolved,true);}
    }
}
