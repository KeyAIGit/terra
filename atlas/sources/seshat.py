# Seshat Global History Databank — переменные сложности политий по НГА.
#
# Прямая выгрузка seshatdatabank.info из контейнера недоступна, а поиск
# зеркал через api.github.com/search закрыт прокси (доступны только
# repo-scoped вызовы). Рабочее официальное зеркало найдено на Zenodo:
# «Seshat Data: Equinox Packaged Data» (MajidBenam/Equinox_data),
# https://doi.org/10.5281/zenodo.6629022 — упакованный релиз Equinox-2020.
# В архиве ОДИН XLSX (13 листов); главный лист Equinox2020_CanonDat —
# канонический экспорт фактов (NGA, Polity, Variable, Value/Date From/To),
# плюс справочники Polities (444 политии) и NGAs (35 точек с координатами).
# Лицензия: в архиве LICENSE = AGPL-3.0; сайт Seshat указывает для данных
# CC BY-NC-SA 4.0 — фиксируем обе, шиппить в игру без проверки нельзя.
# Ярус K: экспертно закодированные значения с источниками.

from __future__ import annotations

import zipfile

from atlas import schema
from atlas.sources import common

NAME = "seshat"
TITLE = "Seshat Databank: Equinox packaged data (Zenodo mirror)"
LICENSE = "AGPL-3.0 (LICENSE в архиве); сайт Seshat: CC-BY-NC-SA-4.0"
DOI = "https://doi.org/10.5281/zenodo.6629022"
ZIP_URL = ("https://zenodo.org/api/records/6629022/files/"
           "MajidBenam/Equinox_data-1.0.zip/content")


def _cell(v):
    """Ячейка pandas -> строка или None (NaN/пусто)."""
    if v is None:
        return None
    s = str(v).strip()
    if s in ("", "nan", "NaN", "None"):
        return None
    return s


def fetch(ctx: common.Ctx) -> dict:
    man = ctx.manifest
    out_dir = common.src_dir(NAME)

    try:
        import pandas as pd
        import openpyxl  # noqa: F401 — движок чтения xlsx
    except ImportError as e:
        man.set_status(NAME, "failed", f"нет движка xlsx: {e}")
        return {"status": "failed", "note": "pip install openpyxl"}

    need = [c for c in ("polities", "facts") if not man.chunk_done(NAME, c)]
    if need:
        ctx.check(90)
        raw = common.download(ctx, ZIP_URL, common.raw_path(NAME, "equinox.zip"))
        member = common.zip_member(raw, ".xlsx")
        with zipfile.ZipFile(raw) as z:
            xlsx_path = z.extract(member, common.raw_path(NAME, "x"))
        xl = pd.ExcelFile(xlsx_path)

        # координаты НГА — для привязки политий
        ngas = {}
        if "NGAs" in xl.sheet_names:
            for r in xl.parse("NGAs").to_dict("records"):
                ngas[_cell(r.get("NGA"))] = (
                    common.to_float(r.get("Latitude")),
                    common.to_float(r.get("Longitude")))

        if not man.chunk_done(NAME, "polities"):
            records = []
            for r in xl.parse("Polities").to_dict("records"):
                pid = _cell(r.get("PolID")) or _cell(r.get("PolName")) or "unknown"
                lat, lon = ngas.get(_cell(r.get("NGA")), (None, None))
                rec = schema.base_record("polity_snapshot", DOI, LICENSE, "K")
                rec.update({
                    "polity_id": f"seshat:{pid}",
                    "polity_name": _cell(r.get("PolName")),
                    "year": common.to_int(r.get("Start")) or 0,   # начало политии
                    "year_end": common.to_int(r.get("End")),
                    "nga": _cell(r.get("NGA")),
                    "world_region": _cell(r.get("World Region")),
                    "complexity": _cell(r.get("Complexity")),
                    "language": _cell(r.get("Language")),
                    "lat": lat, "lon": lon,
                })
                records.append(rec)
            paths, n = common.write_shards("polity_snapshot", records, out_dir,
                                           "polity_snapshot_polities")
            man.mark_chunk(NAME, "polities", rows=n, files=paths)
            print(f"    seshat: {n} политий")

        if not man.chunk_done(NAME, "facts"):
            ctx.check(60)
            # стартовые годы политий — фолбэк для фактов без Date.From
            start_of = {}
            for r in xl.parse("Polities").to_dict("records"):
                start_of[_cell(r.get("PolID"))] = common.to_int(r.get("Start"))
            records = []
            for r in xl.parse("Equinox2020_CanonDat").to_dict("records"):
                pol = _cell(r.get("Polity")) or "unknown"
                year = common.to_int(r.get("Date.From"))
                if year is None:
                    year = start_of.get(pol) or 0
                rec = schema.base_record("polity_snapshot", DOI, LICENSE, "K")
                rec.update({
                    "polity_id": f"seshat:{pol}",
                    "year": year,
                    "nga": _cell(r.get("NGA")),
                    "section": _cell(r.get("Section")),
                    "subsection": _cell(r.get("Subsection")),
                    "variable": _cell(r.get("Variable")),
                    "value_from": _cell(r.get("Value.From")),
                    "value_to": _cell(r.get("Value.To")),
                    "date_from": common.to_int(r.get("Date.From")),
                    "date_to": common.to_int(r.get("Date.To")),
                    "fact_type": _cell(r.get("Fact.Type")),
                    "value_note": _cell(r.get("Value.Note")),
                })
                records.append(rec)
            paths, n = common.write_shards("polity_snapshot", records, out_dir,
                                           "polity_snapshot_facts")
            man.mark_chunk(NAME, "facts", rows=n, files=paths,
                           note="лист Equinox2020_CanonDat")
            print(f"    seshat: {n} фактов Equinox")

    if not man.chunk_done(NAME, "srcrow"):
        paths = common.write_source_row(
            NAME, out_dir, DOI, LICENSE, TITLE,
            "Официальная упаковка Equinox-2020 (Zenodo-зеркало Seshat): "
            "444 политии (с координатами НГА) + 47 тыс. фактов переменных. "
            "ВНИМАНИЕ: лицензия небезусловная (AGPL в архиве / CC-BY-NC-SA "
            "по сайту) — не для прямого шиппинга в игру.")
        man.mark_chunk(NAME, "srcrow", rows=1, files=paths)

    common.drop_raw(NAME)
    return {"status": "done", "note": "Equinox-2020 из Zenodo-зеркала (xlsx)"}
