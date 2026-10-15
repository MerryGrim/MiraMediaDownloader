"""Inspect real installer welcome pages in three languages; never install."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import time

from windows_capture import api, windows, children, capture


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('setup',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args(); setup=args.setup.resolve(); root=args.output.resolve()
    task=Path(__file__).resolve().parents[3]
    assert root.is_relative_to(task) and not root.exists(), 'Use a fresh task-owned output directory'
    root.mkdir(parents=True)
    result={'passed':False,'setup_sha256':hashlib.sha256(setup.read_bytes()).hexdigest(),
            'installation_started':False,'languages':{},'errors':[]}
    user=api()
    try:
        for language,expected in [('english','Welcome to Mira'),('russian','Добро пожаловать в Mira'),
                                  ('chinesesimp','欢迎使用 Mira')]:
            process=subprocess.Popen([str(setup),'/LANG='+language,'/SP-','/NORESTART',
                                      '/LOG='+str(root/(language+'.log'))],
                                     creationflags=subprocess.CREATE_NO_WINDOW)
            forced=False
            try:
                deadline=time.monotonic()+30; window=None; captions=[]
                while time.monotonic()<deadline:
                    for hwnd,cls,title in windows(process.pid):
                        if cls=='TWizardForm':
                            captions=[text.strip() for _,text in children(hwnd)]
                            if expected in captions:
                                window=hwnd; break
                    if window:
                        break
                    if process.poll() is not None:
                        raise AssertionError('Installer exited before welcome')
                    time.sleep(0.05)
                assert window, (language,'Welcome page missing',captions)
                time.sleep(0.25)
                screenshot=root/('welcome-'+language+'.png')
                size=capture(window,screenshot)
                assert any('Pixiv' in caption and 'X' in caption for caption in captions)
                # Only Cancel/close is exercised. No Next or Install button is clicked.
                user.PostMessageW(window,0x0010,0,0)
                deadline=time.monotonic()+15
                while process.poll() is None and time.monotonic()<deadline:
                    for hwnd,cls,title in windows(process.pid):
                        if hwnd==window:
                            continue
                        for button,caption in children(hwnd):
                            clean=caption.replace('&','').strip()
                            if clean in {'Yes','Да','是','是(Y)','是（Y）'}:
                                user.PostMessageW(button,0x00f5,0,0)
                    time.sleep(0.05)
                assert process.poll() is not None, 'Installer cancel did not finish'
                assert process.returncode==2, 'Welcome preview must cancel before installation (exit 2)'
                result['languages'][language]={'welcome_heading':expected,'captions':captions,
                    'screenshot':str(screenshot),'size':size,'exit_code':process.returncode,
                    'welcome_visible':True,'cancel_finished':True,'forced_termination':False}
            finally:
                if process.poll() is None:
                    forced=True
                    subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                   creationflags=subprocess.CREATE_NO_WINDOW,timeout=20)
                    process.wait(timeout=10)
                if forced:
                    result['errors'].append(language+': own preview child required termination')
        result['passed']=len(result['languages'])==3 and not result['errors']
    except Exception as exc:
        result['errors'].append(type(exc).__name__+': '+str(exc))
    (root/'installer-welcome.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'languages':list(result['languages']),'errors':result['errors']},ensure_ascii=True))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
