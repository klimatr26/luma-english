namespace WritingApp.UI;

public static class SessionExportWriter
{
    public static async Task WriteAsync(Stream output, ReadOnlyMemory<byte> content, CancellationToken cancellationToken = default)
    {
        ArgumentNullException.ThrowIfNull(output);
        cancellationToken.ThrowIfCancellationRequested();

        if (output.CanSeek)
        {
            output.SetLength(0);
            output.Position = 0;
        }

        await output.WriteAsync(content, cancellationToken);
        await output.FlushAsync(cancellationToken);
    }
}
