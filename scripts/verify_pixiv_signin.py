"""Run the actual public EXE's offline Pixiv Save-dialog acceptance fixture."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('executable', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--timeout', type=float, default=45)
    args = parser.parse_args()
    executable, root = args.executable.resolve(), args.output.resolve()
    task = Path(__file__).resolve().parents[3]
    if root == task or not root.is_relative_to(task) or root.exists():
        parser.error('Use a new task-owned output directory.')
    if args.timeout <= 0:
        parser.error('Timeout must be positive.')
    root.mkdir(parents=True)
    core = executable.parent / 'runtime' / 'MiraMediaDownloaderCore.exe'
    result = {'passed': False, 'public_exe_sha256': sha256(executable),
              'core_sha256': sha256(core), 'actual_user_cookies_accessed': False,
              'network_requests_allowed': 0, 'forced_termination': False, 'errors': []}
    result['exe_sha256'] = result['public_exe_sha256']
    result['network_requests'] = 0
    environment = dict(os.environ)
    environment.update(APPDATA=str(root / 'isolated-roaming'), LOCALAPPDATA=str(root / 'isolated-local'),
                       MIRA_SESSION_DIR=str(root / 'wrapper-empty-vault'), PYTHONIOENCODING='utf-8')
    started = time.monotonic()
    with (root / 'stdout.log').open('wb') as stdout, (root / 'stderr.log').open('wb') as stderr:
        process = subprocess.Popen([str(executable), '--login-probe', str(root / 'fixture'), '--pixiv-auth-fixture'],
                                   env=environment, stdout=stdout, stderr=stderr,
                                   creationflags=subprocess.CREATE_NO_WINDOW)
        try:
            code = process.wait(timeout=args.timeout)
            result['actual_parent_exit_code'] = code
            if code != 0:
                raise AssertionError('Actual Pixiv fixture process returned a failure.')
            data = json.loads((root / 'fixture' / 'pixiv-signin-probe.json').read_text(encoding='utf-8'))
            if (not data.get('passed') or data.get('errors') or
                    data.get('actual_user_cookies_accessed') is not False or
                    data.get('network_requests_allowed') != 0):
                raise AssertionError('Packaged Pixiv Save-dialog fixture did not pass.')
            result.update(passed=True, probe=data, fixture_receipt=str(root / 'fixture' / 'pixiv-signin-probe.json'))
        except Exception as exc:
            result['errors'].append(type(exc).__name__ + ': ' + str(exc))
        finally:
            if process.poll() is None:
                subprocess.run([str(Path(os.environ['SystemRoot']) / 'System32' / 'taskkill.exe'),
                                '/PID', str(process.pid), '/T', '/F'],
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               timeout=20, creationflags=subprocess.CREATE_NO_WINDOW)
                process.wait(timeout=10)
                result['forced_termination'] = True
                result['passed'] = False
    result['elapsed_seconds'] = round(time.monotonic() - started, 2)
    (root / 'pixiv-signin-smoke.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'passed': result['passed'], 'errors': result['errors']}, ensure_ascii=True))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
