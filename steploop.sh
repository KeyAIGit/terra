#!/bin/bash
# Доводка мира кусками step.py: чекпоинт на каждом выходе по бюджету.
NAME=$1; TO=$2
cd /root/terra
for i in $(seq 1 60); do
  Y=$(python3 -c "import json;print(json.load(open('runs/$NAME/run.json'))['year'])" 2>/dev/null || echo -99999)
  if [ "$Y" -ge "$TO" ]; then echo "ГОТОВО: $NAME дошёл до $Y" >> "logs/$NAME.log"; break; fi
  python3 -u step.py "$NAME" "$TO" 480 >> "logs/$NAME.log" 2>&1
done
