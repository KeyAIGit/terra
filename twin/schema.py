# Схема записей твина. Наследует дисциплину атласа (atlas/schema.py):
# у каждой записи провенанс source/license/tier/retrieved; данные настоящего
# из первоисточников — ярус K. Свои виды записей:
#   feature — векторный объект (здание, дорога, вода, парк, POI, округ);
#             геометрия — GeoJSON-строка, плюс bbox и представительная точка
#   grid    — описание растрового артефакта (npz рядом в data/), сам растр
#             в parquet не кладём
#   obs     — наблюдение сенсора/погоды (station, t, var, value, unit)

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq

from atlas.schema import PROVENANCE_FIELDS, TIERS, base_record as _base, today  # noqa: F401

KINDS = ("feature", "grid", "obs")

KIND_REQUIRED = {
    "feature": ("id", "fclass", "geometry", "lat", "lon",
                "lat_min", "lon_min", "lat_max", "lon_max"),
    "grid": ("id", "layer", "path", "lat_min", "lon_min", "lat_max", "lon_max",
             "rows", "cols", "unit"),
    "obs": ("id", "station", "t", "var", "value", "unit"),
}

_RANGE = {"lat": (-90.0, 90.0), "lon": (-180.0, 180.0),
          "lat_min": (-90.0, 90.0), "lat_max": (-90.0, 90.0),
          "lon_min": (-180.0, 180.0), "lon_max": (-180.0, 180.0)}

META_KIND_KEY = b"terra_twin_kind"


def base_record(kind: str, source: str, license: str, tier: str = "K") -> dict:
    if kind not in KINDS:
        raise ValueError(f"неизвестный kind твина: {kind}")
    if tier not in TIERS:
        raise ValueError(f"неизвестный tier: {tier}")
    rec = _base("place", source, license, tier)  # каркас провенанса атласа
    return {k: rec[k] for k in PROVENANCE_FIELDS}


def validate_record(kind: str, rec: dict) -> list[str]:
    errors: list[str] = []
    if kind not in KINDS:
        return [f"неизвестный kind: {kind}"]
    for f in PROVENANCE_FIELDS:
        if not rec.get(f):
            errors.append(f"пустое поле провенанса: {f}")
    if rec.get("tier") not in TIERS:
        errors.append(f"tier не из {TIERS}: {rec.get('tier')!r}")
    for f in KIND_REQUIRED[kind]:
        if f not in rec:
            errors.append(f"нет обязательного поля {f} (kind={kind})")
        elif rec[f] is None and f not in ("lat", "lon"):
            errors.append(f"обязательное поле {f} = null (kind={kind})")
    for f, (lo, hi) in _RANGE.items():
        v = rec.get(f)
        if v is not None and f in rec:
            try:
                x = float(v)
                if not (lo <= x <= hi):
                    errors.append(f"{f}={x} вне [{lo}, {hi}]")
            except (TypeError, ValueError):
                errors.append(f"{f}={v!r} не число")
    return errors


def records_to_table(kind: str, records: list[dict]) -> pa.Table:
    if not records:
        raise ValueError("пустой список записей")
    tbl = pa.Table.from_pylist(records)
    meta = dict(tbl.schema.metadata or {})
    meta[META_KIND_KEY] = kind.encode()
    return tbl.replace_schema_metadata(meta)


def table_kind(tbl_or_schema) -> str | None:
    schema = getattr(tbl_or_schema, "schema", tbl_or_schema)
    meta = schema.metadata or {}
    v = meta.get(META_KIND_KEY)
    return v.decode() if v else None


def validate_table(path: str, sample_rows: int = 2000) -> list[str]:
    """Проверка parquet-файла твина (по образцу atlas.schema.validate_table)."""
    errors: list[str] = []
    try:
        pf = pq.ParquetFile(path)
    except Exception as e:
        return [f"не читается parquet: {e}"]
    kind = table_kind(pf.schema_arrow)
    if kind is None:
        return [f"нет метаданных {META_KIND_KEY.decode()} в {path}"]
    if kind not in KINDS:
        return [f"неизвестный kind в метаданных: {kind}"]
    cols = set(pf.schema_arrow.names)
    for f in PROVENANCE_FIELDS + KIND_REQUIRED[kind]:
        if f not in cols:
            errors.append(f"нет колонки {f} (kind={kind})")
    if errors:
        return errors
    head = pf.read_row_group(0) if pf.num_row_groups else None
    if head is not None:
        for rec in head.slice(0, sample_rows).to_pylist():
            errs = validate_record(kind, rec)
            if errs:
                errors.append(f"пример плохой записи: {errs[:3]}")
                break
    return errors
