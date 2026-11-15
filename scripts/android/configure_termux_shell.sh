#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
CONFIG_DIR="$HOME/.config/jarvis/android-mcp"
ENV_FILE="$CONFIG_DIR/server.env"
SERVICE_LINK="$PREFIX/var/service/jarvis-android-mcp"
TUNNEL_SERVICE_LINK="$PREFIX/var/service/jarvis-secure-mcp-tunnel"

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

# tunnel-client initializes an MCP session against this server. Restart the
# connected client as well so its upstream MCP catalog is discovered again.
if [ -L "$TUNNEL_SERVICE_LINK" ]; then
  if sv status "$TUNNEL_SERVICE_LINK" >/dev/null 2>&1; then
    sv restart "$TUNNEL_SERVICE_LINK"
    echo "[JARVIS-TUNNEL] cliente reiniciado para atualizar o catálogo de ferramentas MCP."
  else
    echo "[JARVIS-TUNNEL] serviço instalado, mas não estava ativo; inicie-o para atualizar o catálogo MCP."
  fi
else
  echo "[JARVIS-TUNNEL] serviço não instalado; não há cliente local para atualizar."
fi

echo "[JARVIS-ANDROID-MCP] execução Shell remota ${ACTION}."
