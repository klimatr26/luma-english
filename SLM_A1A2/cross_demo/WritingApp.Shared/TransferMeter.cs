using System.Diagnostics;

namespace WritingApp.Shared;

public sealed class TransferMeter(long startingBytes = 0)
{
    private readonly Stopwatch _clock = Stopwatch.StartNew();
    private long _previousBytes = startingBytes;
    private double _previousSeconds;
    private double _rate;
    public bool ShouldReport => _clock.Elapsed.TotalSeconds - _previousSeconds >= 0.5;

    public DownloadProgress Report(string message, long bytes, long total)
    {
        var seconds = _clock.Elapsed.TotalSeconds;
        var elapsed = seconds - _previousSeconds;
        if(elapsed >= 0.25)
        {
            var sample = Math.Max(0, bytes - _previousBytes) / elapsed;
            _rate = _rate == 0 ? sample : 0.65 * _rate + 0.35 * sample;
            _previousBytes = bytes;
            _previousSeconds = seconds;
        }
        return new(message, bytes, total, _rate,
            _rate > 0 && bytes < total ? (total - bytes) / _rate : null);
    }
}
