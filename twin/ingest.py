# Драйвер сбора твина: python3 -m twin.ingest --budget 1500 [--source X]
# Логика — как atlas.ingest: бюджет времени, стоп по диску, резюмируемость
# через twin/data/manifest.json.

from __future__ import annotations

import argparse
import sys
import time
import traceback

from twin.sources import REGISTRY, BY_NAME, common
from twin.state import Manifest, disk_free_gb


def run(budget: float, only: str | None = None) -> int:
    man = Manifest()
    deadline = time.monotonic() + budget
    ctx = common.Ctx(man, deadline)
    todo = [BY_NAME[only]] if only else REGISTRY
    if only and only not in BY_NAME:
        print(f"нет источника {only}; есть: {', '.join(BY_NAME)}")
        return 2

    print(f"twin.ingest: бюджет {budget:.0f}с, диск свободен {disk_free_gb():.1f} ГБ")
    stopped = None
    for mod in todo:
        name = mod.NAME
        st = man.src(name)["status"]
        if st == "done" and not only and name not in ("weather", "live"):
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
        except Exception as e:
            man.set_status(name, "failed", f"{type(e).__name__}: {e}")
            print(f"[x] {name}: failed — {e}")
            traceback.print_exc()

    print("— сводка —")
    for row in man.summary():
        print(f"  {row['source']:<10} {row['status']:<8} файлов {row['files']:<3} "
              f"строк {row['rows']:<8} {row['mb']} МБ"
              + (f"  ! {row['error']}" if row["error"] else ""))
    if stopped:
        print(f"остановлено: {stopped}; повторный запуск продолжит с места обрыва")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Сбор данных твина")
    ap.add_argument("--budget", type=float, default=1500.0,
                    help="бюджет времени, секунд (по умолчанию 1500)")
    ap.add_argument("--source", default=None, help="только один источник")
    args = ap.parse_args()
    return run(args.budget, args.source)


if __name__ == "__main__":
    sys.exit(main())
