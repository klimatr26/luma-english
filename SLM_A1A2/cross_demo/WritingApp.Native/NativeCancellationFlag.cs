using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace WritingApp.Native;

internal sealed unsafe class NativeCancellationFlag : IDisposable
{
    private nint _memory;

    public NativeCancellationFlag()
    {
        _memory = Marshal.AllocHGlobal(sizeof(int));
        *(int*)_memory = 0;
    }

    public int* Pointer
    {
        get
        {
            ObjectDisposedException.ThrowIf(_memory == 0, this);
            return (int*)_memory;
        }
    }

    public void RequestCancellation()
    {
        if (_memory != 0)
            Interlocked.Exchange(ref Unsafe.AsRef<int>((void*)_memory), 1);
    }

    public void Dispose()
    {
        var memory = Interlocked.Exchange(ref _memory, 0);
        if (memory != 0)
            Marshal.FreeHGlobal(memory);
    }
}
