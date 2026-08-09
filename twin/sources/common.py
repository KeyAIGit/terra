# Общие помощники источников твина: контекст с бюджетом, докачиваемый HTTP
# (реиспользуем атласный download — он дюк-типизирован по ctx), писатель
# Parquet-шардов в twin/data/.

from __future__ import annotations

import os
import time

import pyarrow.parquet as pq
import requests

from atlas.sources.common import (  # noqa: F401
    BudgetExceeded, DiskLow, SHARD_MAX_BYTES, download, to_float, to_int,
    zip_member,
)
from twin import schema
from twin.state import DATA_DIR, RAW_DIR, disk_free_gb

USER_AGENT = "TERRA-twin/0.1 (https://github.com/KeyAIGit/terra; info.rfid24@gmail.com)"
MIN_FREE_GB = 8.0


class Ctx:
    """Контекст запуска: дедлайн, манифест, HTTP-сессия."""

    def __init__(self, manifest, deadline: float):
        self.manifest = manifest
        self.deadline = deadline
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def time_left(self) -> float:
        return self.deadline - time.monotonic()

    def check(self, need_seconds: float = 15.0) -> None:
        if self.time_left() < need_seconds:
            raise BudgetExceeded(f"осталось {self.time_left():.0f}с")
        free = disk_free_gb()
        if free < MIN_FREE_GB:
            raise DiskLow(f"свободно {free:.1f} ГБ < {MIN_FREE_GB} ГБ")


def src_dir(name: str) -> str:
    d = os.path.join(DATA_DIR, name)
    os.makedirs(d, exist_ok=True)
    return d


def raw_path(name: str, filename: str) -> str:
    d = os.path.join(RAW_DIR, name)
    os.makedirs(d, exist_ok=True)
    return os.path.join(d, filename)


def write_one_shard(kind: str, records: list[dict], out_dir: str, fname: str) -> str:
    """Один именованный шард (чанковая резюмируемость). Путь — от DATA_DIR."""
    for rec in records[:40] + records[-3:]:
        errs = schema.validate_record(kind, rec)
        if errs:
            raise ValueError(f"запись не прошла схему ({fname}): {errs}")
    tbl = schema.records_to_table(kind, records)
    full = os.path.join(out_dir, fname)
    pq.write_table(tbl, full, compression="snappy")
    if os.path.getsize(full) > SHARD_MAX_BYTES:
        raise ValueError(f"шард {fname} крупнее 256 МБ — уменьшите чанк")
    return os.path.relpath(full, DATA_DIR)


def rel_data(path: str) -> str:
    return os.path.relpath(path, DATA_DIR)


# ── разбор высот OSM ────────────────────────────────────────────────────────
LEVEL_M = 3.2          # метров на этаж, если высоты нет
DEFAULT_H = 5.0        # высота здания без каких-либо подсказок


def parse_height(tags: dict) -> tuple[float, str]:
    """Высота здания в метрах + происхождение ('height'/'levels'/'default').

    Понимает '25', '25 m', '25m', '82 ft'; этажность building:levels.
    """
    h = tags.get("height") or tags.get("building:height")
    if h:
        s = str(h).strip().lower().replace(",", ".")
        try:
            if s.endswith("ft"):
                return float(s[:-2].strip()) * 0.3048, "height"
            if s.endswith("m"):
                s = s[:-1].strip()
            return float(s), "height"
        except ValueError:
            pass
    lv = tags.get("building:levels") or tags.get("levels")
    if lv:
        try:
            n = float(str(lv).replace(",", "."))
            if 0 < n < 200:
                return max(n, 1.0) * LEVEL_M, "levels"
        except ValueError:
            pass
    return DEFAULT_H, "default"
