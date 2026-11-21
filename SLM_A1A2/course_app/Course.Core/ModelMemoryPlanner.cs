using WritingApp.Shared;

namespace Course.Core;

public sealed record ModelMemoryPlan(long WorkingSetBytes, long RequiredAvailableBytes, long SystemReserveBytes,
    long StorageRequiredBytes, bool UsesMappedWeights, bool Fits, string Reason);

/// <summary>Capacity and immediate headroom are separate. These are estimates, never a successful-load guarantee.</summary>
public static class ModelMemoryPlanner
{
    private const long MiB = 1024 * 1024, GiB = 1024 * MiB;
    public static ModelMemoryPlan Plan(ModelEntry model, DeviceProfile device, int context, bool alreadyAvailable, bool lowMemory = false)
    {
        var android = device.Platform == "Android";
        var working = checked(ModelRecommender.Estimate(model, context) + Math.Max(256 * MiB, model.SizeBytes / 10));
        var system = android ? Math.Clamp(device.TotalMemoryBytes / 4, 1280 * MiB, 2 * GiB)
            : Math.Clamp(device.TotalMemoryBytes / 6, GiB, 4 * GiB);
        // The retained CPU runtime uses mmap: file-backed weight pages can be reclaimed.
        // Keep the full working-set estimate against total capacity, and require enough
        // currently available memory for non-file buffers plus the extra margin above.
        var immediate = android ? Math.Max(768 * MiB, working - model.SizeBytes) : checked((long)Math.Ceiling(working / .85));
        var storage = alreadyAvailable ? 0 : checked(model.SizeBytes * (android ? 2 : 1) + 256 * MiB);
        var known = device.TotalMemoryBytes > 0 && device.AvailableMemoryBytes > 0;
        var capacity = working <= Math.Max(0, device.TotalMemoryBytes - system);
        var free = device.AvailableMemoryBytes >= immediate;
        var disk = alreadyAvailable || device.FreeStorageBytes >= storage;
        var fits = known && !lowMemory && capacity && free && disk;
        var mapped = android && working > device.AvailableMemoryBytes;
        var reason = !known ? "No se pudo confirmar la memoria disponible."
            : lowMemory ? "Android indica presión de memoria; libera recursos antes de preparar la IA."
            : !capacity ? "La memoria total no deja la reserva prevista para el sistema."
            : !free ? "La memoria libre no alcanza el margen previsto para preparar el modelo."
            : !disk ? "Falta espacio para guardar y verificar la descarga."
            : mapped ? "La capacidad total permite preparar el modelo, con margen libre ajustado. Si la carga falla se propondrá una alternativa menor."
            : "Hay margen estimado de memoria y almacenamiento para la preparación.";
        return new(working, immediate, system, storage, mapped, fits, reason);
    }
}
