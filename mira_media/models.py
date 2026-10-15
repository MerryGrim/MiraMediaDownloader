from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime, timezone
from pathlib import Path
import math


@dataclass(frozen=True)
class Profile:
    platform: str
    username: str
    url: str


@dataclass(frozen=True)
class MediaItem:
    key: str
    post_id: str
    index: int
    url: str
    extension: str
    posted: str
    author_id: str = ""
    fallback_urls: tuple[str, ...] = ()


@dataclass
class JobOptions:
    profile_url: str = ""
    destination: str = ""
    date_from: str = ""
    date_to: str = ""
    cookies_file: str = ""
    only_new: bool = True
    pixiv_enabled: bool = False
    request_delay: float = 3.0
    download_delay: float = 1.5
    mode: str = "download"
    job_id: str = ""
    auth_source: str = ""
    browser: str = ""
    browser_profile: str = ""

    @property
    def effective_auth_source(self) -> str:
        # Older requests predate the explicit source selector.
        return self.auth_source or ('file' if self.cookies_file else 'none')

    @classmethod
    def from_dict(cls, data: dict) -> "JobOptions":
        obj = cls(**{f.name: data[f.name] for f in fields(cls) if f.name in data})
        for name in ('date_from','date_to','cookies_file','job_id','auth_source','browser','browser_profile'):
            setattr(obj,name,getattr(obj,name) or '')
        obj.validate()
        return obj

    def validate(self) -> None:
        if self.mode not in ("download", "preview"):
            raise ValueError("Неизвестный режим задания.")
        if not self.destination or not Path(self.destination).is_absolute():
            raise ValueError("Выберите абсолютный путь к папке хранения.")
        for value in (self.date_from, self.date_to):
            if value:
                date.fromisoformat(value)
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("Начало периода должно быть раньше его окончания.")
        if self.auth_source not in ('', 'embedded', 'browser', 'file', 'none'):
            raise ValueError('Выберите вход в приложении, браузер, файл или режим без авторизации.')
        if self.effective_auth_source == 'file':
            if not self.cookies_file or not Path(self.cookies_file).is_file():
                raise ValueError("Выбранный файл cookies не найден. Выберите его заново.")
        if self.effective_auth_source == 'browser':
            if self.browser not in ('firefox','chrome','edge','brave'):
                raise ValueError('Выберите поддерживаемый браузер.')
            if not self.browser_profile:
                raise ValueError('Выберите профиль браузера, в котором выполнен вход в X.')
        for name, floor in (("request_delay", 2.0), ("download_delay", 1.0)):
            value = float(getattr(self, name))
            if not math.isfinite(value):
                raise ValueError("Интервал запросов должен быть конечным числом.")
            setattr(self, name, max(floor, min(value, 120.0)))


def within_dates(posted: str, options: JobOptions) -> bool:
    if not options.date_from and not options.date_to:
        return True
    if not posted:
        return False
    try:
        moment = datetime.fromisoformat(posted.replace("Z", "+00:00"))
        if moment.tzinfo is None:
            moment = moment.replace(tzinfo=timezone.utc)
        day = moment.astimezone(timezone.utc).date().isoformat()
    except (ValueError, TypeError):
        return False
    return (not options.date_from or day >= options.date_from) and (
        not options.date_to or day <= options.date_to)
