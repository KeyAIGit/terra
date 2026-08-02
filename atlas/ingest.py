# Драйвер сбора: python3 -m atlas.ingest --budget 1500 [--source X]
#
# Идёт по источникам реестра в порядке приоритета, пропуская done/failed.
# Соблюдает бюджет времени (контейнер убивает долгие процессы ~40 мин) и
# диск (стоп при < 8 ГБ свободного). Всё состояние — в manifest.json;
# повторный запуск продолжает с места обрыва.

from __future__ import annotations

import argparse
import sys
import time
import traceback

from atlas.sources import REGISTRY, BY_NAME, common
from atlas.state import Manifest, disk_free_gb


def run(budget: float, only: str | None = None) -> int:
    man = Manifest()
    deadline = time.monotonic() + budget
    ctx = common.Ctx(man, deadline)
    todo = [BY_NAME[only]] if only else REGISTRY
    if only and only not in BY_NAME:
        print(f"нет источника {only}; есть: {', '.join(BY_NAME)}")
        return 2

    print(f"ingest: бюджет {budget:.0f}с, диск свободен {disk_free_gb():.1f} ГБ")
    stopped = None
    for mod in todo:
        name = mod.NAME
        st = man.src(name)["status"]
        if st == "done" and not only:
            print(f"[=] {name}: уже done, пропуск")
            continue
        if st == "failed" and not only:
            print(f"[x] {name}: failed ({man.src(name)['error']}), пропуск "
                  f"(перезапуск: --source {name})")
            continue
        if ctx.time_left() < 60:
            stopped = "бюджет"
            break
        if disk_free_gb() < common.MIN_FREE_GB:
            stopped = "диск"
            break
        print(f"[>] {name} (осталось {ctx.time_left():.0f}с)")
        man.bump_attempt(name)
        try:
            res = mod.fetch(ctx)
            man.set_status(name, res.get("status", "done"),
                           None if res.get("status") == "done" else res.get("note"))
            print(f"[v] {name}: {res.get('status')} — {res.get('note', '')}")
        except common.BudgetExceeded as e:
            man.set_status(name, "partial", f"бюджет: {e}")
            print(f"[~] {name}: partial — {e}")
            stopped = "бюджет"
            break
        except common.DiskLow as e:
            man.set_status(name, "partial", f"диск: {e}")
            print(f"[~] {name}: стоп по диску — {e}")
            stopped = "диск"
            break
        except KeyboardInterrupt:
            man.set_status(name, "partial", "прерван вручную")
            raise
        except Exception as e:
            man.set_status(name, "failed", f"{type(e).__name__}: {str(e)[:300]}")
            print(f"[x] {name}: ОШИБКА — {e}")
            traceback.print_exc(limit=3)

    print("\n=== сводка склада ===")
    total_mb = 0.0
    for row in man.summary():
        total_mb += row["mb"]
        err = f"  // {row['error']}" if row.get("error") else ""
        print(f"  {row['source']:<16} {row['status']:<8} строк={row['rows']:<9} "
              f"файлов={row['files']:<3} {row['mb']:>8.1f} МБ{err}")
    print(f"  итого: {total_mb:.1f} МБ; диск свободен {disk_free_gb():.1f} ГБ")
    if stopped:
        print(f"  остановка: {stopped}; повторный запуск продолжит с этого места")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Сбор источников TERRA-Атласа")
    ap.add_argument("--budget", type=float, default=1500,
                    help="бюджет времени, сек (по умолчанию 1500)")
    ap.add_argument("--source", default=None,
                    help="только один источник (в т.ч. перезапуск failed)")
    args = ap.parse_args()
    return run(args.budget, args.source)


if __name__ == "__main__":
    sys.exit(main())
