using System.Text.Json;

namespace WritingApp.Shared;

public enum SystemDownloadState { Missing, Pending, Running, Paused, Complete, Failed }
public sealed record SystemDownloadSnapshot(SystemDownloadState State, long ReceivedBytes, long TotalBytes, string Message);
public sealed record SystemDownloadJob(long Id, ModelEntry Model);
public sealed record DownloadTicket(long Id, string ModelId, string Sha256, long SizeBytes);

public interface ISystemDownloadTransport
{
    Task<long> StartOrFindAsync(ModelEntry model);
    Task<IReadOnlyList<SystemDownloadJob>> FindCompletedAsync(CancellationToken ct);
    Task<SystemDownloadSnapshot> QueryAsync(long id);
    Task<Stream> OpenReadAsync(long id);
    Task RemoveAsync(long id);
}

/// <summary>The system owns the transfer. Cancellation of UI monitoring does not cancel the job.</summary>
public sealed class BackgroundModelDownloads(ModelStore store, ISystemDownloadTransport transport,
    IReadOnlyList<ModelEntry>? catalog = null) : IModelDownloads
{
    private readonly SemaphoreSlim _startup = new(1,1);
    public bool ContinuesInBackground => true;
    public string? PendingModelId
    {
        get
        {
            var folder = Path.Combine(store.CacheDirectory, ".download-jobs");
            if (!Directory.Exists(folder)) return null;
            foreach (var path in Directory.GetFiles(folder, "*.json").OrderBy(File.GetCreationTimeUtc))
            {
                try
                {
                    var ticket = JsonSerializer.Deserialize(File.ReadAllText(path), AppJsonContext.Default.DownloadTicket);
                    if (ticket is not null && (catalog ?? PortableCatalog.All).Any(m => m.Id == ticket.ModelId
                        && m.Sha256 == ticket.Sha256 && m.SizeBytes == ticket.SizeBytes && store.FindExisting(m) is null))
                        return ticket.ModelId;
                }
                catch (IOException) { }
                catch (JsonException) { }
            }
            return null;
        }
    }

    public async Task<string?> RecoverCompletedAsync(ModelEntry model, IProgress<DownloadProgress>? progress, CancellationToken ct)
    {
        var jobs = await transport.FindCompletedAsync(ct).ConfigureAwait(false);
        var job = jobs.FirstOrDefault(j => j.Model.Id == model.Id && j.Model.Sha256 == model.Sha256);
        return job is null
            ? await store.FindVerifiedAsync(model, ct).ConfigureAwait(false)
            : await PublishAsync(job, progress, ct).ConfigureAwait(false);
    }

    public async Task FinalizeCompletedAsync(Action<ModelEntry, Exception> reportInvalidDownload, CancellationToken ct)
    {
        foreach (var job in await transport.FindCompletedAsync(ct).ConfigureAwait(false))
        {
            try
            {
                await PublishAsync(job, null, ct).ConfigureAwait(false);
            }
            catch (InvalidDataException ex)
            {
                // An invalid terminal payload is removed by PublishAsync.
                // It should not prevent other verified models from being saved.
                reportInvalidDownload(job.Model, ex);
            }
        }
    }
    private string TicketPath(ModelEntry model)
    {
        ModelStore.SafePath(store.CacheDirectory,model.RelativePath);
        if(model.Sha256.Length!=64 || !model.Sha256.All(Uri.IsHexDigit)) throw new ArgumentException("Invalid download pin.");
        return Path.Combine(store.CacheDirectory,".download-jobs",model.Sha256.ToLowerInvariant()+".json");
    }
    private async Task<DownloadTicket?> ReadTicketAsync(ModelEntry model)
    {
        var path=TicketPath(model);
        if(!File.Exists(path)) return null;
        await using var file=File.OpenRead(path);
        var ticket=await JsonSerializer.DeserializeAsync(file,AppJsonContext.Default.DownloadTicket).ConfigureAwait(false)
            ?? throw new InvalidDataException("Empty system download ticket.");
        if(ticket.ModelId!=model.Id || ticket.Sha256!=model.Sha256 || ticket.SizeBytes!=model.SizeBytes)
            throw new InvalidDataException("System download ticket does not match the pinned model.");
        return ticket;
    }
    private async Task WriteTicketAsync(ModelEntry model,DownloadTicket ticket)
    {
        var path=TicketPath(model); Directory.CreateDirectory(Path.GetDirectoryName(path)!);
        var temporary=path+".partial-"+Guid.NewGuid().ToString("N");
        try
        {
            await using(var file=new FileStream(temporary,FileMode.CreateNew,FileAccess.Write,FileShare.None))
                await JsonSerializer.SerializeAsync(file,ticket,AppJsonContext.Default.DownloadTicket).ConfigureAwait(false);
            File.Move(temporary,path,overwrite:true);
        }
        finally{if(File.Exists(temporary)) File.Delete(temporary);}
    }
    public Task<string> EnsureAsync(ModelEntry model,IProgress<DownloadProgress>? progress,CancellationToken ct)
        => Task.Run(()=>EnsureCoreAsync(model,progress,ct),CancellationToken.None);

    private async Task<string> EnsureCoreAsync(ModelEntry model,IProgress<DownloadProgress>? progress,CancellationToken ct)
    {
        if(store.FindExisting(model) is not null)
        {
            var path=await store.FindVerifiedAsync(model,ct).ConfigureAwait(false)
                ?? throw new InvalidDataException("La copia existente no coincide con el modelo fijado; se conserva. Importa el GGUF exacto.");
            // Recover a process death after publication but before system-job cleanup.
            // The private model is fully verified before removing this redundant job.
            await CancelAsync(model).ConfigureAwait(false);
            return path;
        }
        if(model.DownloadUrl is null) throw new InvalidOperationException("Importa el GGUF exacto de esta conversión local.");
        var recovered = await RecoverCompletedAsync(model, progress, ct).ConfigureAwait(false);
        if (recovered is not null) return recovered;
        DownloadTicket ticket;
        await _startup.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            // Recovery may have published the file while this request waited.
            if (store.FindExisting(model) is not null)
            {
                var verified = await store.FindVerifiedAsync(model, ct).ConfigureAwait(false)
                    ?? throw new InvalidDataException("La copia local no coincide con el catálogo.");
                if (await ReadTicketAsync(model).ConfigureAwait(false) is { } redundant)
                    await RemoveJobAsync(model, redundant.Id).ConfigureAwait(false);
                return verified;
            }
            var existing=await ReadTicketAsync(model).ConfigureAwait(false);
            if(existing is not null)
            {
                var current=await transport.QueryAsync(existing.Id).ConfigureAwait(false);
                if(current.State is SystemDownloadState.Failed or SystemDownloadState.Missing)
                {
                    // A new explicit Prepare request may restart a terminal job, once.
                    await transport.RemoveAsync(existing.Id).ConfigureAwait(false);
                    File.Delete(TicketPath(model)); existing=null;
                }
            }
            if(existing is null)
            {
                ct.ThrowIfCancellationRequested();
                // Persist the ID even if monitoring is cancelled during enqueue.
                var id=await transport.StartOrFindAsync(model).ConfigureAwait(false);
                existing=new(id,model.Id,model.Sha256,model.SizeBytes);
                await WriteTicketAsync(model,existing).ConfigureAwait(false);
            }
            ticket=existing;
        }
        finally{_startup.Release();}

        TransferMeter? meter=null;
        while(true)
        {
            ct.ThrowIfCancellationRequested();
            var snapshot=await transport.QueryAsync(ticket.Id).ConfigureAwait(false);
            if(snapshot.State != SystemDownloadState.Complete && snapshot.TotalBytes>0 && snapshot.TotalBytes!=model.SizeBytes)
                throw new InvalidDataException("El gestor del sistema anuncia un tamaño distinto al catálogo fijado.");
            meter??=new TransferMeter(snapshot.ReceivedBytes);
            progress?.Report(meter.Report(snapshot.Message,snapshot.ReceivedBytes,model.SizeBytes));
            switch(snapshot.State)
            {
                case SystemDownloadState.Failed:
                case SystemDownloadState.Missing:
                    // A background finalizer can publish and retire the system
                    // download between two queries by the UI.
                    if (await store.FindVerifiedAsync(model, ct).ConfigureAwait(false) is { } verified)
                        return verified;
                    throw new IOException(snapshot.Message+" Pulsa Descargar / reanudar para volver a intentarlo.");
                case SystemDownloadState.Complete:
                    return await PublishAsync(new(ticket.Id, model), progress, ct).ConfigureAwait(false)
                        ?? throw new IOException("La descarga ya no está disponible en Android.");
            }
            await Task.Delay(1000,ct).ConfigureAwait(false);
        }
    }

    private async Task<string?> PublishAsync(SystemDownloadJob job, IProgress<DownloadProgress>? progress, CancellationToken ct)
    {
        var model = job.Model;
        await _startup.WaitAsync(ct).ConfigureAwait(false);
        try
        {
            // Query again under the same gate as cancellation and other publishers.
            var snapshot = await transport.QueryAsync(job.Id).ConfigureAwait(false);
            if (snapshot.State != SystemDownloadState.Complete)
                return await store.FindVerifiedAsync(model, ct).ConfigureAwait(false);

            progress?.Report(new("Descarga completa. Verificando y guardando el GGUF…", model.SizeBytes, model.SizeBytes));
            string path;
            try
            {
                ct.ThrowIfCancellationRequested();
                if (snapshot.TotalBytes != model.SizeBytes || snapshot.ReceivedBytes != model.SizeBytes)
                    throw new InvalidDataException("El tamaño de la descarga no coincide con el catálogo.");
                await using var stream = await transport.OpenReadAsync(job.Id).ConfigureAwait(false);
                path = await store.ImportAsync(model, stream, progress, ct).ConfigureAwait(false);
            }
            catch (InvalidDataException)
            {
                await RemoveJobAsync(model, job.Id).ConfigureAwait(false);
                throw;
            }
            await RemoveJobAsync(model, job.Id).ConfigureAwait(false);
            return path;
        }
        finally { _startup.Release(); }
    }

    private async Task RemoveJobAsync(ModelEntry model, long id)
    {
        await transport.RemoveAsync(id).ConfigureAwait(false);
        try
        {
            if ((await ReadTicketAsync(model).ConfigureAwait(false))?.Id == id)
                File.Delete(TicketPath(model));
        }
        catch (JsonException) { } // Keep an unreadable ticket for diagnosis. The system job was already retired.
    }

    public async Task CancelAsync(ModelEntry model)
    {
        await _startup.WaitAsync().ConfigureAwait(false);
        try
        {
            var ticket=await ReadTicketAsync(model).ConfigureAwait(false);
            if(ticket is null) return;
            await RemoveJobAsync(model, ticket.Id).ConfigureAwait(false);
        }
        finally{_startup.Release();}
    }
}
