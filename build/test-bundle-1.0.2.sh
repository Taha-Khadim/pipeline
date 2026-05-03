#!/bin/bash
# Smoke-test the rebuilt 1.0.2 .deb against ALL the reported issues.
set -e
ROOT=/home/taha/Portfolio/pipeline
DEB="$ROOT/build/dist/lumora-pipeline_1.0.2_amd64.deb"
TEST="$ROOT/build/test-bundle"
GOOGLE_KEY="$(grep -E '^GOOGLE_API_KEY=' "$ROOT/.env" | cut -d= -f2)"

echo "==> extracting bundle"
rm -rf "$TEST"
mkdir -p "$TEST"
dpkg-deb -x "$DEB" "$TEST/extracted"

PORT=8782
LOG="$TEST/server.log"
DATA="$TEST/data"
mkdir -p "$DATA"

echo "==> starting bundled binary on :$PORT"
PLAYWRIGHT_BROWSERS_PATH="$TEST/extracted/opt/lumora-pipeline/ms-playwright" \
LUMORA_DATA_DIR="$DATA" \
LUMORA_SKIP_PLAYWRIGHT_INSTALL=1 \
GOOGLE_API_KEY="$GOOGLE_KEY" \
"$TEST/extracted/opt/lumora-pipeline/lumora-pipeline" --no-browser --port $PORT >"$LOG" 2>&1 &
SVR_PID=$!
echo "PID $SVR_PID"

for i in 1 2 3 4 5 6 7 8 9 10; do
    sleep 1
    if curl -s -o /dev/null -w "" "http://127.0.0.1:$PORT/"; then
        echo "  up after ${i}s"; break
    fi
done

echo
echo "[1] Pakistan is in countries list"
HAS_PK=$(curl -s "http://127.0.0.1:$PORT/discover/cities/Pakistan" | python3 -c "import sys,json;print(len(json.load(sys.stdin).get('cities', [])))")
echo "    Pakistan cities: $HAS_PK (expected > 20)"

echo
echo "[2] Discover with OSM only — fast and contactable-only"
curl -s -X POST "http://127.0.0.1:$PORT/discover/start" \
    -H "Content-Type: application/json" \
    -d '{"industry":"Dentist","city":"London","country":"United Kingdom","sources":["openstreetmap"]}' >/dev/null
sleep 2
JOB_ID=$(curl -s "http://127.0.0.1:$PORT/discover/recent-jobs" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")
for i in $(seq 1 20); do
    sleep 1
    R=$(curl -s "http://127.0.0.1:$PORT/discover/job/$JOB_ID")
    if echo "$R" | grep -qE '"COMPLETED"|"FAILED"'; then break; fi
done
TOTAL=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?limit=2000" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
NO_CONT=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?limit=2000" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(sum(1 for l in d if not l.get('phone') and not (l.get('emails') or []) and not l.get('website_url')))
")
echo "    saved: $TOTAL leads, without any contact info: $NO_CONT (must be 0)"

echo
echo "[3] Pipeline filters"
PH=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?has_phone=true&limit=2000" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
EM=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?has_email=true&limit=2000" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
EM_NS=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?has_email=true&has_website=false&limit=2000" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
PH_NS=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?has_phone=true&has_website=false&limit=2000" | python3 -c "import sys,json;print(len(json.load(sys.stdin)))")
echo "    has_phone=$PH  has_email=$EM  email+no-site=$EM_NS  phone+no-site=$PH_NS"

LEAD_ID=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?limit=1" | python3 -c "import sys,json;print(json.load(sys.stdin)[0]['id'])")

echo
echo "[4] Status update persists"
RES=$(curl -s -X PUT "http://127.0.0.1:$PORT/leads/api/$LEAD_ID" -H "Content-Type: application/json" -d '{"status":"CONTACTED"}')
AFTER=$(curl -s "http://127.0.0.1:$PORT/leads/api/$LEAD_ID" | python3 -c "import sys,json;print(json.load(sys.stdin)['status'])")
echo "    PUT response: $RES"
echo "    GET reads back: $AFTER (expected CONTACTED)"

echo
echo "[5] Single delete"
HC=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "http://127.0.0.1:$PORT/leads/api/$LEAD_ID")
HG=$(curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/leads/api/$LEAD_ID")
echo "    DELETE -> HTTP $HC, GET after delete -> HTTP $HG (expected 200, 404)"

echo
echo "[6] Bulk delete"
IDS=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?limit=3" | python3 -c "import sys,json;print(json.dumps([l['id'] for l in json.load(sys.stdin)]))")
BD=$(curl -s -X POST "http://127.0.0.1:$PORT/leads/api/bulk-delete" -H "Content-Type: application/json" -d "{\"lead_ids\": $IDS}")
echo "    bulk-delete response: $BD"

echo
echo "[7] Outreach email generation with Gemini"
ANY=$(curl -s "http://127.0.0.1:$PORT/leads/api/list?limit=1" | python3 -c "import sys,json;d=json.load(sys.stdin);print(d[0]['id'] if d else 0)")
if [ "$ANY" = "0" ]; then
    echo "    no leads left to test on (skipped)"
else
    OUT=$(curl -s -X POST "http://127.0.0.1:$PORT/outreach/api/generate" \
        -H "Content-Type: application/json" \
        -d "{\"lead_id\": $ANY, \"type\": \"email\", \"context\": \"They have great Google reviews but no website at all - patients searching them on Google find nothing.\"}")
    HAS_SUBJ=$(echo "$OUT" | python3 -c "import sys,json;d=json.load(sys.stdin);print('OK' if d.get('subject') and d.get('body') else 'FAIL: '+json.dumps(d)[:200])")
    MODEL=$(echo "$OUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('_model','?'))")
    SUBJ=$(echo "$OUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('subject',''))")
    BODY1=$(echo "$OUT" | python3 -c "import sys,json;print(json.load(sys.stdin).get('body','')[:140])")
    echo "    status: $HAS_SUBJ"
    echo "    model:   $MODEL"
    echo "    subject: $SUBJ"
    echo "    body:    $BODY1..."
fi

echo
echo "[8] Dashboard renders with clickable elements"
DASH_HTML=$(curl -s "http://127.0.0.1:$PORT/")
echo "$DASH_HTML" | grep -q 'href="/leads"' && echo "    Total Leads -> /leads OK" || echo "    Total Leads link MISSING"
echo "$DASH_HTML" | grep -q 'href="/leads?status=CONTACTED"' && echo "    Contacted -> /leads?status=CONTACTED OK" || echo "    Contacted link MISSING"
echo "$DASH_HTML" | grep -q 'href="/leads?status=CLOSED_WON"' && echo "    Clients Won -> /leads?status=CLOSED_WON OK" || echo "    Won link MISSING"
echo "$DASH_HTML" | grep -q 'href="/leads?status=FOUND"' && echo "    Funnel rows clickable OK" || echo "    Funnel rows MISSING"

echo
echo "==> server log tail"
tail -15 "$LOG"

kill $SVR_PID 2>/dev/null || true
wait $SVR_PID 2>/dev/null || true
echo done
