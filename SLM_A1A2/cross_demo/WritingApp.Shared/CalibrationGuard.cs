namespace WritingApp.Shared;

public sealed class CalibrationInterruptedException() : OperationCanceledException(
    "La comparación se interrumpió al salir de la aplicación o apagar la pantalla. Mantén la app visible y vuelve a preparar la IA; no se guardaron tiempos de segundo plano.");

/// <summary>Only calibration is guarded; downloads and ordinary inference keep their own lifecycle.</summary>
internal sealed class CalibrationGuard : IAsyncDisposable
{
    private readonly CancellationTokenSource _deadline, _watchStop = new();
    private readonly Func<bool>? _allowed;
    private readonly Task _watch;
    private int _interrupted;
    public CancellationToken Token => _deadline.Token;
    public bool IsAllowed { get { try { return _allowed?.Invoke() ?? true; } catch { return false; } } }
    public CalibrationGuard(CancellationToken parent, TimeSpan budget, Func<bool>? allowed)
    {
        _allowed = allowed;
        _deadline = CancellationTokenSource.CreateLinkedTokenSource(parent);
        _deadline.CancelAfter(budget);
        _watch = allowed is null ? Task.CompletedTask : WatchAsync();
    }
    public void ThrowIfInterrupted()
    {
        if (Volatile.Read(ref _interrupted) != 0) throw new CalibrationInterruptedException();
    }
    public void Check()
    {
        if (!IsAllowed) Interrupt();
        ThrowIfInterrupted(); Token.ThrowIfCancellationRequested();
    }
    private void Interrupt() { Interlocked.Exchange(ref _interrupted, 1); _deadline.Cancel(); }
    private async Task WatchAsync()
    {
        try
        {
            while (!_watchStop.IsCancellationRequested)
            {
                if (!IsAllowed) { Interrupt(); return; }
                await Task.Delay(500, _watchStop.Token).ConfigureAwait(false);
            }
        }
        catch (OperationCanceledException) when (_watchStop.IsCancellationRequested) { }
    }
    public async ValueTask DisposeAsync()
    {
        _watchStop.Cancel(); await _watch.ConfigureAwait(false);
        _watchStop.Dispose(); _deadline.Dispose();
    }
}
