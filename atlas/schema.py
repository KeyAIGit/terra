# Единая схема записей склада TERRA-Атласа.
#
# Виды записей (kind): person / place / polity_snapshot / event / artifact /
# grid_layer / source. У КАЖДОЙ записи обязательны поля провенанса:
#   source    — URL или устойчивый id источника записи
#   license   — лицензия источника (SPDX-подобная строка)
#   tier      — ярус достоверности: "K" (известно из источника),
#               "T" (типично для эпохи-места), "R" (реконструкция/модель)
#   retrieved — дата получения (ISO YYYY-MM-DD)
#
# Разные источники добавляют свои колонки — это разрешено; валидатор
# проверяет обязательный костяк, типы и диапазоны, а не запрещает лишнее.

from __future__ import annotations

import datetime as _dt
import json

import pyarrow as pa
import pyarrow.parquet as pq

TIERS = ("K", "T", "R")

KINDS = (
    "person",
    "place",
    "polity_snapshot",
    "event",
    "artifact",
    "grid_layer",
    "source",
    # слой «где мы вообще находимся»: небо над головой и физика места
    "sky_object",     # звезда, планета, спутник, линия созвездия
    "constant",       # измеренная величина мира (радиус Земли, R₀ Галактики…)
    "timeseries",     # ряд по времени (эксцентриситет орбиты, наклон оси…)
    "taxon",          # вид/род живого: кто вообще населяет эту планету
)

# Обязательные поля провенанса (у всех видов).
PROVENANCE_FIELDS = ("source", "license", "tier", "retrieved")

# Обязательные содержательные поля по видам (сверх провенанса).
# lat/lon допускают null (не всё локализовано), но колонки обязаны быть там,
# где перечислены.
KIND_REQUIRED = {
    "person": ("id", "name"),
    "place": ("id", "name", "lat", "lon"),
    "polity_snapshot": ("polity_id", "year"),
    "event": ("id", "name", "year_start"),
    "artifact": ("id", "title"),
    "grid_layer": ("layer", "year", "lon", "lat", "value"),
    "source": ("id", "url"),
    "sky_object": ("id", "kind_of", "name"),
    "constant": ("id", "name", "value", "unit"),
    "timeseries": ("series", "t", "value"),
    "taxon": ("id", "name", "rank"),
}

# Поля, которые при наличии обязаны быть числовыми и в диапазоне.
_RANGE_CHECKS = {
    "lat": (-90.0, 90.0),
    "lon": (-180.0, 180.0),
}

# Ключ метаданных parquet, куда пишем вид записи.
META_KIND_KEY = b"terra_atlas_kind"


def today() -> str:
    """Дата 'получено' в ISO."""
    return _dt.date.today().isoformat()


def base_record(kind: str, source: str, license: str, tier: str) -> dict:
    """Каркас записи с провенансом; содержательные поля добавляет вызывающий."""
    if kind not in KINDS:
        raise ValueError(f"неизвестный kind: {kind}")
    if tier not in TIERS:
        raise ValueError(f"неизвестный tier: {tier}")
    return {
        "source": source,
        "license": license,
        "tier": tier,
        "retrieved": today(),
    }


def validate_record(kind: str, rec: dict) -> list[str]:
    """Проверка одной записи; возвращает список ошибок (пустой = ок)."""
    errors: list[str] = []
    if kind not in KINDS:
        return [f"неизвестный kind: {kind}"]
    for f in PROVENANCE_FIELDS:
        v = rec.get(f)
        if v is None or v == "":
            errors.append(f"пустое обязательное поле провенанса: {f}")
    if rec.get("tier") not in TIERS:
        errors.append(f"tier должен быть одним из {TIERS}, а не {rec.get('tier')!r}")
    for f in KIND_REQUIRED[kind]:
        if f not in rec:
            errors.append(f"нет обязательного поля {f} для kind={kind}")
        elif rec[f] is None and f not in ("lat", "lon"):
            errors.append(f"обязательное поле {f} = null для kind={kind}")
    for f, (lo, hi) in _RANGE_CHECKS.items():
        v = rec.get(f)
        if v is not None and f in rec:
            try:
                x = float(v)
                if not (lo <= x <= hi):
                    errors.append(f"{f}={x} вне диапазона [{lo}, {hi}]")
            except (TypeError, ValueError):
                errors.append(f"{f}={v!r} не число")
    return errors


def records_to_table(kind: str, records: list[dict]) -> pa.Table:
    """Список dict-записей -> pyarrow.Table с меткой kind в метаданных.

    Схему выводит pyarrow; None-значения дают nullable-колонки.
    Все записи обязаны иметь одинаковый набор ключей (нормализация — забота
    источника), иначе pyarrow сам поднимет ошибку.
    """
    if not records:
        raise ValueError("пустой список записей")
    tbl = pa.Table.from_pylist(records)
    meta = dict(tbl.schema.metadata or {})
    meta[META_KIND_KEY] = kind.encode()
    return tbl.replace_schema_metadata(meta)


def table_kind(tbl_or_schema) -> str | None:
    """Читает kind из метаданных таблицы/схемы parquet."""
    schema = getattr(tbl_or_schema, "schema", tbl_or_schema)
    meta = schema.metadata or {}
    v = meta.get(META_KIND_KEY)
    return v.decode() if v else None


def validate_table(path: str, sample_rows: int = 2000) -> list[str]:
    """Проверка parquet-файла склада: kind, обязательные колонки, ярусы,
    null-ы в обязательных полях, диапазоны координат. Возвращает ошибки."""
    errors: list[str] = []
    try:
        pf = pq.ParquetFile(path)
    except Exception as e:  # битый файл
        return [f"не читается parquet: {e}"]
    schema = pf.schema_arrow
    kind = table_kind(schema)
    if kind is None:
        return [f"нет метаданных {META_KIND_KEY.decode()} в {path}"]
    if kind not in KINDS:
        return [f"неизвестный kind в метаданных: {kind}"]
    cols = set(schema.names)
    for f in PROVENANCE_FIELDS + KIND_REQUIRED[kind]:
        if f not in cols:
            errors.append(f"нет колонки {f} (kind={kind})")
    if errors:
        return errors

    # Колоночные проверки по всему файлу (дёшево на parquet).
    import pyarrow.compute as pc

    tbl = pf.read(columns=list(
        {"tier", "source", "license", "retrieved"}
        | set(KIND_REQUIRED[kind]) & {"lat", "lon"}
    ))
    tiers = pc.unique(tbl.column("tier")).to_pylist()
    bad_tiers = [t for t in tiers if t not in TIERS]
    if bad_tiers:
        errors.append(f"недопустимые tier: {bad_tiers}")
    for f in ("source", "license", "retrieved"):
        n_null = tbl.column(f).null_count
        if n_null:
            errors.append(f"{n_null} null в колонке {f}")
    for f, (lo, hi) in _RANGE_CHECKS.items():
        if f in tbl.column_names:
            col = pc.drop_null(tbl.column(f))
            if len(col):
                mn = pc.min(col).as_py()
                mx = pc.max(col).as_py()
                if mn < lo or mx > hi:
                    errors.append(f"{f} вне [{lo},{hi}]: min={mn}, max={mx}")

    # Построчная проверка образца (ловит null в обязательных не-гео полях).
    head = pf.read_row_group(0) if pf.num_row_groups else None
    if head is not None:
        for rec in head.slice(0, sample_rows).to_pylist():
            errs = validate_record(kind, rec)
            if errs:
                errors.append(f"пример плохой записи: {errs[:3]}")
                break
    return errors


def example_records(path: str, n: int = 2) -> list[dict]:
    """Первые n записей файла для сводок doctor'а."""
    pf = pq.ParquetFile(path)
    batch = next(pf.iter_batches(batch_size=n))
    out = []
    for rec in batch.to_pylist():
        # Обрезаем длинные строки, чтобы сводка оставалась читаемой.
        out.append({
            k: (v[:80] + "…" if isinstance(v, str) and len(v) > 80 else v)
            for k, v in rec.items()
        })
    return out


if __name__ == "__main__":
    # Мини-самопроверка схемы.
    rec = base_record("place", "https://pleiades.stoa.org/places/912985", "CC-BY-3.0", "K")
    rec.update({"id": "pleiades:912985", "name": "Ur", "lat": 30.96, "lon": 46.10})
    errs = validate_record("place", rec)
    print("ошибки:", errs or "нет")
    print(json.dumps(rec, ensure_ascii=False))
