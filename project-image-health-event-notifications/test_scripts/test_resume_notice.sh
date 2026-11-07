#!/bin/sh
# Host test for image-health-resume-notice.conf. Runs stock Telegraf with
# both project configs and the scripted event_handler in test_files/, then
# checks the Logs-tab output for: two sent alarms, the pause, the resume
# with the held-back count, and the next alarm being sent again.
#
# Needs: telegraf on PATH. --non-strict-env-handling keeps the ${VAR:-default}
# lines working on Telegraf 1.38 and later. ntfy is pointed at a closed local port, so the
# http outputs log connection errors to stderr; that is expected here.
#
# Exit codes: 0 pass, 1 expected output missing or out of order,
# 2 telegraf not found.

set -eu

cd "$(dirname "$0")/.."
command -v telegraf >/dev/null 2>&1 || { echo "telegraf not found on PATH" >&2; exit 2; }

out=$(mktemp)
EXECUTABLES_DIR="$PWD/test_files" \
ALARM_QUIET_PERIOD=5s \
NOTIFY_MAX_BEFORE_PAUSE=2 \
NTFY_TOPIC_URL=http://127.0.0.1:9/ \
    telegraf --non-strict-env-handling \
             --config image-health-to-ntfy.conf \
             --config image-health-resume-notice.conf >"$out" 2>"$out.err" &
pid=$!
sleep 20
kill "$pid" 2>/dev/null || { echo "telegraf exited early:" >&2; cat "$out.err" >&2; exit 1; }
wait "$pid" 2>/dev/null || true

cat "$out"

# Each pattern must appear, in this order.
fail=0
pos=0
for want in \
    "activated (cause: Blocked, count: 1)" \
    "activated (cause: Blocked, count: 2)" \
    "Image health notifications paused" \
    "Image health notifications resumed" \
    "not sent: 2 activations" \
    "activated (cause: Blocked, count: 1)"; do
    line=$(awk -v start="$pos" -v want="$want" 'NR > start && index($0, want) { print NR; exit }' "$out")
    if [ -z "$line" ]; then
        echo "FAIL: missing after line $pos: $want" >&2
        fail=1
        break
    fi
    pos=$line
done

if grep -q "activated (cause: Blocked, count: [34])" "$out"; then
    echo "FAIL: a held-back alarm was sent" >&2
    fail=1
fi

rm -f "$out" "$out.err"
[ "$fail" -eq 0 ] && echo "PASS"
exit "$fail"
