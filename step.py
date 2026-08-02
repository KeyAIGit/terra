"""Шаг мира вперёд короткими отрезками: контейнер не любит долгих фоновых процессов."""
import gzip, json, pickle, sys, time
from pathlib import Path
from terra.sim import Sim

name, target = sys.argv[1], int(sys.argv[2])
budget = float(sys.argv[3]) if len(sys.argv) > 3 else 480.0
d = Path("runs") / name
cks = sorted(d.glob("checkpoints/ck_*.pkl.gz"),
             key=lambda p: int(p.name.split("_", 1)[1].split(".", 1)[0]))
s = Sim.restore(cks[-1], d / "world", run_dir=d)
print(f"с {s.year} к {target}", flush=True)
t0 = time.time()
while s.year < target and time.time() - t0 < budget:
    s.step()
s.cfg["year_end"] = max(s.cfg.get("year_end", target), target)
s._snapshot(); s.checkpoint(); s.flush()
alive = [p for p in s.polities.values() if p.dead is None]
print(f"дошёл до {s.year} за {time.time()-t0:.0f} c | народов {len(alive)} | "
      f"{sum(p.pop for p in alive)/1e6:.1f} млн | знаний до "
      f"{max((s.reps[p.pid].count() for p in alive), default=0)}", flush=True)
print(json.dumps(s.stats, ensure_ascii=False), flush=True)
