#!/bin/bash
# Контейнер убивает долгие фоновые процессы. Гоняем мир кусками,
# продолжая с последней точки сохранения, пока не дойдём до цели.
NAME=$1; TO=$2; SEED=${3:-1}
cd /home/claude/terra
if [ ! -f "runs/$NAME/run.json" ]; then
  python3 -u -m terra new --seed "$SEED" --to "$TO" --name "$NAME" --no-report >> "logs/$NAME.log" 2>&1
fi
for i in $(seq 1 40); do
  Y=$(python3 -c "import json;print(json.load(open('runs/$NAME/run.json'))['year'])" 2>/dev/null || echo -99999)
  if [ "$Y" -ge "$TO" ]; then echo "ГОТОВО: $NAME дошёл до $Y" >> "logs/$NAME.log"; break; fi
  echo "--- продолжаю с года $Y (попытка $i)" >> "logs/$NAME.log"
  python3 -u -m terra continue "$NAME" --to "$TO" >> "logs/$NAME.log" 2>&1
  # если run.json не обновился, восстановим его из точки сохранения
  python3 - "$NAME" <<'PY' >> "logs/$NAME.log" 2>&1
import gzip, pickle, json, sys
from pathlib import Path
d = Path("runs") / sys.argv[1]
cks = sorted(d.glob("checkpoints/ck_*.pkl.gz"), key=lambda p: int(p.name.split("_",1)[1].split(".",1)[0]))
if cks:
    with gzip.open(cks[-1], "rb") as f: st = pickle.load(f)
    cur = json.loads((d/"run.json").read_text()) if (d/"run.json").exists() else {}
    if cur.get("year", -10**9) < st["year"]:
        (d/"run.json").write_text(json.dumps({"run_id": st["run_id"], "config": st["cfg"],
            "year": st["year"], "stats": st["stats"],
            "resolver": {"heuristic": st["stats"]["junctures"]},
            "n_polities_ever": st["next_pid"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        print("run.json подтянут до", st["year"])
PY
done
