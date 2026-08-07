# Манифест состояния твина: twin/data/manifest.json.
# Полностью повторяет дисциплину атласа (atlas/state.py): статусы источников,
# чанки с резюмируемостью, реестр parquet-файлов. Класс Manifest общий.

from __future__ import annotations

import os

from atlas.state import Manifest as _Manifest, now_iso, sha256_file  # noqa: F401

TWIN_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(TWIN_DIR, "data")
RAW_DIR = os.path.join(DATA_DIR, "_raw")
MANIFEST_PATH = os.path.join(DATA_DIR, "manifest.json")


class Manifest(_Manifest):
    def __init__(self, path: str = MANIFEST_PATH):
        super().__init__(path)


def disk_free_gb(path: str = DATA_DIR) -> float:
    os.makedirs(path, exist_ok=True)
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 1e9
