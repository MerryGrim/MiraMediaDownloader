"""Inspect only a newly launched Mira QA process and its own child windows."""
import argparse
import ctypes as C
from ctypes import wintypes as W
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from PIL import Image

PROJECT = Path(__file__).resolve().parents[1]
from windows_capture import api, windows

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--executable', type=Path, help='Public packaged MiraMediaDownloader.exe; omit for source mode')
parser.add_argument('--native-only', action='store_true', help='Expect only the native loader when using a generated Core fixture')
parser.add_argument('--output', required=True, type=Path)
args = parser.parse_args()
out = args.output.resolve()
assert out.is_relative_to(PROJECT.parent) and not out.exists(), 'Use a new directory inside the project or its parent'
out.mkdir(parents=True)
user = api()
user.SendMessageW.argtypes = [W.HWND, W.UINT, W.WPARAM, W.LPARAM]
user.SendMessageW.restype = C.c_ssize_t
user.GetClassLongPtrW.argtypes = [W.HWND, C.c_int]
user.GetClassLongPtrW.restype = C.c_size_t
user.CopyIcon.argtypes = [W.HICON]
user.CopyIcon.restype = W.HICON
user.DestroyIcon.argtypes = [W.HICON]
user.LoadIconW.argtypes = [W.HINSTANCE, W.LPCWSTR]
user.LoadIconW.restype = W.HICON
user.LoadImageW.argtypes = [W.HINSTANCE, W.LPCWSTR, W.UINT, C.c_int, C.c_int, W.UINT]
user.LoadImageW.restype = W.HANDLE
user.DrawIconEx.argtypes = [W.HDC, C.c_int, C.c_int, W.HICON, C.c_int, C.c_int, W.UINT, W.HBRUSH, W.UINT]
user.DrawIconEx.restype = W.BOOL
user.GetDC.argtypes = [W.HWND]
user.GetDC.restype = W.HDC
user.ReleaseDC.argtypes = [W.HWND, W.HDC]
gdi = C.WinDLL('gdi32', use_last_error=True)
gdi.CreateCompatibleDC.argtypes = [W.HDC]
gdi.CreateCompatibleDC.restype = W.HDC
gdi.SelectObject.argtypes = [W.HDC, W.HANDLE]
gdi.SelectObject.restype = W.HANDLE
gdi.DeleteObject.argtypes = [W.HANDLE]
gdi.DeleteDC.argtypes = [W.HDC]

class Header(C.Structure):
    _fields_ = [('size', W.DWORD), ('width', W.LONG), ('height', W.LONG),
                ('planes', W.WORD), ('bits', W.WORD), ('compression', W.DWORD),
                ('image', W.DWORD), ('x', W.LONG), ('y', W.LONG),
                ('used', W.DWORD), ('important', W.DWORD)]
gdi.CreateDIBSection.argtypes = [W.HDC, C.c_void_p, W.UINT, C.POINTER(C.c_void_p), W.HANDLE, W.DWORD]
gdi.CreateDIBSection.restype = W.HBITMAP

def render(icon, size):
    dc = user.GetDC(None)
    memory = gdi.CreateCompatibleDC(dc)
    header = Header(C.sizeof(Header), size, -size, 1, 32, 0, 0, 0, 0, 0, 0)
    bits = C.c_void_p()
    bitmap = gdi.CreateDIBSection(dc, C.byref(header), 0, C.byref(bits), None, 0)
    assert bitmap and bits.value
    previous = gdi.SelectObject(memory, bitmap)
    try:
        C.memset(bits, 255, size * size * 4)
        assert user.DrawIconEx(memory, 0, 0, icon, size, size, 0, None, 3)
        gdi.GdiFlush()
        return Image.frombytes('RGB', (size, size), C.string_at(bits, size * size * 4), 'raw', 'BGRX')
    finally:
        gdi.SelectObject(memory, previous)
        gdi.DeleteObject(bitmap)
        gdi.DeleteDC(memory)
        user.ReleaseDC(None, dc)

generic = user.LoadIconW(None, C.cast(C.c_void_p(32512), W.LPCWSTR))
assert generic
public_exe = args.executable.resolve() if args.executable else None
core_exe = public_exe.parent / 'runtime' / 'MiraMediaDownloaderCore.exe' if public_exe else None
report = {'passed': False, 'windows': {}, 'actual_user_data_accessed': False,
    'fixture_mode': True, 'fixture_cli': '--startup-probe',
    'application_mode': 'native_fixture' if args.native_only else 'frozen' if public_exe else 'source',
    'public_exe_sha256': hashlib.sha256(public_exe.read_bytes()).hexdigest() if public_exe else None,
    'core_exe_sha256': hashlib.sha256(core_exe.read_bytes()).hexdigest() if core_exe and core_exe.is_file() else None,
    'exit_code': None}
environment = dict(os.environ, QT_QPA_PLATFORM='windows', MIRA_STARTUP_LANGUAGE='en', MIRA_STARTUP_THEME='light',
    APPDATA=str(out / 'empty-roaming'), LOCALAPPDATA=str(out / 'empty-local'),
    MIRA_SESSION_DIR=str(out / 'empty-vault'), MIRA_STARTUP_TRACE=str(out / 'native.json'))
command = ([str(args.executable.resolve())] if args.executable else [sys.executable, '-m', 'mira_media'])
command += ['--startup-probe', str(out / 'gui')]
with (out / 'stdout.log').open('wb') as stdout, (out / 'stderr.log').open('wb') as stderr:
    process = subprocess.Popen(command, cwd=PROJECT, env=environment, stdout=stdout, stderr=stderr)
    try:
        deadline = time.monotonic() + 30
        while process.poll() is None and time.monotonic() < deadline:
            for hwnd, cls, title in windows(process.pid):
                kind = 'native' if cls == 'MiraNativeStartup' else 'qt' if cls.startswith('Qt') and 'Mira' in title else None
                if kind is None or kind in report['windows']:
                    continue
                # WM_GETICON is the actual window taskbar icon, not QIcon metadata.
                raw = {'small': int(user.SendMessageW(hwnd, 0x007F, 0, 0)),
                       'large': int(user.SendMessageW(hwnd, 0x007F, 1, 0)),
                       'class_small': int(user.GetClassLongPtrW(hwnd, -34)),
                       'class_large': int(user.GetClassLongPtrW(hwnd, -14))}
                facts = {'class': cls, 'wm_geticon_small': bool(raw['small']),
                         'wm_geticon_large': bool(raw['large']),
                         'class_small': bool(raw['class_small']), 'class_large': bool(raw['class_large']),
                         'bitmaps': {}}
                assert raw['small'] and raw['large'], (kind, raw)
                for label, size in [('small', 16), ('large', 32)]:
                    copied = user.CopyIcon(raw[label])
                    assert copied
                    try:
                        picture = render(copied, size)
                    finally:
                        user.DestroyIcon(copied)
                    fallback = render(generic, size)
                    expected_handle = user.LoadImageW(None, str(PROJECT / 'assets/mira.ico'), 1, size, size, 0x0010)
                    assert expected_handle
                    try:
                        expected = render(expected_handle, size)
                    finally:
                        user.DestroyIcon(expected_handle)
                    picture.save(out / f'{kind}-{label}-{size}.png')
                    expected.save(out / f'brand-reference-{size}.png')
                    fallback.save(out / f'windows-generic-{size}.png')
                    actual_data = picture.tobytes()
                    generic_difference = sum(abs(a-b) for a,b in zip(actual_data, fallback.tobytes())) / len(actual_data)
                    brand_difference = sum(abs(a-b) for a,b in zip(actual_data, expected.tobytes())) / len(actual_data)
                    assert generic_difference > 10, (kind, label, generic_difference)
                    assert brand_difference < generic_difference, (kind, label, brand_difference, generic_difference)
                    facts['bitmaps'][label] = {'pixels': size, 'sha256': hashlib.sha256(actual_data).hexdigest(),
                        'difference_from_windows_generic': round(generic_difference, 3),
                        'difference_from_brand_reference': round(brand_difference, 3)}
                report['windows'][kind] = facts
            time.sleep(.01)
        report['exit_code'] = process.wait(timeout=2)
        assert report['exit_code'] == 0
        expected = {'native'} if args.native_only else {'native', 'qt'} if args.executable else {'qt'}
        assert expected <= report['windows'].keys(), report
        report['passed'] = True
    finally:
        if process.poll() is None:
            process.kill()  # Exact QA-owned process; launcher job owns its children.
            process.wait(timeout=5)
(out / 'identity-icons.json').write_text(json.dumps(report, indent=2))
print(json.dumps({'passed': report['passed'], 'output': str(out), 'windows': report['windows']}, indent=2))
