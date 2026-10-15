"""CLI QA compatibility imports; the frozen-safe implementation lives in the app."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from mira_media.corner_capture import BACKGROUND, client_geometry, composed_corner_proof

__all__ = ['BACKGROUND', 'client_geometry', 'composed_corner_proof']
