import sys, time, collections
from terra.sim import Sim
n = int(sys.argv[1]) if len(sys.argv)>1 else 200
s = Sim({"seed":1,"snapshot_every":10**9,"checkpoint_every":10**9})
s.seed_world()
t=time.time(); mark=t
for k in range(n):
    s.step()
    if s.year % 1000 < 11 and time.time()-mark>0:
        alive=[p for p in s.polities.values() if p.dead is None]
        pop=sum(p.pop for p in alive)
        tc=sorted(s.reps[p.pid].count() for p in alive)
        md=collections.Counter(p.subsistence for p in alive).most_common(3)
        print(f"{s.year:>7} | народов {len(alive):3d} | {pop/1e6:8.2f} млн | знаний макс {tc[-1]:3d} мед {tc[len(tc)//2]:3d} | {md} | {time.time()-t:5.0f}s", flush=True)
        mark=time.time()
alive=[p for p in s.polities.values() if p.dead is None]
print("\nСТАТИСТИКА:", s.stats)
print("формы:", dict(collections.Counter(p.form for p in alive)))
print("\nЛЕТОПИСЬ (вес>=2.8):")
for e in [e for e in s.chronicle if e.weight>=2.8][:26]: print(f"  {e.year:>7} {e.kind:11s} {e.text[:100]}")
