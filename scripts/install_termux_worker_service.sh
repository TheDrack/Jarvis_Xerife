#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
HOME="${HOME:-/data/data/com.termux/files/home}"
SERVICE="$PREFIX/var/service/jarvis-agent-worker"
CONFIG="$HOME/.config/jarvis/agent-worker"
BOOT="$HOME/.termux/boot"

[ -x "$PREFIX/bin/sv" ] || { echo "Termux runit (sv) não está instalado." >&2; exit 1; }
[ -f "$ROOT/app/multiagent/worker_daemon.py" ] || { echo "Checkout inválido: worker_daemon.py ausente." >&2; exit 1; }

mkdir -p "$SERVICE" "$CONFIG" "$BOOT" "$HOME/jarvis-mobile/logs/agent-worker" "$HOME/jarvis-mobile/state"
touch "$SERVICE/down"
mkdir -p "$SERVICE/log"
install -m 755 "$ROOT/deploy/termux/runit/jarvis-agent-worker/run" "$SERVICE/run"
install -m 755 "$ROOT/deploy/termux/runit/jarvis-agent-worker/log/run" "$SERVICE/log/run"
install -m 755 "$ROOT/scripts/jarvis-worker" "$PREFIX/bin/jarvis-worker"
install -m 755 "$ROOT/deploy/termux/boot/10-jarvis-agent-worker.sh" "$BOOT/10-jarvis-agent-worker.sh"

if [ ! -f "$CONFIG/worker.env" ]; then
    install -m 600 "$ROOT/deploy/termux/worker.env.example" "$CONFIG/worker.env"
else
    chmod 600 "$CONFIG/worker.env"
fi

# Keep the service disabled until credentials are configured locally.
"$PREFIX/bin/sv" down "$SERVICE" >/dev/null 2>&1 || true

echo "Termux worker service installed."
echo "Service: $SERVICE (disabled until credentials are configured)"
echo "Config:  $CONFIG/worker.env (mode 600)"
echo "Control: jarvis-worker {configure|start|stop|restart|status|logs}"
echo "Boot:    $BOOT/10-jarvis-agent-worker.sh"
