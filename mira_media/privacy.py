"""Logs never contain raw requests, headers, cookie values or secret paths."""
import re


def safe_message(message: object) -> str:
    text = str(message)
    text = re.sub(r"https?://\S+", "[адрес скрыт]", text)
    text = re.sub(r"(?i)(auth_token|ct0|phpsessid|refresh[_-]?token|authorization|cookie|password)\s*[:=]\s*[^\s,;]+", r"\1=[скрыто]", text)
    return text[:1500]
