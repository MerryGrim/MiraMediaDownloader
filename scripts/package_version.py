# SPDX-License-Identifier: GPL-2.0-or-later
"""Read the project version without shell-dependent inline quoting."""
from pathlib import Path
import tomllib

print(tomllib.loads((Path(__file__).resolve().parents[1] / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"])
