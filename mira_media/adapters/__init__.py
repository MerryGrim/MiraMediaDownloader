"""Restricted, local-only media source adapters.

The X adapter embeds gallery-dl's extractor, not its CLI/job runner.  It never
loads gallery-dl configuration, archives, credentials, browser stores, or disk
caches. Pixiv uses the website's returned original-image URLs and is opt-in.
"""

from .gallery import AdapterError, GalleryAdapter
from .profiles import parse_profile, validate_media_url

__all__ = ["AdapterError", "GalleryAdapter", "parse_profile", "validate_media_url"]
