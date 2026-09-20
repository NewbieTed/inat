from __future__ import annotations

import os
from pathlib import Path

from platformdirs import user_data_path


def default_db_path() -> Path:
    """Return the application database, honoring an explicit override."""
    override = os.environ.get("INAT_DB")
    if override:
        return Path(override).expanduser()
    return user_data_path("inat", appauthor=False) / "inat.db"

