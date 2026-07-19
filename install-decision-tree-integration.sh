#!/usr/bin/env bash
set -euo pipefail

REPO="we6jbo/baypark-ollama-console"
BRANCH="main"
RAW="https://raw.githubusercontent.com/$REPO/$BRANCH"
PROJECT="/opt/baypark-ollama-console"
DT="/var/lib/dt-core"
QUEUE_DIR="/var/lib/baypark-decision-queue"
GROUP="baypark-bridge"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="/opt/baypark-integration-backups/$STAMP"
LOG="$PROJECT/decision-tree-integration-install.log"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

exec > >(tee -a "$LOG") 2>&1
printf '[%s] Starting GitHub Decision Tree integration update.\n' "$(date --iso-8601=seconds)"

for user in pi bayparkai; do
    id "$user" >/dev/null 2>&1 || { echo "Required user $user does not exist."; exit 1; }
done
for file in "$PROJECT/app.py" "$DT/main.py" "$DT/models.py"; do
    [[ -f "$file" ]] || { echo "Required file missing: $file"; exit 1; }
done

curl -fsSL "$RAW/app.py" -o "$TMP/app.py"
curl -fsSL "$RAW/dt-core/main.py" -o "$TMP/main.py"
curl -fsSL "$RAW/dt-core/human_queue.py" -o "$TMP/human_queue.py"
python3 -m py_compile "$TMP/app.py" "$TMP/main.py" "$TMP/human_queue.py"
grep -q "APP_VERSION = '7.609.0'" "$TMP/app.py" || { echo 'Unexpected app.py version.'; exit 1; }

mkdir -p "$BACKUP" "$QUEUE_DIR"
cp -a "$PROJECT/app.py" "$BACKUP/app.py.before"
cp -a "$DT/main.py" "$BACKUP/main.py.before"
[[ -f "$DT/human_queue.py" ]] && cp -a "$DT/human_queue.py" "$BACKUP/human_queue.py.before" || true

getent group "$GROUP" >/dev/null || groupadd --system "$GROUP"
usermod -aG "$GROUP" pi
usermod -aG "$GROUP" bayparkai
chown pi:"$GROUP" "$QUEUE_DIR"
chmod 2770 "$QUEUE_DIR"

install -o bayparkai -g bayparkai -m 0644 "$TMP/app.py" "$PROJECT/app.py"
install -o pi -g pi -m 0644 "$TMP/main.py" "$DT/main.py"
install -o pi -g pi -m 0644 "$TMP/human_queue.py" "$DT/human_queue.py"

runuser -u pi -- env PYTHONPATH="$DT" python3 -c 'from human_queue import connect; c=connect(); c.execute("SELECT 1"); c.close(); print("Decision queue database initialized.")'
chown -R pi:"$GROUP" "$QUEUE_DIR"
find "$QUEUE_DIR" -type d -exec chmod 2770 {} +
find "$QUEUE_DIR" -type f -exec chmod 0660 {} +

mkdir -p "$PROJECT/update-backups"
chown -R bayparkai:bayparkai "$PROJECT/update-backups"
chmod 0755 "$PROJECT/update-backups"
chown bayparkai:bayparkai "$PROJECT/app.py"
chmod 0644 "$PROJECT/app.py"

systemctl restart dt-core.service
BAYPARK_UNIT="$(systemctl list-units --type=service --all --no-legend | awk '/baypark.*console|baypark.*ollama/ {print $1; exit}')"
if [[ -n "$BAYPARK_UNIT" ]]; then
    systemctl restart "$BAYPARK_UNIT"
else
    PID="$(pgrep -f '^/usr/bin/python3 /opt/baypark-ollama-console/app.py$' | head -n1 || true)"
    [[ -n "$PID" ]] && kill "$PID" || true
fi

sleep 3
runuser -u pi -- touch "$QUEUE_DIR/.pi-write-test"
runuser -u bayparkai -- touch "$QUEUE_DIR/.bayparkai-write-test"
rm -f "$QUEUE_DIR/.pi-write-test" "$QUEUE_DIR/.bayparkai-write-test"

printf '[%s] Installation completed. Backups: %s\n' "$(date --iso-8601=seconds)" "$BACKUP"
echo 'Network Assistant version 7.609.0 installed.'
echo 'New commands: pending questions; open question NUMBER; answer question NUMBER ANSWER; decision queue status; decision tree update help'
