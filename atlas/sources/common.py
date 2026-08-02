# Общие помощники источников: докачиваемый HTTP, писатель Parquet-шардов,
# контроль бюджета времени и диска.

from __future__ import annotations

import os
import time
import zipfile

import pyarrow as pa
import pyarrow.parquet as pq
import requests

from atlas import schema
from atlas.state import DATA_DIR, RAW_DIR, disk_free_gb

USER_AGENT = "TERRA-atlas/0.1 (https://github.com/KeyAIGit/terra; info.rfid24@gmail.com)"
MIN_FREE_GB = 8.0          # жёсткий стоп по диску
SHARD_MAX_BYTES = 256 * 1024 * 1024  # предел размера шарда


class BudgetExceeded(Exception):
    """Вышло время бюджета — источник сохраняется как partial."""


class DiskLow(Exception):
    """Свободного диска меньше порога — глобальный стоп."""


class Ctx:
    """Контекст запуска: дедлайн, манифест, каталоги."""

    def __init__(self, manifest, deadline: float):
        self.manifest = manifest
        self.deadline = deadline
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def time_left(self) -> float:
        return self.deadline - time.monotonic()

    def check(self, need_seconds: float = 15.0) -> None:
        """Проверка бюджета и диска между чанками."""
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


def download(ctx: Ctx, url: str, dest: str, resume: bool = True,
             timeout: int = 60, max_retries: int = 3) -> str:
    """Скачивание с докачкой через Range в dest (.part до завершения).

    Возвращает dest. Уже скачанный файл не трогает. Уважает бюджет ctx:
    при его истечении бросает BudgetExceeded, .part остаётся для докачки.
    """
    if os.path.exists(dest):
        return dest
    part = dest + ".part"
    for attempt in range(max_retries):
        ctx.check()
        have = os.path.getsize(part) if (resume and os.path.exists(part)) else 0
        headers = {"Range": f"bytes={have}-"} if have else {}
        try:
            with ctx.session.get(url, stream=True, timeout=timeout, headers=headers) as r:
                if have and r.status_code == 200:
                    have = 0  # сервер не умеет Range — начинаем заново
                elif have and r.status_code != 206:
                    r.raise_for_status()
                r.raise_for_status()
                mode = "ab" if have else "wb"
                with open(part, mode) as f:
                    last_check = time.monotonic()
                    for blk in r.iter_content(chunk_size=1 << 20):
                        f.write(blk)
                        if time.monotonic() - last_check > 5:
                            last_check = time.monotonic()
                            if ctx.time_left() < 10:
                                raise BudgetExceeded("бюджет кончился при скачивании")
                            if disk_free_gb() < MIN_FREE_GB:
                                raise DiskLow("мало диска при скачивании")
            os.replace(part, dest)
            return dest
        except (BudgetExceeded, DiskLow):
            raise
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            time.sleep(3 * (attempt + 1))
            print(f"    повтор скачивания ({e})")
    return dest


def drop_raw(name: str) -> None:
    """Удалить сырьё источника (скачал → обработал → удали)."""
    import shutil
    d = os.path.join(RAW_DIR, name)
    if os.path.isdir(d):
        shutil.rmtree(d)


def zip_member(zpath: str, suffix: str, biggest: bool = True) -> str:
    """Имя элемента zip по суффиксу (при biggest — самый крупный)."""
    with zipfile.ZipFile(zpath) as z:
        cands = [i for i in z.infolist()
                 if i.filename.lower().endswith(suffix.lower())
                 and not i.filename.startswith("__MACOSX")]
        if not cands:
            raise FileNotFoundError(f"в {zpath} нет *{suffix}")
        cands.sort(key=lambda i: i.file_size, reverse=biggest)
        return cands[0].filename


def write_shards(kind: str, records: list[dict], out_dir: str, prefix: str,
                 rows_per_shard: int = 200_000) -> tuple[list[str], int]:
    """Пишет записи в Parquet-шарды (snappy) <prefix>_NNNN.parquet.

    Валидирует образец записей до записи. Возвращает (относительные пути
    от DATA_DIR, число строк). Контроль 256 МБ: если шард вышел крупнее —
    режем пополам по строкам и переписываем.
    """
    if not records:
        return [], 0
    for rec in records[:50] + records[-5:]:
        errs = schema.validate_record(kind, rec)
        if errs:
            raise ValueError(f"запись не прошла схему ({prefix}): {errs}; rec={ {k: rec.get(k) for k in list(rec)[:8]} }")
    paths: list[str] = []
    n = len(records)
    shard_idx = 0
    i = 0
    step = rows_per_shard
    while i < n:
        batch = records[i:i + step]
        tbl = schema.records_to_table(kind, batch)
        fname = f"{prefix}_{shard_idx:04d}.parquet"
        full = os.path.join(out_dir, fname)
        pq.write_table(tbl, full, compression="snappy")
        if os.path.getsize(full) > SHARD_MAX_BYTES and len(batch) > 1:
            # слишком жирный шард — уменьшаем шаг и переписываем
            os.unlink(full)
            step = max(1, step // 2)
            continue
        rel = os.path.relpath(full, DATA_DIR)
        paths.append(rel)
        shard_idx += 1
        i += len(batch)
    return paths, n


def write_one_shard(kind: str, records: list[dict], out_dir: str, fname: str) -> str:
    """Пишет ОДИН именованный шард (для чанковой резюмируемости, как у Met).

    Возвращает путь относительно DATA_DIR. Валидирует образец записей.
    """
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


def write_source_row(name: str, out_dir: str, url: str, license: str,
                     title: str, description: str, tier: str = "K") -> list[str]:
    """Служебная запись kind=source c описанием датасета."""
    rec = schema.base_record("source", url, license, tier)
    rec.update({"id": f"src:{name}", "url": url, "title": title,
                "description": description})
    paths, _ = write_shards("source", [rec], out_dir, "source", 10)
    return paths


def to_float(v):
    """Мягкий float: '' / None / мусор -> None."""
    try:
        if v is None or v == "":
            return None
        x = float(v)
        if x != x:  # NaN
            return None
        return x
    except (TypeError, ValueError):
        return None


def to_int(v):
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except (TypeError, ValueError):
        return None
