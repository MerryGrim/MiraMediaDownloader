"""Compositor corner proof over an owned solid QA window, never a desktop grab."""
from __future__ import annotations

import ctypes as C
from ctypes import wintypes as W
import os
import time
from PIL import Image

BACKGROUND = (17, 203, 149)


def api():
    """The small Win32 surface also available inside the frozen application."""
    if os.name != 'nt':
        raise RuntimeError('Windows compositor QA only')
    user = C.WinDLL('user32', use_last_error=True)
    user.SetThreadDpiAwarenessContext.argtypes = [W.HANDLE]
    user.SetThreadDpiAwarenessContext.restype = W.HANDLE
    user.SetThreadDpiAwarenessContext(W.HANDLE(-4))
    user.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user.GetWindowRect.restype = W.BOOL
    user.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user.GetClientRect.restype = W.BOOL
    user.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
    user.ClientToScreen.restype = W.BOOL
    return user


def client_geometry(hwnd):
    user = api()
    user.GetClientRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user.ClientToScreen.argtypes = [W.HWND, C.POINTER(W.POINT)]
    outer, client, point = W.RECT(), W.RECT(), W.POINT()
    assert user.GetWindowRect(hwnd, C.byref(outer))
    assert user.GetClientRect(hwnd, C.byref(client))
    assert user.ClientToScreen(hwnd, C.byref(point))
    return {'window': [outer.left, outer.top, outer.right, outer.bottom],
            'client': [point.x, point.y, point.x + client.right, point.y + client.bottom]}


def composed_corner_proof(hwnd, target, *, rounded):
    """Temporarily cover the target's background with our own solid popup.

    Capture only that HWND rectangle. DWM clipping, unlike QWidget.grab or
    PrintWindow, reveals our solid background at rounded outer corners.
    """
    user, gdi = api(), C.WinDLL('gdi32')
    user.CreateWindowExW.argtypes = [W.DWORD, W.LPCWSTR, W.LPCWSTR, W.DWORD,
                                   C.c_int, C.c_int, C.c_int, C.c_int,
                                   W.HWND, W.HMENU, W.HINSTANCE, C.c_void_p]
    user.CreateWindowExW.restype = W.HWND
    user.SetWindowPos.argtypes = [W.HWND, W.HWND, C.c_int, C.c_int, C.c_int, C.c_int, W.UINT]
    user.GetWindowLongW.argtypes = [W.HWND, C.c_int]
    user.GetWindowLongW.restype = W.LONG
    user.GetWindow.argtypes = [W.HWND, W.UINT]; user.GetWindow.restype = W.HWND
    user.DestroyWindow.argtypes = [W.HWND]
    user.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.GetDC.argtypes = [W.HWND]; user.GetDC.restype = W.HDC
    user.ReleaseDC.argtypes = [W.HWND, W.HDC]
    gdi.CreateCompatibleDC.argtypes = [W.HDC]; gdi.CreateCompatibleDC.restype = W.HDC
    gdi.CreateCompatibleBitmap.argtypes = [W.HDC, C.c_int, C.c_int]; gdi.CreateCompatibleBitmap.restype = W.HBITMAP
    gdi.SelectObject.argtypes = [W.HDC, W.HANDLE]; gdi.SelectObject.restype = W.HANDLE
    gdi.DeleteObject.argtypes = [W.HANDLE]; gdi.DeleteDC.argtypes = [W.HDC]
    gdi.BitBlt.argtypes = [W.HDC, C.c_int, C.c_int, C.c_int, C.c_int, W.HDC, C.c_int, C.c_int, W.DWORD]
    gdi.BitBlt.restype = W.BOOL
    gdi.SetBkColor.argtypes = [W.HDC, W.DWORD]
    gdi.ExtTextOutW.argtypes = [W.HDC, C.c_int, C.c_int, W.UINT, C.POINTER(W.RECT), W.LPCWSTR, W.UINT, C.c_void_p]
    geometry = client_geometry(hwnd)
    left, top, right, bottom = geometry['window']
    width, height = right-left, bottom-top
    assert width > 24 and height > 24
    was_topmost = bool(user.GetWindowLongW(hwnd, -20) & 8)
    backdrop = user.CreateWindowExW(0x80, 'STATIC', 'Mira owned corner QA backdrop', 0x80000000,
                                   left-32, top-32, width+64, height+64, user.GetWindow(hwnd, 4), None, None, None)
    assert backdrop
    screen = memory = bitmap = previous = None
    try:
        user.SetWindowPos(backdrop, W.HWND(-1), left-32, top-32, width+64, height+64, 0x0050)
        user.SetWindowPos(hwnd, W.HWND(-1), 0, 0, 0, 0, 0x0013)
        user.SetWindowPos(backdrop, hwnd, left-32, top-32, width+64, height+64, 0x0050)
        # Fill a visible STATIC popup without a Qt event loop or reading data.
        dc = user.GetDC(backdrop)
        try:
            gdi.SetBkColor(dc, BACKGROUND[0] | BACKGROUND[1] << 8 | BACKGROUND[2] << 16)
            rect = W.RECT(0, 0, width+64, height+64)
            gdi.ExtTextOutW(dc, 0, 0, 2, C.byref(rect), '', 0, None)  # ETO_OPAQUE
        finally:
            user.ReleaseDC(backdrop, dc)
        C.WinDLL('dwmapi').DwmFlush()
        time.sleep(.12)
        screen = user.GetDC(None)
        memory = gdi.CreateCompatibleDC(screen)
        bitmap = gdi.CreateCompatibleBitmap(screen, width, height)
        previous = gdi.SelectObject(memory, bitmap)
        assert gdi.BitBlt(memory, 0, 0, width, height, screen, left, top, 0x00CC0020)
        gdi.SelectObject(memory, previous); previous = None
        class Header(C.Structure):
            _fields_ = [('size', W.DWORD), ('width', W.LONG), ('height', W.LONG),
                        ('planes', W.WORD), ('bits', W.WORD), ('compression', W.DWORD),
                        ('image', W.DWORD), ('x', W.LONG), ('y', W.LONG),
                        ('used', W.DWORD), ('important', W.DWORD)]
        header = Header(C.sizeof(Header), width, -height, 1, 32, 0, 0, 0, 0, 0, 0)
        raw = C.create_string_buffer(width*height*4)
        gdi.GetDIBits.argtypes = [W.HDC, W.HBITMAP, W.UINT, W.UINT, C.c_void_p, C.c_void_p, W.UINT]
        assert gdi.GetDIBits(memory, bitmap, 0, height, raw, C.byref(header), 0) == height
        image = Image.frombytes('RGB', (width, height), raw.raw, 'raw', 'BGRX')
        image.save(target)
        points = [(0, 0), (width-1, 0), (0, height-1), (width-1, height-1)]
        pixels = [image.getpixel(p) for p in points]
        # The native shadow darkens our background. Its chromatic ratios remain
        # identifiable; an opaque light/dark app corner does not have that hue.
        background = [g >= 40 and abs(r/g - BACKGROUND[0]/BACKGROUND[1]) < .025 and
                      abs(b/g - BACKGROUND[2]/BACKGROUND[1]) < .035 for r,g,b in pixels]
        center = image.getpixel((width//2, height//2))
        r,g,b = center
        body_visible = not (g >= 40 and abs(r/g - BACKGROUND[0]/BACKGROUND[1]) < .025 and
                            abs(b/g - BACKGROUND[2]/BACKGROUND[1]) < .035)
        return {'passed': body_visible and (all(background) if rounded else not any(background)),
                'body_visible': body_visible, 'center_pixel': center,
                'rounded_expected': rounded, 'corner_pixels': pixels,
                'owned_background': list(BACKGROUND), 'background_corners': background,
                'geometry': geometry, 'screenshot': str(target)}
    finally:
        if previous and memory: gdi.SelectObject(memory, previous)
        if bitmap: gdi.DeleteObject(bitmap)
        if memory: gdi.DeleteDC(memory)
        if screen: user.ReleaseDC(None, screen)
        user.DestroyWindow(backdrop)
        if not was_topmost:
            user.SetWindowPos(hwnd, W.HWND(-2), 0, 0, 0, 0, 0x0013)
