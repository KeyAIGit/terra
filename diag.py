import sys, time, collections, numpy as np
from terra.sim import Sim
from terra import knowledge as kn, society as so, agents as ag
s = Sim({"seed":1,"snapshot_every":10**9,"checkpoint_every":10**9})
s.seed_world()
t=time.time()
for k in range(int(sys.argv[1])): s.step()
alive=[p for p in s.polities.values() if p.dead is None]
print(f"год {s.year} за {time.time()-t:.0f}s, народов {len(alive)}, {sum(p.pop for p in alive)/1e6:.2f} млн")
cnt=collections.Counter()
for p in alive:
    for tid in np.flatnonzero(s.reps[p.pid].known): cnt[kn.CATALOG[tid].name]+=1
print("\nкто чем владеет (из %d народов):"%len(alive))
for n,c in cnt.most_common(30): print(f"   {c:4d}  {n}")
# лучший народ в зерновом очаге
best=None; bs=-1
for p in alive:
    cells=np.fromiter(p.cells,dtype=np.int64)
    g=float(s.world.biotic["wild_grains"].ravel()[cells].max())
    if g>bs: bs, best = g, p
p=best; rep=s.reps[p.pid]; cells=np.fromiter(p.cells,dtype=np.int64)
ts=so.tech_scale(p,s.settlements)
print(f"\nлучший зерновой народ: {p.name}  pop={int(p.pop)} grains={bs:.2f} mode={p.subsistence}")
print(f"   surplus={p.surplus:.3f} tech_scale={ts:.0f} знаний={rep.count()}")
aff=rep.affordances()
print("   аффордансы:", {a:round(float(v),2) for a,v in zip(kn.AFFORDANCES,aff) if v>0})
mats=so.materials_vec(s.matfield,p)
m=kn.reachable_mask(rep,mats,ts,p.surplus,float(so.MODE_SED[so.MODE_I[p.subsistence]]),so.biomes_of(s.clim(),p))
print("   достижимо сейчас:", [kn.CATALOG[t].name for t in np.flatnonzero(m)])
for key in ("sedentism","wild_harvest","quern","cultivation","smoke_dry","pit_store","basket"):
    tt=kn.BY_KEY[key]
    why=[]
    if not (tt.needs_aff and all(aff[kn.AFF_IDX[a]]>=v for a,v in tt.needs_aff.items())) and tt.needs_aff:
        why.append("аффордансы "+str({a:(round(float(aff[kn.AFF_IDX[a]]),2),v) for a,v in tt.needs_aff.items() if aff[kn.AFF_IDX[a]]<v}))
    for mk,mv in tt.needs_mat.items():
        if mats[kn.MAT_KEYS.index(mk)]<mv: why.append(f"{mk}<{mv}")
    if ts<tt.needs_pop: why.append(f"масштаб {ts:.0f}<{tt.needs_pop}")
    if p.surplus<tt.needs_surplus: why.append(f"избыток<{tt.needs_surplus}")
    if float(so.MODE_SED[so.MODE_I[p.subsistence]])<tt.needs_sedentism: why.append(f"оседлость<{tt.needs_sedentism}")
    print(f"   {tt.name:26s} {'ЕСТЬ' if rep.known[tt.tid] else ('доступно' if not why else 'нет: '+', '.join(why))}")
co=s.co; idx=co.live_idx()
c=np.bincount(co.last_act[idx],minlength=ag.N_ACT)/idx.size
print("\nдействия:", {a:round(float(v),3) for a,v in sorted(zip(ag.ACTIONS,c),key=lambda t:-t[1])[:6]})
print("средний surplus:", round(float(np.mean([p.surplus for p in alive])),4),
      " food_ratio-прокси K/pop:", round(float(np.mean([so.capacity(s.world,s.grid,s.clim(),p,s.reps[p.pid])/max(p.pop,1) for p in alive])),2))
