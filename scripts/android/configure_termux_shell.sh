#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
CONFIG_DIR="$HOME/.config/jarvis/android-mcp"
ENV_FILE="$CONFIG_DIR/server.env"
SERVICE_LINK="$PREFIX/var/service/jarvis-android-mcp"

ACTION="${1:-}"
case "$ACTION" in
  enable) VALUE=1 ;;
  disable) VALUE=0 ;;
  *)
    echo "Uso: bash scripts/android/configure_termux_shell.sh enable|disable" >&2
    exit 2
    ;;
esac

[ -f "$ENV_FILE" ] || {
  echo "[JARVIS-ANDROID-MCP] server.env ausente; instale primeiro o MCP Android." >&2
  exit 1
}

TEMP_FILE="$(mktemp "$CONFIG_DIR/.server.env.XXXXXX")"
trap 'rm -f "$TEMP_FILE"' EXIT
grep -v '^JARVIS_ANDROID_SHELL_ENABLED=' "$ENV_FILE" > "$TEMP_FILE" || true
printf 'JARVIS_ANDROID_SHELL_ENABLED=%s\n' "$VALUE" >> "$TEMP_FILE"
chmod 600 "$TEMP_FILE"
mv "$TEMP_FILE" "$ENV_FILE"
trap - EXIT

if ! command -v sv >/dev/null 2>&1; then
  echo "[JARVIS-ANDROID-MCP] configuração salva; sv não está disponível para reiniciar o serviço." >&2
  exit 1
fi

sv restart "$SERVICE_LINK"
echo "[JARVIS-ANDROID-MCP] execução Shell remota ${ACTION}."
