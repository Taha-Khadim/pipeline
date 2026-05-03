#!/bin/bash
set -e
ROOT=/home/taha/Portfolio/pipeline
DEB="$ROOT/build/dist/lumora-pipeline_1.0.1_amd64.deb"
TEST="$ROOT/build/test-bundle"

echo "==> extracting bundle"
rm -rf "$TEST"
mkdir -p "$TEST"
dpkg-deb -x "$DEB" "$TEST/extracted"

PORT=8781
LOG="$TEST/server.log"
DATA="$TEST/data"
mkdir -p "$DATA"

echo "==> starting bundled binary"
PLAYWRIGHT_BROWSERS_PATH="$TEST/extracted/opt/lumora-pipeline/ms-playwright" \
LUMORA_DATA_DIR="$DATA" \
LUMORA_SKIP_PLAYWRIGHT_INSTALL=1 \
"$TEST/extracted/opt/lumora-pipeline/lumora-pipeline" --no-browser --port $PORT >"$LOG" 2>&1 &
SVR_PID=$!
echo "PID $SVR_PID"

for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 1
  if curl -s -o /dev/null -w "" "http://127.0.0.1:$PORT/"; then
    echo "  up after ${i}s"; break
  fi
done

echo "==> firing scrape"
curl -s -X POST "http://127.0.0.1:$PORT/discover/start" \
  -H "Content-Type: application/json" \
  -d '{"industry":"Salon","city":"Mumbai","country":"India","sources":["openstreetmap","google_maps","yelp"]}'
echo

sleep 2
JOB_ID=$(curl -s "http://127.0.0.1:$PORT/discover/recent-jobs" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
echo "Tracking job: $JOB_ID"

for i in $(seq 1 30); do
  sleep 6
  R=$(curl -s "http://127.0.0.1:$PORT/discover/job/$JOB_ID")
  ST=$(echo "$R" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'],'count:',d['results_count'],'leads:',len(d['leads']))")
  echo "  $i: $ST"
  echo "$R" | grep -q '"COMPLETED"' && break
  echo "$R" | grep -q '"FAILED"' && break
done

echo "==> FINAL"
curl -s "http://127.0.0.1:$PORT/discover/job/$JOB_ID" | python3 -c "
import sys, json, collections
d = json.load(sys.stdin)
print(f'Status: {d[\"status\"]}, count: {d[\"results_count\"]}, leads: {len(d[\"leads\"])}')
src = collections.Counter()
ph=we=0
for l in d['leads']:
    src[(l.get('source','') or '').split(':')[0]] += 1
    if l.get('phone'): ph+=1
    if l.get('has_website'): we+=1
print(f'  sources: {dict(src)}')
print(f'  with phone:   {ph}/{len(d[\"leads\"])}')
print(f'  with website: {we}/{len(d[\"leads\"])}')
"

echo "==> server log tail"
tail -25 "$LOG"

kill $SVR_PID 2>/dev/null || true
wait $SVR_PID 2>/dev/null || true
echo "done"
