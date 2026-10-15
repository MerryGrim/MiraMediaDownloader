"""Offline source-contract fixtures; these do not claim live account coverage."""

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from mira_media.adapters import AdapterError, GalleryAdapter, parse_profile, validate_media_url
from mira_media.adapters.gallery import GuardedSession, _load_cookies
from mira_media.control import Cancelled
from mira_media.models import JobOptions


class ControlFixture:
    def __init__(self):
        self.waits = []
        self.stopped = False
        self.checks = 0

    def check(self):
        self.checks += 1
        if self.stopped:
            raise Cancelled()

    def wait(self, seconds):
        self.waits.append(seconds)
        self.check()


def options(**kwargs):
    return JobOptions(destination=str(Path.cwd()), **kwargs)


def response(status=200, body=None, location=None):
    import json
    item = requests.Response()
    item.status_code = status
    item._content = json.dumps(body or {}).encode()
    item._content_consumed = True
    item.url = "https://x.com/example"
    if location:
        item.headers["Location"] = location
    return item


@pytest.mark.parametrize("url,canonical", [
    ("https://x.com/Example", "https://x.com/Example/media"),
    ("twitter.com/example/media/?s=20", "https://x.com/example/media"),
    ("https://www.twitter.com/a_1", "https://x.com/a_1/media"),
])
def test_x_profile_canonicalization(url, canonical):
    assert parse_profile(url).url == canonical
    assert parse_profile(url).platform == "x"


@pytest.mark.parametrize("url", [
    "https://x.com/search?q=from:example", "https://x.com/example/status/123",
    "https://evil.test/example", "https://x.com.evil.test/example",
    "https://x.com@evil.test/example", "https://evil.test@x.com/example",
    "https://nitter.net/example", "https://fxtwitter.com/example",
    "http://x.com/example", "https://x.com:123/example", "https://x.com/i",
    "https://x.com/home", "https://x.com/example/likes", "https://x.com/%65xample",
    "https://x.com/example\\evil", "https://x.com/exam\nple",
    "https://www.pixiv.net/artworks/123", "https://pixiv.net/users/0",
])
def test_profile_input_allowlist(url):
    with pytest.raises(ValueError):
        parse_profile(url, pixiv_enabled=True)


def test_pixiv_opt_in_and_canonicalization():
    with pytest.raises(ValueError, match="отключён"):
        parse_profile("https://www.pixiv.net/en/users/123")
    profile = parse_profile("https://pixiv.net/en/users/123/artworks/", True)
    assert (profile.platform, profile.username, profile.url) == (
        "pixiv", "123", "https://www.pixiv.net/users/123/artworks")


@pytest.mark.parametrize("platform,url,accepted", [
    ("x", "https://pbs.twimg.com/media/Ab_c-1?format=jpg&name=orig", True),
    ("x", "https://pbs.twimg.com/media/Abc.jpg?name=orig", True),
    ("x", "https://pbs.twimg.com/media/Abc?format=jpg&name=large", True),
    ("x", "https://pbs.twimg.com/media/Abc?format=jpg&name=arbitrary", False),
    ("x", "https://pbs.twimg.com/profile_images/Abc.jpg?name=orig", False),
    ("x", "https://pbs.twimg.com.evil.test/media/Abc?format=jpg&name=orig", False),
    ("x", "https://pbs.twimg.com/media/Abc?format=mp4&name=orig", False),
    ("x", "https://video.twimg.com/media/Abc.mp4", False),
    ("x", "pbs.twimg.com/media/Abc?format=jpg&name=orig", False),
    ("x", "https://name:token@pbs.twimg.com/media/Abc?format=jpg&name=orig", False),
    ("pixiv", "https://i.pximg.net/img-original/img/2026/01/01/00/00/00/123_p0.jpg", True),
    ("pixiv", "https://i.pximg.net/img-master/img/2026/01/01/00/00/00/123_p0_master1200.jpg", False),
    ("pixiv", "https://s.pximg.net/common/images/limit_unviewable_360.png", False),
])
def test_original_media_allowlists(platform, url, accepted):
    assert validate_media_url(platform, url) is accepted


def test_cookies_domain_filtering_and_no_disk_rewrite(tmp_path):
    path = tmp_path / "cookies.txt"
    payload = ("# Netscape HTTP Cookie File\n"
               ".twitter.com\tTRUE\t/\tTRUE\t2147483647\tauth_token\tprivate-token\n"
               ".x.com\tTRUE\t/\tTRUE\t2147483647\tct0\tprivate-csrf\n"
               ".evil.test\tTRUE\t/\tTRUE\t2147483647\tauth_token\twrong\n"
               ".pixiv.net\tTRUE\t/\tTRUE\t2147483647\tPHPSESSID\tpixiv-private\n")
    path.write_text(payload, encoding="utf-8")
    jar = _load_cookies(str(path), "x")
    assert {(c.domain, c.name) for c in jar} == {(".x.com", "auth_token"), (".x.com", "ct0")}
    assert jar.get("auth_token", domain=".x.com") == "private-token"
    pixiv_jar = _load_cookies(str(path), "pixiv")
    assert {(c.domain, c.name) for c in pixiv_jar} == {(".pixiv.net", "PHPSESSID")}
    assert path.read_text(encoding="utf-8") == payload


def test_malformed_cookie_errors_do_not_disclose_token(tmp_path):
    path = tmp_path / "cookies.txt"
    path.write_text("a private-token cookie\n", encoding="utf-8")
    with pytest.raises(AdapterError) as raised:
        _load_cookies(str(path), "x")
    assert "private-token" not in str(raised.value)


def test_malformed_netscape_cookie_values_never_warn_or_leak(tmp_path):
    import warnings
    path = tmp_path / "cookies.txt"
    path.write_text("# Netscape HTTP Cookie File\n.x.com\tTRUE\t/\tTRUE\tprivate-token\tauth_token\tsecret\n", encoding="utf-8")
    with warnings.catch_warnings(record=True) as recorded:
        warnings.simplefilter("always")
        with pytest.raises(AdapterError) as raised:
            _load_cookies(str(path), "x")
    assert recorded == []
    assert "private-token" not in str(raised.value)


def test_upstream_logging_never_relays_payloads_or_urls():
    from mira_media.adapters.gallery import _QuietLogger
    logs = []
    logger = _QuietLogger(lambda *args: logs.append(args))
    logger.debug("private-token")
    logger.warning("https://private.test/?token=private-token")
    logger.error("cookie=private-token")
    logger.traceback(Exception("private-token"))
    assert len(logs) == 1
    assert "private-token" not in str(logs)


@pytest.mark.parametrize("status", [401, 403, 429])
def test_access_denial_is_fatal_without_retry(status):
    control = ControlFixture()
    session = GuardedSession("x", options(), control)
    with patch.object(requests.Session, "request", return_value=response(status)) as send:
        with pytest.raises(AdapterError):
            session.get("https://x.com/i/api/graphql/fixture", timeout=(10, 25))
    assert send.call_count == 1
    assert control.waits == []


def test_request_pacing_pagination_and_bounded_network_retries():
    control = ControlFixture()
    session = GuardedSession("x", options(request_delay=3.0), control)
    with patch.object(requests.Session, "request", side_effect=requests.ConnectionError("private-token")) as send:
        with pytest.raises(AdapterError) as raised:
            session.get("https://x.com/i/api/graphql/fixture")
    assert send.call_count == 3
    assert "private-token" not in str(raised.value)
    assert control.waits
    assert control.checks >= 6


def test_redirect_to_login_stops_even_when_upstream_disables_redirects():
    session = GuardedSession("x", options(), ControlFixture())
    with patch.object(requests.Session, "request", return_value=response(302, location="https://x.com/i/flow/login")) as send:
        with pytest.raises(AdapterError):
            session.get("https://x.com/home", allow_redirects=False)
    assert send.call_count == 1


def test_cross_host_redirect_blocked_before_credentials_leave_platform():
    session = GuardedSession("x", options(), ControlFixture())
    with patch.object(requests.Session, "request", return_value=response(302, location="https://evil.test/")) as send:
        with pytest.raises(AdapterError):
            session.get("https://x.com/home")
    assert send.call_count == 1


def test_cancelled_control_prevents_request():
    control = ControlFixture()
    control.stopped = True
    session = GuardedSession("x", options(), control)
    with patch.object(requests.Session, "request") as send:
        with pytest.raises(Cancelled):
            session.get("https://x.com/home")
    send.assert_not_called()


def metadata(**kwargs):
    data = {"author": {"id": 42, "name": "example"}, "tweet_id": 123,
            "num": 1, "type": "photo", "extension": "jpg",
            "date": datetime(2026, 1, 2, tzinfo=timezone.utc)}
    data.update(kwargs)
    return data


def test_x_actual_backend_fixture_images_originals_multi_post_and_duplicates():
    from gallery_dl.extractor.common import Message
    from gallery_dl.extractor.twitter import TwitterMediaExtractor

    def fixture_items(extractor):
        assert extractor.config("logout") is False
        assert extractor.config("quoted") is False
        assert extractor.config("size") == ["orig", "4096x4096", "large", "medium", "small"]
        assert extractor._get_auth_info() == (None, None)
        yield Message.Url, "https://pbs.twimg.com/media/A?format=jpg&name=orig", metadata()
        yield Message.Url, "https://pbs.twimg.com/media/B?format=jpg&name=orig", metadata(num=2)
        yield Message.Url, "https://pbs.twimg.com/media/A?format=jpg&name=orig", metadata()
        yield Message.Url, "https://pbs.twimg.com/media/RT?format=jpg&name=orig", metadata(retweet_id=456)
        yield Message.Url, "https://pbs.twimg.com/media/Q?format=jpg&name=orig", metadata(quote_id=456, quote_by="example")
        yield Message.Url, "https://pbs.twimg.com/media/Else?format=jpg&name=orig", metadata(author={"id": 43, "name": "other"})
        yield Message.Url, "https://pbs.twimg.com/media/Gif?format=jpg&name=orig", metadata(type="animated_gif")

    adapter = GalleryAdapter(parse_profile("https://x.com/example"), options(), ControlFixture(), lambda *args: None)
    with patch.object(TwitterMediaExtractor, "items", fixture_items), \
            patch("gallery_dl.config.load", side_effect=AssertionError("global config accessed")), \
            patch("gallery_dl.cache.database", side_effect=AssertionError("global cache accessed")):
        media = list(adapter.iter_media())
    assert [(item.key, item.index, item.author_id) for item in media] == [("x:A", 1, "42"), ("x:B", 2, "42")]
    assert media[0].posted == "2026-01-02T00:00:00Z"
    adapter.close()


def test_missing_author_id_fails_instead_of_using_name_as_folder():
    adapter = GalleryAdapter(parse_profile("https://x.com/example"), options(), ControlFixture(), lambda *args: None)
    with pytest.raises(AdapterError, match="ID автора"):
        adapter._x_item("https://pbs.twimg.com/media/A?format=jpg&name=orig", metadata(author={"name": "example"}))


def test_own_attached_image_in_quoting_post_is_kept_but_expanded_quote_is_not():
    adapter = GalleryAdapter(parse_profile("https://x.com/example"), options(), ControlFixture(), lambda *args: None)
    url = "https://pbs.twimg.com/media/A?format=jpg&name=orig"
    # Current backend names the referenced post `quoted_id`; do not depend on
    # these numeric quote fields to decide ownership across backend versions.
    assert adapter._x_item(url, metadata(quoted_id=456)) is not None
    assert adapter._x_item(url, metadata(quote_id=456)) is not None
    assert adapter._x_item(url, metadata(quote_by="example")) is None
    assert adapter._x_item(url, metadata(quote_id=456, author={"id": 43, "name": "other"})) is None


def test_x_only_same_image_known_fallback_sizes_returned_by_extractor():
    adapter = GalleryAdapter(parse_profile("https://x.com/example"), options(), ControlFixture(), lambda *args: None)
    item = adapter._x_item("https://pbs.twimg.com/media/A?format=jpg&name=orig", metadata(_fallback=iter([
        "https://pbs.twimg.com/media/A?format=jpg&name=4096x4096",
        "https://pbs.twimg.com/media/A?format=jpg&name=large",
        "https://evil.test/A.jpg",
        "https://pbs.twimg.com/media/Other?format=jpg&name=large",
    ])))
    assert item.fallback_urls == (
        "https://pbs.twimg.com/media/A?format=jpg&name=4096x4096",
        "https://pbs.twimg.com/media/A?format=jpg&name=large",
    )


def test_date_boundaries_inclusive_and_utc():
    adapter = GalleryAdapter(parse_profile("https://x.com/example"), options(date_from="2026-01-02", date_to="2026-01-02"), ControlFixture(), lambda *args: None)
    assert adapter._in_dates("2026-01-02T00:00:00Z")
    assert adapter._in_dates("2026-01-02T23:59:59Z")
    assert not adapter._in_dates("2026-01-03T00:00:00Z")
    assert not adapter._in_dates("")


def test_pixiv_original_pages_only_no_guessed_or_restricted_fallback():
    logs = []
    adapter = GalleryAdapter(parse_profile("https://www.pixiv.net/users/123", True), options(pixiv_enabled=True), ControlFixture(), lambda *args: logs.append(args))
    original = "https://i.pximg.net/img-original/img/2026/01/01/00/00/00/456_p0.png"
    fixtures = {
        "user/123/profile/all": {"illusts": {"456": None, "455": None}, "manga": {}},
        "illust/456": {"userId": "123", "illustType": 0, "createDate": "2026-01-01T12:00:00+09:00"},
        "illust/456/pages": [{"urls": {"original": original}}, {"urls": {"original": "https://s.pximg.net/common/images/limit_unviewable_360.png"}}],
        "illust/455": {"userId": "123", "illustType": 2},
    }
    with patch.object(adapter, "_pixiv_json", side_effect=lambda path, **kwargs: fixtures[path]) as read:
        media = list(adapter.iter_media())
    assert len(media) == 1 and media[0].url == original and media[0].author_id == "123"
    assert media[0].posted == "2026-01-01T03:00:00Z"
    assert read.call_count == 4
    assert logs
