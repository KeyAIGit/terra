"""
Двухпроходный протокол оракула: за ключевых людей мира думает внешний разум.

Развилки в TERRA детерминированы: у каждой устойчивый идентификатор `jid`,
зависящий только от сида, года, вида развилки, народа и человека. Поэтому
можно прогнать отрезок истории дважды:

  проход 1 — мир выкладывает развилки в oracle/pending.jsonl и решает их
             встроенной эвристикой, чтобы не останавливаться;
  между     — внешний разум (LLM) читает развилки и дописывает свои решения
             в oracle/resolved.jsonl;
  проход 2 — тот же отрезок прогоняется заново; развилки с теми же jid
             находят готовые ответы и мир идёт уже по ним.

    python3 oracle_demo.py collect <мир> --at -2000 --to -1700
    (внешний разум пишет ответы)
    python3 oracle_demo.py apply   <мир> --at -2000 --to -1700
    python3 oracle_demo.py diff    <мир-эвристика> <мир-оракул>
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from terra.cli import _ck_year, _load_run, _yr  # noqa: E402
from terra.sim import Sim  # noqa: E402


def _fork(run: str, at: int, to: int, name: str, resolver: str, budget: int):
    d, meta = _load_run(run)
    cks = sorted((d / "checkpoints").glob("ck_*.pkl.gz"), key=_ck_year)
    pick = min(cks, key=lambda p: abs(_ck_year(p) - at))
    over = {"run_id": name, "resolver": resolver, "resolver_budget": budget,
            "oracle_wait": 0.0, "year_end": to}
    s = Sim.restore(pick, d / "world", over, run_dir=Path("runs") / name, new_run_id=name)
    print(f"ветвление от {_yr(_ck_year(pick))} до {_yr(to)}, решатель: {resolver}")
    s.run(to, verbose=True)
    return s


def cmd_collect(a):
    s = _fork(a.run, a.at, a.to, a.name, "oracle", a.budget)
    p = s.dir / "oracle" / "pending.jsonl"
    n = sum(1 for _ in p.open(encoding="utf-8")) if p.exists() else 0
    print(f"\nразвилок выложено: {n}\n  {p}")
    print(f"ответы дописывать сюда: {s.dir / 'oracle' / 'resolved.jsonl'}")
    print('  формат строки: {"jid": "...", "choice": "...", "reasoning": "..."}')


def cmd_apply(a):
    s = _fork(a.run, a.at, a.to, a.name, "oracle", a.budget)
    print(f"\nрешено оракулом: {s.resolver.stats['oracle']}, "
          f"эвристикой: {s.resolver.stats['heuristic']}")
    return s


def cmd_diff(a):
    rows = []
    for r in (a.a, a.b):
        d, m = _load_run(r)
        tl = [json.loads(x) for x in (d / "timeline.jsonl").read_text(
            encoding="utf-8").splitlines() if x.strip()]
        rows.append((m, tl[-1] if tl else {}))
    print(f"{'':26s}{rows[0][0]['run_id'][:20]:>22s}{rows[1][0]['run_id'][:20]:>22s}")
    for k, label, f in (("pop", "людей", lambda v: f"{v/1e6:.2f} млн"),
                        ("polities", "народов", str),
                        ("tech_max", "знаний макс", str),
                        ("cities", "городов", str),
                        ("largest_city", "крупнейший город", lambda v: f"{int(v):,}".replace(",", " ")),
                        ("complexity", "сложность", lambda v: f"{v:.3f}"),
                        ("inequality", "неравенство", lambda v: f"{v:.3f}")):
        print(f"{label:26s}{f(rows[0][1].get(k, 0)):>22s}{f(rows[1][1].get(k, 0)):>22s}")
    for k, label in (("wars", "войн"), ("collapses", "обрушений"),
                     ("fissions", "расколов"), ("discoveries", "открытий")):
        print(f"{label:26s}{rows[0][0]['stats'].get(k, 0):>22d}{rows[1][0]['stats'].get(k, 0):>22d}")


def main():
    ap = argparse.ArgumentParser("oracle_demo")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c, f in (("collect", cmd_collect), ("apply", cmd_apply)):
        p = sub.add_parser(c)
        p.add_argument("run")
        p.add_argument("--at", type=int, required=True)
        p.add_argument("--to", type=int, required=True)
        p.add_argument("--name", required=True)
        p.add_argument("--budget", type=int, default=60)
        p.set_defaults(f=f)
    p = sub.add_parser("diff")
    p.add_argument("a")
    p.add_argument("b")
    p.set_defaults(f=cmd_diff)
    a = ap.parse_args()
    a.f(a)


if __name__ == "__main__":
    main()
