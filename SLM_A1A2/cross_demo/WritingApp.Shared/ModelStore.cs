using System.Buffers;
using System.Net;
using System.Security.Cryptography;
namespace WritingApp.Shared;

public sealed class ModelStore : IDisposable, IModelDownloads
{
    private readonly string _root;
    private readonly string[] _external;
    private readonly HttpClient _http;
    private readonly SemaphoreSlim _gate = new(1,1);
    public ModelStore(string rootFolder,string[]? externalRoots=null,HttpMessageHandler? handler=null)
    {
        _root=Path.GetFullPath(rootFolder); Directory.CreateDirectory(_root);
        _external=(externalRoots??[]).Select(Path.GetFullPath).Distinct().ToArray();
        _http=handler is null ? new HttpClient(new SocketsHttpHandler {
            ConnectTimeout=TimeSpan.FromSeconds(30), MaxConnectionsPerServer=4,
            AutomaticDecompression=DecompressionMethods.None
        }) : new HttpClient(handler);
        _http.Timeout=Timeout.InfiniteTimeSpan;
        _http.DefaultRequestHeaders.UserAgent.ParseAdd("WritingLab-Demo/0.1");
    }
    public string CacheDirectory => _root;
    public event Action? ModelPublished;
    public bool ContinuesInBackground => false;
    public Task CancelAsync(ModelEntry model) => Task.CompletedTask; // The caller cancels its token.
    public static string SafePath(string root,string relative)
    {
        var parts=relative.Replace('\\','/').Split('/');
        if (string.IsNullOrWhiteSpace(relative) || Path.IsPathRooted(relative) || relative.Contains(':') || parts.Any(p=>p is "" or "." or "..")) throw new ArgumentException("Unsafe model path.");
        var fullRoot=Path.GetFullPath(root);
        var full=Path.GetFullPath(Path.Combine(fullRoot,Path.Combine(parts)));
        var tail=Path.GetRelativePath(fullRoot,full);
        if (Path.IsPathRooted(tail) || tail==".." || tail.StartsWith(".."+Path.DirectorySeparatorChar)) throw new ArgumentException("Model path escapes cache.");
        return full;
    }
    public string? FindExisting(ModelEntry model)
    {
        foreach(var root in new[]{_root}.Concat(_external))
        {
            var path=SafePath(root,model.RelativePath);
            if(File.Exists(path)) return path;
        }
        return null;
    }
    public async Task<string?> FindVerifiedAsync(ModelEntry model,CancellationToken ct)
    {
        foreach(var root in new[]{_root}.Concat(_external))
        {
            var path=SafePath(root,model.RelativePath);
            if(await VerifyAsync(model,path,ct)) return path;
        }
        return null;
    }
    public async Task<bool> VerifyAsync(ModelEntry model,string path,CancellationToken ct)
    {
        ct.ThrowIfCancellationRequested();
        if(!File.Exists(path)) return false;
        await using var file=new FileStream(path,FileMode.Open,FileAccess.Read,FileShare.Read,1024*1024,FileOptions.Asynchronous|FileOptions.SequentialScan);
        if(file.Length!=model.SizeBytes) return false;
        var magic=new byte[4];
        if(await file.ReadAsync(magic,ct)!=4 || !magic.AsSpan().SequenceEqual("GGUF"u8)) return false;
        file.Position=0;
        var actual=await SHA256.HashDataAsync(file,ct);
        return Convert.ToHexString(actual).Equals(model.Sha256,StringComparison.OrdinalIgnoreCase);
    }
    // Some Android response-stream methods perform synchronous work before yielding.
    // Enter the complete transfer on a worker, including synchronous continuations.
    public Task<string> EnsureAsync(ModelEntry model,IProgress<DownloadProgress>? progress,CancellationToken ct)
        => Task.Run(() => EnsureCoreAsync(model,progress,ct), CancellationToken.None);
    private async Task<string> EnsureCoreAsync(ModelEntry model,IProgress<DownloadProgress>? progress,CancellationToken ct)
    {
        await _gate.WaitAsync(ct);
        try
        {
            if(FindExisting(model) is {} existing)
            {
                progress?.Report(new("Verificando modelo existente (SHA-256)…",0,model.SizeBytes));
                existing=await FindVerifiedAsync(model,ct) ?? throw new InvalidDataException("Ningún archivo existente coincide con el modelo. Se conservan; importa el GGUF exacto para reparar la caché.");
                progress?.Report(new("Modelo existente verificado; no se descargó de nuevo.",model.SizeBytes,model.SizeBytes));
                return existing;
            }
            if(model.DownloadUrl is null) throw new InvalidOperationException("Este GGUF se convirtió localmente para el experimento. Importa ese archivo; no se sustituye por otro modelo.");
            var destination=SafePath(_root,model.RelativePath);
            Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
            var partial=destination+".download-"+model.Sha256.ToLowerInvariant()+".partial";
            long offset=File.Exists(partial)?new FileInfo(partial).Length:0;
            if(offset>model.SizeBytes) { File.Delete(partial); offset=0; }
            if(offset==model.SizeBytes)
            {
                if(await VerifyAsync(model,partial,ct).ConfigureAwait(false))
                {File.Move(partial,destination,overwrite:false);return destination;}
                File.Delete(partial);offset=0;
            }
            using var request=new HttpRequestMessage(HttpMethod.Get,model.DownloadUrl);
            request.Headers.AcceptEncoding.ParseAdd("identity");
            if(offset>0) request.Headers.Range=new System.Net.Http.Headers.RangeHeaderValue(offset,null);
            using var response=await _http.SendAsync(request,HttpCompletionOption.ResponseHeadersRead,ct).ConfigureAwait(false);
            if(response.StatusCode==HttpStatusCode.TooManyRequests) throw new HttpRequestException("HTTP 429: descarga detenida, sin reintentos automáticos.",null,response.StatusCode);
            if(response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden) throw new HttpRequestException("El proveedor exige acceso o aceptación de licencia. Gestiona el acceso con el proveedor e importa el GGUF verificado.",null,response.StatusCode);
            response.EnsureSuccessStatusCode();
            if(response.StatusCode==HttpStatusCode.PartialContent)
            {
                var range=response.Content.Headers.ContentRange;
                if(range?.From!=offset || range.To!=model.SizeBytes-1 || range.Length!=model.SizeBytes)
                    throw new InvalidDataException("El rango de descarga no coincide con el modelo fijado; se conserva el parcial.");
            }
            else if(response.StatusCode==HttpStatusCode.OK) offset=0; // A server may ignore Range; never append a full response.
            else throw new InvalidDataException("Respuesta HTTP inesperada para el archivo.");
            if(response.Content.Headers.ContentLength is long length && length!=model.SizeBytes-offset)
                throw new InvalidDataException("El tamaño anunciado no coincide con el catálogo fijado.");
            await using var input=await response.Content.ReadAsStreamAsync(ct).ConfigureAwait(false);
            var buffer=ArrayPool<byte>.Shared.Rent(1024*1024);
            var meter=new TransferMeter(offset);
            try
            {
                await using(var output=new FileStream(partial,offset==0?FileMode.Create:FileMode.Append,
                    FileAccess.Write,FileShare.None,1024*1024,FileOptions.Asynchronous|FileOptions.SequentialScan))
                {
                    long total=offset;
                    progress?.Report(meter.Report(offset>0?"Reanudando descarga…":"Descargando…",total,model.SizeBytes));
                    while(true)
                    {
                        int read=await input.ReadAsync(buffer.AsMemory(),ct).ConfigureAwait(false);
                        if(read==0) break;
                        if(total+read>model.SizeBytes) throw new InvalidDataException("El archivo supera el tamaño fijado.");
                        await output.WriteAsync(buffer.AsMemory(0,read),ct).ConfigureAwait(false);
                        total+=read;
                        if(meter.ShouldReport) progress?.Report(meter.Report("Descargando…",total,model.SizeBytes));
                    }
                    await output.FlushAsync(ct).ConfigureAwait(false);
                }
                if(new FileInfo(partial).Length!=model.SizeBytes)
                    throw new EndOfStreamException("La conexión terminó antes de completar el archivo. El parcial se conserva para reanudar.");
                progress?.Report(new("Verificando SHA-256 del archivo completo…",model.SizeBytes,model.SizeBytes));
                if(!await VerifyAsync(model,partial,ct).ConfigureAwait(false))
                {File.Delete(partial);throw new InvalidDataException("Descarga incompleta o SHA-256 incorrecto; no se publica el archivo.");}
                ct.ThrowIfCancellationRequested();
                File.Move(partial,destination,overwrite:false);
                progress?.Report(new("Modelo verificado y listo.",model.SizeBytes,model.SizeBytes));
                return destination;
            }
            finally { ArrayPool<byte>.Shared.Return(buffer); }
        }
        finally{_gate.Release();}
    }
    public Task<string> ImportAsync(ModelEntry model,Stream input,IProgress<DownloadProgress>? progress,CancellationToken ct)
        => Task.Run(() => ImportCoreAsync(model,input,progress,ct), CancellationToken.None);
    private async Task<string> ImportCoreAsync(ModelEntry model,Stream input,IProgress<DownloadProgress>? progress,CancellationToken ct)
    {
        await _gate.WaitAsync(ct);
        try
        {
            var destination=SafePath(_root,model.RelativePath);
            if(File.Exists(destination))
            {
                if(await VerifyAsync(model,destination,ct)) return destination;
            }
            return await WriteVerifiedAsync(model,input,progress,ct,archiveExisting:true);
        }
        finally{_gate.Release();}
    }
    private async Task<string> WriteVerifiedAsync(ModelEntry model,Stream input,IProgress<DownloadProgress>? progress,CancellationToken ct,bool archiveExisting=false)
    {
        var destination=SafePath(_root,model.RelativePath);
        Directory.CreateDirectory(Path.GetDirectoryName(destination)!);
        var partial=destination+".partial-"+Guid.NewGuid().ToString("N");
        var buffer=ArrayPool<byte>.Shared.Rent(1024*1024);
        try
        {
            long total=0; var lastReport=Environment.TickCount64;
            using var hash=IncrementalHash.CreateHash(HashAlgorithmName.SHA256);
            await using(var output=new FileStream(partial,FileMode.CreateNew,FileAccess.Write,FileShare.None,1024*1024,FileOptions.Asynchronous|FileOptions.SequentialScan))
            {
                while(true)
                {
                    int read=await input.ReadAsync(buffer.AsMemory(),ct); if(read==0) break;
                    if(total+read>model.SizeBytes) throw new InvalidDataException("El archivo supera el tamaño fijado.");
                    hash.AppendData(buffer,0,read); await output.WriteAsync(buffer.AsMemory(0,read),ct); total+=read;
                    if(Environment.TickCount64-lastReport>=200)
                    {progress?.Report(new("Copiando y verificando GGUF…",total,model.SizeBytes));lastReport=Environment.TickCount64;}
                }
                await output.FlushAsync(ct);
            }
            if(total!=model.SizeBytes || !Convert.ToHexString(hash.GetHashAndReset()).Equals(model.Sha256,StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("Tamaño o SHA-256 incorrecto: no se publica el archivo descargado.");
            await using(var verify=new FileStream(partial,FileMode.Open,FileAccess.Read,FileShare.Read))
            {
                var magic=new byte[4]; if(await verify.ReadAsync(magic,ct)!=4 || !magic.AsSpan().SequenceEqual("GGUF"u8)) throw new InvalidDataException("El archivo no es GGUF.");
            }
            ct.ThrowIfCancellationRequested();
            string? archived=null;
            if(archiveExisting && File.Exists(destination))
            {
                // Only an explicit, fully verified import can archive a file in our own cache.
                // External roots are never renamed or replaced.
                archived=destination+".unverified-"+Guid.NewGuid().ToString("N");
                File.Move(destination,archived,overwrite:false);
            }
            try{File.Move(partial,destination,overwrite:false);}
            catch
            {
                if(archived is not null && !File.Exists(destination)) File.Move(archived,destination,overwrite:false);
                throw;
            }
            ModelPublished?.Invoke();
            if(archived is not null) progress?.Report(new("Copia anterior preservada como no verificada: "+archived,total,total));
            progress?.Report(new("Modelo verificado y listo.",total,total)); return destination;
        }
        finally
        {
            ArrayPool<byte>.Shared.Return(buffer);
            if(File.Exists(partial)) File.Delete(partial);
        }
    }
    public void Dispose(){_http.Dispose();_gate.Dispose();}
}
