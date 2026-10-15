"""Capture only windows owned by a QA child process, without desktop pixels."""
from __future__ import annotations
import ctypes as C
from ctypes import wintypes as W
import os


def api():
    if os.name != 'nt':
        raise RuntimeError('Windows QA only')
    user = C.WinDLL('user32', use_last_error=True)
    # PrintWindow paints physical pixels; virtualized GetWindowRect dimensions
    # otherwise clip the bitmap on a scaled Windows desktop.
    user.SetThreadDpiAwarenessContext.argtypes = [W.HANDLE]
    user.SetThreadDpiAwarenessContext.restype = W.HANDLE
    user.SetThreadDpiAwarenessContext(W.HANDLE(-4))
    user.GetWindowThreadProcessId.argtypes = [W.HWND, C.POINTER(W.DWORD)]
    user.GetWindowThreadProcessId.restype = W.DWORD
    user.IsWindowVisible.argtypes = [W.HWND]
    user.IsWindowVisible.restype = W.BOOL
    user.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
    user.GetClassNameW.argtypes = [W.HWND, W.LPWSTR, C.c_int]
    user.GetWindowRect.argtypes = [W.HWND, C.POINTER(W.RECT)]
    user.GetWindowRect.restype = W.BOOL
    user.PostMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
    user.PostMessageW.restype = W.BOOL
    return user


def descendants(parent):
    kernel = C.WinDLL('kernel32', use_last_error=True)
    class Entry(C.Structure):
        _fields_ = [('size',W.DWORD),('usage',W.DWORD),('pid',W.DWORD),('heap',C.c_size_t),
                    ('module',W.DWORD),('threads',W.DWORD),('parent',W.DWORD),
                    ('priority',W.LONG),('flags',W.DWORD),('exe',W.WCHAR*260)]
    kernel.CreateToolhelp32Snapshot.argtypes = [W.DWORD,W.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = W.HANDLE
    kernel.Process32FirstW.argtypes = [W.HANDLE,C.POINTER(Entry)]
    kernel.Process32NextW.argtypes = [W.HANDLE,C.POINTER(Entry)]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.CreateToolhelp32Snapshot(2,0)
    if handle == C.c_void_p(-1).value:
        raise C.WinError(C.get_last_error())
    pairs=[]
    try:
        item=Entry(); item.size=C.sizeof(Entry)
        valid=kernel.Process32FirstW(handle,C.byref(item))
        while valid:
            pairs.append((int(item.pid),int(item.parent)))
            valid=kernel.Process32NextW(handle,C.byref(item))
    finally:
        kernel.CloseHandle(handle)
    owned={int(parent)}
    while True:
        found=owned|{pid for pid,owner in pairs if owner in owned}
        if found==owned:
            return owned
        owned=found


def window_text(user, hwnd):
    text=C.create_unicode_buffer(16384)
    user.GetWindowTextW(hwnd,text,len(text))
    return text.value


def windows(parent, *, class_name=None):
    user=api(); owned=descendants(parent); values=[]
    callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def visit(hwnd,_):
        pid=W.DWORD(); user.GetWindowThreadProcessId(hwnd,C.byref(pid))
        if int(pid.value) not in owned or not user.IsWindowVisible(hwnd):
            return True
        name=C.create_unicode_buffer(256); user.GetClassNameW(hwnd,name,len(name))
        if class_name is None or name.value==class_name:
            values.append((int(hwnd),name.value,window_text(user,hwnd)))
        return True
    cb=callback(visit)
    user.EnumWindows.argtypes=[callback,W.LPARAM]
    user.EnumWindows(cb,0)
    return values


def children(hwnd):
    user=api(); values=[]
    callback=C.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
    def visit(child,_):
        if user.IsWindowVisible(child):
            values.append((int(child),window_text(user,child)))
        return True
    cb=callback(visit)
    user.EnumChildWindows.argtypes=[W.HWND,callback,W.LPARAM]
    user.EnumChildWindows(hwnd,cb,0)
    return values


def capture(hwnd, target):
    from PIL import Image
    user=api(); gdi=C.WinDLL('gdi32',use_last_error=True)
    user.GetDC.argtypes=[W.HWND]; user.GetDC.restype=W.HDC
    user.ReleaseDC.argtypes=[W.HWND,W.HDC]
    user.PrintWindow.argtypes=[W.HWND,W.HDC,W.UINT]; user.PrintWindow.restype=W.BOOL
    for name,args,returns in (
        ('CreateCompatibleDC',[W.HDC],W.HDC),
        ('CreateCompatibleBitmap',[W.HDC,C.c_int,C.c_int],W.HBITMAP),
        ('SelectObject',[W.HDC,W.HANDLE],W.HANDLE),
        ('DeleteObject',[W.HANDLE],W.BOOL),('DeleteDC',[W.HDC],W.BOOL)):
        call=getattr(gdi,name); call.argtypes=args; call.restype=returns
    rect=W.RECT()
    if not user.GetWindowRect(hwnd,C.byref(rect)):
        raise C.WinError(C.get_last_error())
    width,height=rect.right-rect.left,rect.bottom-rect.top
    if not (20<=width<=8000 and 20<=height<=8000):
        raise RuntimeError('Unexpected QA window size')
    dc=user.GetDC(None); memory=gdi.CreateCompatibleDC(dc)
    bitmap=gdi.CreateCompatibleBitmap(dc,width,height); previous=gdi.SelectObject(memory,bitmap)
    try:
        if not user.PrintWindow(hwnd,memory,2):
            raise RuntimeError('Window-only capture failed')
        gdi.SelectObject(memory,previous)
        class Header(C.Structure):
            _fields_=[('size',W.DWORD),('width',W.LONG),('height',W.LONG),('planes',W.WORD),
                      ('bits',W.WORD),('compression',W.DWORD),('image',W.DWORD),
                      ('x',W.LONG),('y',W.LONG),('used',W.DWORD),('important',W.DWORD)]
        header=Header(C.sizeof(Header),width,-height,1,32,0,0,0,0,0,0)
        raw=C.create_string_buffer(width*height*4)
        gdi.GetDIBits.argtypes=[W.HDC,W.HBITMAP,W.UINT,W.UINT,C.c_void_p,C.c_void_p,W.UINT]
        if gdi.GetDIBits(memory,bitmap,0,height,raw,C.byref(header),0)!=height:
            raise RuntimeError('Bitmap read failed')
        image=Image.frombytes('RGB',(width,height),raw.raw,'raw','BGRX')
        image.save(target)
        return (width,height)
    finally:
        gdi.SelectObject(memory,previous); gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory); user.ReleaseDC(None,dc)
