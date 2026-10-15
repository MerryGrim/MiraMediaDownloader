"""Two-page public end-to-end check, explicitly bounded and account-free."""
from __future__ import annotations

import argparse
from itertools import islice
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image
from mira_media.adapters import GalleryAdapter
from mira_media.downloads import file_hash
from mira_media.engine import run_job
from mira_media.models import JobOptions


class TwoPages(GalleryAdapter):
    def iter_media(self):
        yield from islice(super().iter_media(), 2)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('profile')
    parser.add_argument('output')
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    report = {'profile': args.profile, 'sample_limit_images': 2,
              'actual_user_cookies_accessed': False, 'account_login_tested': False,
              'full_gallery_scanned': False, 'runs': [], 'files': []}
    for number in range(2):
        events = []
        options = JobOptions(profile_url=args.profile, destination=str(root), pixiv_enabled=True,
                             auth_source='none', only_new=True, request_delay=3.0, download_delay=1.5)
        code = run_job(options, events.append, adapter_factory=TwoPages)
        stats = [event for event in events if event['type'] == 'stats'][-1]
        report['runs'].append({'exit_code': code, 'stats': stats,
                               'states': [event['state'] for event in events if event['type'] == 'state'],
                               'messages': [event['message'] for event in events if event['type'] == 'log']})
        (root / 'download-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        assert code == 0 and stats['found'] == 2 and stats['failed'] == 0
        assert stats['downloaded'] == (2 if number == 0 else 0)
        assert stats['skipped'] == (0 if number == 0 else 2)
    for path in sorted((root / 'Pixiv').rglob('*.png')):
        with Image.open(path) as image:
            size = image.size
            image.verify()
        report['files'].append({'path': str(path.relative_to(root)), 'size': path.stat().st_size,
                                'dimensions': size, 'sha256': file_hash(path)})
    assert len(report['files']) == 2
    assert not list(root.rglob('*.part'))
    (root / 'download-check.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
