"""Small exact URL allowlists; input never reaches a generic extractor."""

import re
from urllib.parse import parse_qs, urlsplit

from mira_media.models import Profile


class ProfileError(ValueError):
    pass


_RESERVED_X = {
    "home", "search", "explore", "i", "intent", "share", "settings", "messages",
    "notifications", "login", "logout", "signup", "tos", "privacy", "compose",
    "hashtag", "jobs", "download", "about", "help", "account", "oauth",
}
IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp", "avif"}


def _split_url(value):
    if not isinstance(value, str) or len(value) > 2048:
        raise ProfileError("Некорректная ссылка.")
    value = value.strip()
    if any(ord(ch) < 32 for ch in value) or "\\" in value:
        raise ProfileError("Некорректная ссылка.")
    if "://" not in value:
        value = "https://" + value
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError:
        raise ProfileError("Некорректная ссылка.") from None
    if (parsed.scheme.lower() != "https" or parsed.username is not None
            or parsed.password is not None or port not in (None, 443)):
        raise ProfileError("Используйте HTTPS-ссылку на профиль X или Pixiv.")
    return parsed


def parse_profile(url: str, pixiv_enabled: bool = False) -> Profile:
    parsed = _split_url(url)
    host = (parsed.hostname or "").lower()
    if host in {"x.com", "www.x.com", "twitter.com", "www.twitter.com"}:
        match = re.fullmatch(r"/([A-Za-z0-9_]{1,15})(?:/media)?/?", parsed.path)
        if not match or match[1].lower() in _RESERVED_X:
            raise ProfileError("Нужна ссылка на профиль X: https://x.com/имя или /имя/media.")
        name = match[1]
        return Profile("x", name, f"https://x.com/{name}/media")
    if host in {"pixiv.net", "www.pixiv.net"}:
        match = re.fullmatch(r"/(?:en/)?users/([1-9][0-9]*)(?:/artworks)?/?", parsed.path)
        if not match:
            raise ProfileError("Нужна ссылка Pixiv вида https://www.pixiv.net/users/12345.")
        if not pixiv_enabled:
            raise ProfileError("Pixiv отключён. Включите экспериментальный адаптер в настройках.")
        user_id = match[1]
        return Profile("pixiv", user_id, f"https://www.pixiv.net/users/{user_id}/artworks")
    raise ProfileError("Поддерживаются только профили x.com, twitter.com и опционально pixiv.net.")


def validate_media_url(platform: str, url: str) -> bool:
    """Allow original CDN images and X's explicit standard size fallbacks."""
    if not isinstance(url, str) or not url.startswith("https://"):
        return False
    try:
        parsed = _split_url(url)
    except (ValueError, TypeError):
        return False
    if parsed.fragment:
        return False
    host = (parsed.hostname or "").lower()
    if platform == "x":
        if host != "pbs.twimg.com":
            return False
        if not re.fullmatch(r"/media/[A-Za-z0-9_-]+(?:\.(?:jpg|jpeg|png|gif|webp|avif))?", parsed.path, re.I):
            return False
        query = parse_qs(parsed.query)
        return (len(query.get("name", [])) == 1
                and query["name"][0] in {"orig", "4096x4096", "large", "medium", "small"}
                and query.get("format", [parsed.path.rpartition(".")[2].lower()])[0].lower()
                in IMAGE_EXTENSIONS)
    if platform == "pixiv":
        return (host == "i.pximg.net"
                and bool(re.fullmatch(r"/img-original/img/[0-9/]+/[A-Za-z0-9_-]+\.(?:jpg|jpeg|png|gif|webp|avif)", parsed.path, re.I))
                and not parsed.query)
    return False
