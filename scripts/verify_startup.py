"""Measure the shipped native loader and first-paint handoff, using empty data."""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from PIL import Image

from windows_capture import api, windows, capture
from window_corners import client_geometry, composed_corner_proof


def artwork_pixel_proof(frame):
    """Check visible pastel artwork, independent of DPI and exact bitmap bytes.

    The left art panel occupies roughly the first two fifths of the native
    landscape loader. Ignore its outer border and sample broad color areas;
    grayscale text/a monogram, a flat tinted rectangle and a blank capture do
    not provide sufficient chromatic coverage and variation.
    """
    image=frame.convert('RGB')
    width,height=image.size
    fractions=(0.04,0.08,0.375,0.925)
    box=tuple(round(value*dimension) for value,dimension in
              zip(fractions,(width,height,width,height)))
    region=image.crop(box).resize((160,160),Image.Resampling.BILINEAR)
    samples=list(region.getdata())
    pastel=[(r,g,b) for r,g,b in samples
            if max(r,g,b)>=140 and min(r,g,b)>=65 and 24<=max(r,g,b)-min(r,g,b)<=155]
    bins={(r//16,g//16,b//16) for r,g,b in pastel}
    fraction=len(pastel)/len(samples)
    nonblank=any(high-low>30 for low,high in image.getextrema())
    landscape=width>height
    return {'passed':bool(nonblank and landscape and fraction>=0.045 and len(bins)>=8),
            'image_size':[width,height],'landscape':landscape,'whole_image_nonblank':nonblank,
            'left_art_region':list(box),'region_fraction':list(fractions),
            'sample_pixels':len(samples),'pastel_colored_pixels':len(pastel),
            'pastel_colored_fraction':round(fraction,5),'pastel_color_bins':len(bins),
            'minimum_pastel_fraction':0.045,'minimum_color_bins':8}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable',type=Path); parser.add_argument('output',type=Path)
    args=parser.parse_args(); executable=args.executable.resolve(); root=args.output.resolve()
    task=Path(__file__).resolve().parents[3]
    assert root.is_relative_to(task) and not root.exists(), 'Use a new task-owned output directory'
    root.mkdir(parents=True)
    result={'passed':False,'exe_sha256':hashlib.sha256(executable.read_bytes()).hexdigest(),
            'actual_user_cookies_accessed':False,'network_requests':0,'languages':{},'errors':[]}
    artwork=Path(__file__).resolve().parents[1]/'assets'/'installer-welcome-cloud-v1.png'
    with Image.open(artwork) as source:
        result['startup_art_source']={'name':artwork.name,'sha256':hashlib.sha256(artwork.read_bytes()).hexdigest(),
                                      'image_size':list(source.size)}
    user=api()
    from ctypes import wintypes
    user.GetWindowLongPtrW.argtypes=[wintypes.HWND,ctypes.c_int]
    user.GetWindowLongPtrW.restype=ctypes.c_ssize_t
    try:
        for language,theme in [('ru','light'),('en','light'),('zh_CN','dark')]:
            directory=root/language; directory.mkdir()
            environment=dict(os.environ)
            environment.update(MIRA_STARTUP_LANGUAGE=language,MIRA_STARTUP_THEME=theme,
                               MIRA_STARTUP_TRACE=str(directory/'native-timing.json'),
                               APPDATA=str(directory/'isolated-roaming'),
                               LOCALAPPDATA=str(directory/'isolated-local'),
                               MIRA_SESSION_DIR=str(directory/'isolated-empty-vault'))
            started=time.monotonic(); screenshot=None; visible_ms=None; proof=None; caption_bits=None; corner_proof=None
            with (directory/'stdout.log').open('wb') as stdout,(directory/'stderr.log').open('wb') as stderr:
                process=subprocess.Popen([str(executable),'--startup-probe',str(directory/'gui')],
                    env=environment,stdout=stdout,stderr=stderr,creationflags=subprocess.CREATE_NO_WINDOW)
                try:
                    deadline=time.monotonic()+30
                    while process.poll() is None and time.monotonic()<deadline:
                        if screenshot is None:
                            owned=windows(process.pid,class_name='MiraNativeStartup')
                            if owned:
                                caption_bits=user.GetWindowLongPtrW(owned[0][0],-16) & 0x00c00000
                                geometry=client_geometry(owned[0][0])
                                assert geometry['client']==geometry['window'], 'Loader has a caption/frame inset'
                                if visible_ms is None:
                                    visible_ms=round((time.monotonic()-started)*1000)
                                try:
                                    painted=json.loads((directory/'native-timing.json').read_text(encoding='utf-8'))['first_paint_ms']>=0
                                except (OSError,ValueError,KeyError):
                                    painted=False
                                if painted:
                                    target=directory/'startup-indicator.png'
                                    capture(owned[0][0],target)
                                    with Image.open(target) as frame:
                                        proof=artwork_pixel_proof(frame)
                                        if proof['passed']:
                                            corner_proof=composed_corner_proof(owned[0][0],directory/'startup-corners.png',rounded=True)
                                            assert corner_proof['passed'], corner_proof
                                            screenshot=target
                        time.sleep(0.01)
                    assert process.poll() is not None, 'Startup process did not finish'
                    assert process.returncode==0, 'Actual startup returned a failure'
                finally:
                    if process.poll() is None:
                        subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],
                            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                            creationflags=subprocess.CREATE_NO_WINDOW,timeout=20)
                        process.wait(timeout=10)
            trace=json.loads((directory/'native-timing.json').read_text(encoding='utf-8'))
            assert trace['dismiss_reason']=='ready' and trace['exit_code']==0,trace
            assert 0<=trace['first_paint_ms']<=trace['core_spawn_ms']<trace['ready_ms']<=trace['exit_ms'],trace
            assert screenshot and screenshot.is_file(), ('No landscape loader with visible pastel artwork captured',proof)
            assert (directory/'gui'/'startup-main.png').is_file()
            assert visible_ms<1500, 'Native indicator took too long to become visible on this host'
            result['languages'][language]={'theme':theme,'timing':trace,'visible_after_ms':visible_ms,
                                          'no_standard_caption':True,
                                          'native_caption_bits':caption_bits,'artwork_pixel_proof':proof,
                                          'corner_pixel_proof':corner_proof,
                                          'screenshot':str(screenshot),'actual_parent_exit_code':0}
        result['themes_with_verified_art']=sorted({item['theme'] for item in result['languages'].values()
                                                 if item['artwork_pixel_proof']['passed']})
        result['tested_combinations']=[{'language':language,'theme':item['theme']}
                                       for language,item in result['languages'].items()]
        result['passed']=len(result['languages'])==3 and result['themes_with_verified_art']==['dark','light']
    except Exception as exc:
        result['errors'].append(type(exc).__name__+': '+str(exc))
    (root/'startup-smoke.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed':result['passed'],'languages':list(result['languages']),'errors':result['errors']},ensure_ascii=True))
    return 0 if result['passed'] else 1


if __name__=='__main__':
    raise SystemExit(main())
