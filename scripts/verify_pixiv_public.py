"""Bounded public metadata check; never imports a user session or downloads media."""
from __future__ import annotations

import argparse
from itertools import islice
import json
from pathlib import Path
import sys
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mira_media.adapters import GalleryAdapter, parse_profile
from mira_media.control import Control
from mira_media.models import JobOptions


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('profile')
    parser.add_argument('output')
    args = parser.parse_args()
    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    profile = parse_profile(args.profile, pixiv_enabled=True)
    assert profile.platform == 'pixiv'
    options = JobOptions(profile_url=profile.url, destination=str(output.parent),
                         pixiv_enabled=True, auth_source='none', mode='preview', request_delay=3.0)
    result = {'profile': profile.url, 'actual_user_cookies_accessed': False,
              'account_login_tested': False, 'image_files_downloaded': 0,
              'full_gallery_scanned': False, 'requests': 0, 'visible_post_ids': None,
              'sample': [], 'logs': []}
    adapter = GalleryAdapter(profile, options, Control(),
                             lambda level, message: result['logs'].append({'level': level, 'message': message}))
    read = adapter._pixiv_json

    def record(path, **kwargs):
        result['requests'] += 1
        # Hard bound protects this diagnostic from becoming a full gallery scan.
        if result['requests'] > 6:
            raise AssertionError('Public metadata diagnostic request budget exhausted')
        body = read(path, **kwargs)
        if path.endswith('/profile/all'):
            ids = set()
            for category in ('illusts', 'manga'):
                ids.update((body.get(category) or {}).keys())
            result['visible_post_ids'] = len(ids)
        return body

    adapter._pixiv_json = record
    try:
        for item in islice(adapter.iter_media(), 2):
            result['sample'].append({'key': item.key, 'post_id': item.post_id,
                                     'author_id': item.author_id, 'index': item.index,
                                     'extension': item.extension, 'posted': item.posted,
                                     'original_host': urlsplit(item.url).hostname})
        assert len(result['sample']) == 2, 'Could not observe two available image pages'
        assert all(item['author_id'] == profile.username for item in result['sample'])
        assert all(item['original_host'] == 'i.pximg.net' for item in result['sample'])
    finally:
        adapter.close()
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()
