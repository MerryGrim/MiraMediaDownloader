from __future__ import annotations

import argparse
import io
import json
import os
from pathlib import Path
import sys
import threading


def _restore_stream(name: str, number: int, mode: str):
    """PyInstaller's windowed bootloader leaves Python streams unset.

    QProcess supplies inherited standard handles even to a GUI subsystem EXE.
    Duplicate them so closing a Python wrapper cannot close Qt's original.
    """
    if getattr(sys,name) is not None:
        getattr(sys,name).reconfigure(encoding='utf-8',errors='replace')
        return
    if os.name != 'nt':
        return
    import ctypes
    import msvcrt
    kernel = ctypes.WinDLL('kernel32',use_last_error=True)
    kernel.GetStdHandle.argtypes = [ctypes.c_uint32]
    kernel.GetStdHandle.restype = ctypes.c_void_p
    kernel.GetCurrentProcess.restype = ctypes.c_void_p
    kernel.DuplicateHandle.argtypes = [ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p),ctypes.c_uint32,ctypes.c_int,ctypes.c_uint32]
    kernel.DuplicateHandle.restype = ctypes.c_int
    handle = kernel.GetStdHandle(number & 0xffffffff)
    if not handle or handle == ctypes.c_void_p(-1).value:
        return
    duplicate = ctypes.c_void_p()
    process = kernel.GetCurrentProcess()
    if not kernel.DuplicateHandle(process,handle,process,ctypes.byref(duplicate),0,False,2):
        return
    flags = os.O_BINARY | (os.O_RDONLY if mode == 'r' else os.O_WRONLY)
    fd = msvcrt.open_osfhandle(duplicate.value,flags)
    stream = io.TextIOWrapper(os.fdopen(fd,mode+'b',buffering=0),encoding='utf-8',errors='replace',write_through=True)
    setattr(sys,name,stream)


def worker(path: str) -> int:
    _restore_stream('stdin',-10,'r')
    _restore_stream('stdout',-11,'w')
    _restore_stream('stderr',-12,'w')
    emit_lock = threading.Lock()

    def emit(event):
        if sys.stdout is None:
            return
        try:
            with emit_lock:
                sys.stdout.write(json.dumps(event,ensure_ascii=False) + '\n')
                sys.stdout.flush()
        except (OSError,ValueError):
            control.command('stop')

    from .control import Control
    from .models import JobOptions
    control = Control(emit)
    try:
        request = Path(path).resolve()
        if request.stat().st_size > 128*1024:
            raise ValueError('Некорректный размер служебного запроса.')
        data = json.loads(request.read_text(encoding='utf-8-sig'))
        if not isinstance(data,dict):
            raise ValueError('Некорректный запрос задания.')
        # Only consume/delete requests in our own tasks directory, never an
        # arbitrary JSON file passed by a caller.
        destination = Path(str(data.get('destination',''))).resolve()
        if request.parent == destination / '.mira' / 'tasks':
            request.unlink(missing_ok=True)
        options = JobOptions.from_dict(data)
        def listen():
            if sys.stdin is None:
                return
            try:
                buffer = b''
                while True:
                    chunk = os.read(sys.stdin.fileno(),4096)
                    if not chunk:
                        break
                    buffer += chunk
                    if len(buffer) > 32768:
                        buffer = b''
                    while b'\n' in buffer:
                        line,buffer = buffer.split(b'\n',1)
                        try:
                            command = json.loads(line)
                            if isinstance(command,dict):
                                control.command(command.get('command',''))
                        except (ValueError,TypeError):
                            pass
                # A disconnected GUI must not leave an orphan download running.
                control.command('stop')
            except (OSError,ValueError):
                control.command('stop')
        threading.Thread(target=listen,name='mira-controls',daemon=True).start()
        from .engine import run_job
        return run_job(options,emit,control)
    except Exception as exc:
        from .privacy import safe_message
        from .locking import DestinationBusy
        message = safe_message(exc) if isinstance(exc,(ValueError,DestinationBusy)) else 'Не удалось запустить задание. Проверьте настройки и комплектность приложения.'
        emit({'type':'log','level':'error','message':message})
        emit({'type':'state','state':'error','message':message})
        return 1


def main():
    if '--version' in sys.argv[1:]:
        _restore_stream('stdout',-11,'w')
        _restore_stream('stderr',-12,'w')
    parser = argparse.ArgumentParser(description='Mira Media Downloader')
    parser.add_argument('--worker',metavar='REQUEST',help=argparse.SUPPRESS)
    parser.add_argument('--screenshot',metavar='PNG',help=argparse.SUPPRESS)
    parser.add_argument('--design-probe',metavar='DIRECTORY',help=argparse.SUPPRESS)
    parser.add_argument('--startup-probe',metavar='DIRECTORY',help=argparse.SUPPRESS)
    parser.add_argument('--login-probe',metavar='DIRECTORY',help=argparse.SUPPRESS)
    parser.add_argument('--login-probe-live',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--pixiv-auth-fixture',action='store_true',help=argparse.SUPPRESS)
    parser.add_argument('--login-platform',choices=('x','pixiv'),default='x',help=argparse.SUPPRESS)
    parser.add_argument('--login-language',choices=('ru','en','zh_CN'),default='ru',help=argparse.SUPPRESS)
    from . import __version__
    parser.add_argument('--version',action='version',version=f'Mira Media Downloader {__version__}')
    args = parser.parse_args()
    if args.worker:
        return worker(args.worker)
    from .app_identity import set_windows_app_id
    set_windows_app_id()
    # Configure Chromium before either QApplication or WebEngine initializes.
    from .webengine_runtime import configure_login_runtime
    configure_login_runtime()
    if args.login_probe:
        if args.pixiv_auth_fixture:
            from .pixiv_login_diagnostics import pixiv_signin_probe
            return pixiv_signin_probe(args.login_probe)
        from .diagnostics import login_probe
        return login_probe(args.login_probe,args.login_probe_live,args.login_platform,args.login_language)
    if args.screenshot or args.design_probe or args.startup_probe:
        # Release screenshots must never enumerate a person's real collection,
        # alter their preferences or open their saved authentication vault.
        from PySide6.QtCore import QSettings
        screenshot_root = Path(args.startup_probe or args.design_probe).resolve() if (args.startup_probe or args.design_probe) else Path(args.screenshot).resolve().parent
        QSettings.setDefaultFormat(QSettings.Format.IniFormat)
        QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                          str(screenshot_root / 'isolated-ui-settings'))
        preferences = QSettings('Mira', 'MiraMediaDownloader')
        preferences.clear()
        preferences.setValue('destination', str(screenshot_root / 'empty-preview-collection'))
        if args.startup_probe:
            language = os.environ.get('MIRA_STARTUP_LANGUAGE', 'ru')
            theme = os.environ.get('MIRA_STARTUP_THEME', 'light')
            preferences.setValue('ui_language', language if language in ('ru','en','zh_CN') else 'ru')
            preferences.setValue('ui_theme', theme if theme in ('light','dark') else 'light')
        preferences.sync()
        os.environ['MIRA_SESSION_DIR'] = str(screenshot_root / 'isolated-empty-ui-vault')
        if args.startup_probe:
            os.environ['APPDATA'] = str(screenshot_root / 'isolated-roaming')
            os.environ['LOCALAPPDATA'] = str(screenshot_root / 'isolated-local')
    if args.design_probe:
        from .design_diagnostics import design_probe
        return design_probe(args.design_probe)
    from .ui import run_gui
    if args.startup_probe:
        return run_gui(str(Path(args.startup_probe).resolve() / 'startup-main.png'))
    return run_gui(args.screenshot or '')


if __name__ == '__main__':
    raise SystemExit(main())
