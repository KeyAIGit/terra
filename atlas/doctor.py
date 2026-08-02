# Сводка и самопроверка склада: python3 -m atlas.doctor [--examples]
#
# По каждому источнику: статус из манифеста, число записей, размер,
# проверка схемы КАЖДОГО parquet (провенанс, ярусы, координаты),
# примеры записей. Ненулевой код выхода при ошибках схемы.

from __future__ import annotations

import argparse
import glob
import json
import os
import sys

import pyarrow.parquet as pq

from atlas import schema
from atlas.state import Manifest, DATA_DIR, disk_free_gb


def main() -> int:
    ap = argparse.ArgumentParser(description="Диагностика склада TERRA-Атласа")
    ap.add_argument("--examples", action="store_true",
                    help="печатать примеры записей каждого источника")
    args = ap.parse_args()

    man = Manifest()
    print("=== TERRA-Атлас: доктор склада ===")
    print(f"data: {DATA_DIR} (диск свободен {disk_free_gb():.1f} ГБ)\n")

    problems = 0
    grand_rows = 0
    grand_bytes = 0
    src_names = sorted(man.data.get("sources", {}).keys())
    for name in src_names:
        s = man.src(name)
        pdir = os.path.join(DATA_DIR, name)
        files = sorted(glob.glob(os.path.join(pdir, "*.parquet")))
        rows = 0
        size = 0
        kinds: dict[str, int] = {}
        errs_all: list[str] = []
        for fp in files:
            size += os.path.getsize(fp)
            try:
                pf = pq.ParquetFile(fp)
                n = pf.metadata.num_rows
                rows += n
                k = schema.table_kind(pf.schema_arrow) or "?"
                kinds[k] = kinds.get(k, 0) + n
            except Exception as e:
                errs_all.append(f"{os.path.basename(fp)}: не читается ({e})")
                continue
            errs = schema.validate_table(fp)
            for e in errs:
                errs_all.append(f"{os.path.basename(fp)}: {e}")
        grand_rows += rows
        grand_bytes += size
        kinds_s = ", ".join(f"{k}:{v}" for k, v in sorted(kinds.items()))
        print(f"[{s.get('status', '?'):>7}] {name:<16} "
              f"{rows:>9} записей  {size / 1e6:>8.1f} МБ  файлов {len(files):<3} ({kinds_s})")
        if s.get("error"):
            print(f"          причина: {s['error']}")
        if s.get("pending_urls"):
            print(f"          в очереди URL-ов: {len(s['pending_urls'])}")
        if errs_all:
            problems += len(errs_all)
            for e in errs_all[:4]:
                print(f"          СХЕМА: {e}")
            if len(errs_all) > 4:
                print(f"          … и ещё {len(errs_all) - 4}")
        if args.examples and files:
            try:
                for ex in schema.example_records(files[0], 1):
                    slim = {k: v for k, v in ex.items() if v is not None}
                    print("          пример: "
                          + json.dumps(slim, ensure_ascii=False)[:220])
            except Exception as e:
                print(f"          пример не читается: {e}")

    print(f"\nитого: {grand_rows} записей, {grand_bytes / 1e6:.1f} МБ "
          f"в {len(src_names)} источниках")
    if problems:
        print(f"ПРОБЛЕМ СХЕМЫ: {problems}")
        return 1
    print("схема: все parquet прошли проверку")
    return 0


if __name__ == "__main__":
    sys.exit(main())
