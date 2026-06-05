---
language: csharp
tags: [csharp, unsafe, interop, pointers, pinvoke, span, marshal]
title: Unsafe Code & Interop
description: Unsafe blocks with pointers, fixed-size buffers, P/Invoke declarations, Marshal class for unmanaged memory, and Span<T> for safe stack/memory access.
source: pattern
---

```csharp
using System.Runtime.InteropServices;

// ── P/Invoke — calling Win32 API ───────────────────────────────────────
public static class NativeMethods
{
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    public static extern nint GetModuleHandle(string? lpModuleName);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern int MessageBox(nint hWnd, string text, string caption, uint type);
}

// ── Unsafe block with pointers ─────────────────────────────────────────
public static unsafe class FastBuffer
{
    public static void ZeroFill(Span<byte> buffer)
    {
        fixed (byte* ptr = buffer)
        {
            for (int i = 0; i < buffer.Length; i++)
                ptr[i] = 0;
        }
    }

    // Stackalloc + pointer arithmetic
    public static Span<int> GenerateSquares(int count)
    {
        int* arr = stackalloc int[count];
        for (int i = 0; i < count; i++)
            arr[i] = i * i;
        return new Span<int>(arr, count);
    }
}

// ── Marshal — converting unmanaged data ────────────────────────────────
public static class UnmanagedHelper
{
    public static nint AllocateAndCopy(byte[] data)
    {
        nint ptr = Marshal.AllocHGlobal(data.Length);
        Marshal.Copy(data, 0, ptr, data.Length);
        return ptr;
    }

    public static byte[] ReadAndFree(nint ptr, int length)
    {
        byte[] data = new byte[length];
        Marshal.Copy(ptr, data, 0, length);
        Marshal.FreeHGlobal(ptr);
        return data;
    }

    // Struct to byte[] and back
    public static byte[] StructToBytes<T>(T value) where T : struct
    {
        byte[] buffer = new byte[Marshal.SizeOf<T>()];
        Marshal.StructureToPtr(value, Marshal.UnsafeAddrOfPinnedArrayElement(buffer, 0), false);
        return buffer;
    }
}

// ── Span<T> — safe, stack-allocated memory region ──────────────────────
Span<int> stackSpan = stackalloc int[256];
Span<byte> managedSpan = new byte[1024];
ReadOnlySpan<char> slice = "Hello, World!".AsSpan()[7..12]; // "World"

```
