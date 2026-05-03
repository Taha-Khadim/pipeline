#!/bin/bash
# Verify the new fixes:
#   1. discover skips leads without contact info
#   2. lead PUT updates status correctly
#   3. lead DELETE removes the row
#   4. /leads/api/list filters by has_phone / has_email / has_website
#   5. outreach /api/generate fails fast with clear error if no API key
set -e
cd /home/taha/Portfolio/pipeline
pkill -9 -f "uvicorn.*8765" 2>/dev/null || true
sleep 1
# shellcheck source=/dev/null
source venv/bin/activate

# Use a fresh data dir so we don't pollute the user's real DB.
TEST_DATA=/home/taha/Portfolio/pipeline/build/.test-data
rm -rf "$TEST_DATA"
mkdir -p "$TEST_DATA"
LOG=/home/taha/Portfolio/pipeline/build/.fixes.log
rm -f "$LOG"
LUMORA_DATA_DIR="$TEST_DATA" GOOGLE_API_KEY="" \
    python -m uvicorn app.main:app --port 8765 >"$LOG" 2>&1 &
SVR_PID=$!
echo "Server PID: $SVR_PID"

for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    if curl -s -o /dev/null -w "" http://127.0.0.1:8765/; then
        echo "Server up after ${i}s"; break
    fi
done

echo
echo "=== 1. Run a tiny scrape to populate leads (OSM only — fast) ==="
curl -s -X POST http://127.0.0.1:8765/discover/start \
    -H "Content-Type: application/json" \
    -d '{"industry":"Dentist","city":"London","country":"United Kingdom","sources":["openstreetmap"]}'
echo
sleep 2
JOB_ID=$(curl -s http://127.0.0.1:8765/discover/recent-jobs | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
for i in $(seq 1 30); do
    sleep 2
    R=$(curl -s "http://127.0.0.1:8765/discover/job/$JOB_ID")
    if echo "$R" | grep -q '"COMPLETED"'; then break; fi
    if echo "$R" | grep -q '"FAILED"'; then break; fi
done
echo "Job done: $(echo "$R" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d['status'], 'count:', d['results_count'])")"

echo
echo "=== 2. Confirm only contactable leads were saved ==="
TOTAL=$(curl -s http://127.0.0.1:8765/leads/api/list?limit=2000 | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
NO_CONTACT=$(curl -s http://127.0.0.1:8765/leads/api/list?limit=2000 | python3 -c "
import sys, json
d = json.load(sys.stdin)
n = 0
for l in d:
    if not l.get('phone') and not (l.get('emails') or []) and not l.get('website_url'):
        n += 1
print(n)
")
echo "  total leads: $TOTAL, leads without any contact: $NO_CONTACT (must be 0)"

echo
echo "=== 3. has_phone / has_email / has_website filters ==="
PH=$(curl -s 'http://127.0.0.1:8765/leads/api/list?has_phone=true&limit=2000' | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
EM=$(curl -s 'http://127.0.0.1:8765/leads/api/list?has_email=true&limit=2000' | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
WB=$(curl -s 'http://127.0.0.1:8765/leads/api/list?has_website=true&limit=2000' | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
NW=$(curl -s 'http://127.0.0.1:8765/leads/api/list?has_website=false&limit=2000' | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
EM_NS=$(curl -s 'http://127.0.0.1:8765/leads/api/list?has_email=true&has_website=false&limit=2000' | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
PH_NS=$(curl -s 'http://127.0.0.1:8765/leads/api/list?has_phone=true&has_website=false&limit=2000' | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
echo "  has_phone=true:   $PH"
echo "  has_email=true:   $EM"
echo "  has_website=true: $WB"
echo "  has_website=false:$NW"
echo "  email + no site:  $EM_NS"
echo "  phone + no site:  $PH_NS"

LEAD_ID=$(curl -s http://127.0.0.1:8765/leads/api/list?limit=1 | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")

echo
echo "=== 4. PUT status update ==="
BEFORE=$(curl -s "http://127.0.0.1:8765/leads/api/$LEAD_ID" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
RES=$(curl -s -X PUT "http://127.0.0.1:8765/leads/api/$LEAD_ID" -H "Content-Type: application/json" -d '{"status":"RESEARCHED"}')
AFTER=$(curl -s "http://127.0.0.1:8765/leads/api/$LEAD_ID" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
echo "  PUT response: $RES"
echo "  before=$BEFORE  after=$AFTER  (expected RESEARCHED)"

echo
echo "=== 5. PUT invalid status returns 400 ==="
BAD=$(curl -s -o /dev/null -w "%{http_code}" -X PUT "http://127.0.0.1:8765/leads/api/$LEAD_ID" -H "Content-Type: application/json" -d '{"status":"NOT_A_REAL_STATUS"}')
echo "  HTTP $BAD (expected 400)"

echo
echo "=== 6. DELETE single lead ==="
DEL=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "http://127.0.0.1:8765/leads/api/$LEAD_ID")
GONE=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8765/leads/api/$LEAD_ID")
echo "  DELETE: HTTP $DEL (expected 200), GET after delete: HTTP $GONE (expected 404)"

echo
echo "=== 7. Bulk delete ==="
IDS=$(curl -s http://127.0.0.1:8765/leads/api/list?limit=3 | python3 -c "import sys,json;print(json.dumps([l['id'] for l in json.load(sys.stdin)]))")
echo "  deleting: $IDS"
BD=$(curl -s -X POST http://127.0.0.1:8765/leads/api/bulk-delete -H "Content-Type: application/json" -d "{\"lead_ids\": $IDS}")
echo "  response: $BD"

echo
echo "=== 8. Outreach without API key ==="
ANY_LEAD=$(curl -s http://127.0.0.1:8765/leads/api/list?limit=1 | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['id'] if d else 0)")
if [ "$ANY_LEAD" != "0" ]; then
    OUT=$(curl -s -o /dev/null -w "%{http_code}" -X POST http://127.0.0.1:8765/outreach/api/generate -H "Content-Type: application/json" -d "{\"lead_id\": $ANY_LEAD, \"type\": \"email\", \"context\": \"They're losing customers because they have no website.\"}")
    BODY=$(curl -s -X POST http://127.0.0.1:8765/outreach/api/generate -H "Content-Type: application/json" -d "{\"lead_id\": $ANY_LEAD, \"type\": \"email\", \"context\": \"They're losing customers because they have no website.\"}")
    echo "  HTTP $OUT (expected 400 — no key set)"
    echo "  body: $BODY"
fi

echo
echo "=== Server log (errors only) ==="
grep -E "(ERROR|Traceback|app.routers.discover|skipped)" "$LOG" | tail -20

kill $SVR_PID 2>/dev/null || true
wait $SVR_PID 2>/dev/null || true
echo done
