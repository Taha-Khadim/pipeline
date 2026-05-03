#!/bin/bash
# End-to-end smoke test of the discover pipeline.
set -e

cd /home/taha/Portfolio/pipeline
pkill -9 -f "uvicorn.*8765" 2>/dev/null || true
sleep 1

# shellcheck source=/dev/null
source venv/bin/activate

LOG=/home/taha/Portfolio/pipeline/build/.e2e.log
rm -f "$LOG"
python -m uvicorn app.main:app --port 8765 >"$LOG" 2>&1 &
SVR_PID=$!
echo "Server PID: $SVR_PID"

for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    if curl -s -o /dev/null -w "" http://127.0.0.1:8765/discover; then
        echo "Server up after ${i}s"
        break
    fi
done

curl -s -X POST http://127.0.0.1:8765/discover/start \
    -H "Content-Type: application/json" \
    -d '{"industry":"Dentist","city":"London","country":"United Kingdom","sources":["openstreetmap","google_maps","yelp"]}'
echo

# Find the actual job id (might not be 1 if previous runs created jobs)
sleep 2
JOB_ID=$(curl -s "http://127.0.0.1:8765/discover/recent-jobs" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
echo "Tracking job: $JOB_ID"

for i in $(seq 1 25); do
    sleep 6
    R=$(curl -s "http://127.0.0.1:8765/discover/job/$JOB_ID")
    STATUS=$(echo "$R" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
    COUNT=$(echo "$R" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['results_count'],len(d['leads']))")
    echo "  poll $i: status=$STATUS count=$COUNT"
    if [ "$STATUS" = "COMPLETED" ] || [ "$STATUS" = "FAILED" ]; then
        break
    fi
done

echo "--- FINAL ---"
curl -s "http://127.0.0.1:8765/discover/job/$JOB_ID" | python3 -c "
import sys, json, collections
d = json.load(sys.stdin)
print(f'Status: {d[\"status\"]}, count: {d[\"results_count\"]}, leads: {len(d[\"leads\"])}')
sources = collections.Counter()
phones = 0; webs = 0
for l in d['leads']:
    sources[(l.get('source','') or '').split(':')[0]] += 1
    if l.get('phone'): phones += 1
    if l.get('has_website'): webs += 1
print(f'  sources: {dict(sources)}')
print(f'  with phone: {phones}/{len(d[\"leads\"])}')
print(f'  with website: {webs}/{len(d[\"leads\"])}')
for l in d['leads'][:8]:
    name = l['business_name'][:34]
    ph = (l.get('phone') or '-')[:20]
    src = (l.get('source','') or '').split(':')[0]
    print(f'  [{src:<14}] {name:<34} ph={ph:<20} web={l.get(\"has_website\")}')
"

echo "--- log tail ---"
tail -40 "$LOG"

kill $SVR_PID 2>/dev/null || true
wait $SVR_PID 2>/dev/null || true
echo "done"
