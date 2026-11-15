#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

APP_ROOT="$HOME/.local/opt/jarvis-tunnel"
CLIENT="$APP_ROOT/bin/tunnel-client"
CONFIG_DIR="$HOME/.config/jarvis/tunnel"
ENV_FILE="$CONFIG_DIR/tunnel.env"
SECRET_FILE="$CONFIG_DIR/runtime-key"
PROFILE_NAME="jarvis-android"

[ -x "$CLIENT" ] || { echo "Execute install_secure_mcp_tunnel.sh primeiro." >&2; exit 1; }
[ -f "$ENV_FILE" ] || { echo "Configuração local ausente; reinstale o cliente." >&2; exit 1; }

. "$ENV_FILE"
MCP_SERVER_URL="${MCP_SERVER_URL:-http://127.0.0.1:8765/mcp}"
HEALTH_ADDR="${HEALTH_ADDR:-127.0.0.1:8767}"

read -r -p "Tunnel ID Android (criado em Platform > Tunnels): " tunnel_id
[[ "$tunnel_id" =~ ^tunnel__?[a-z0-9]{32}$ ]] || { echo "Formato de tunnel_id inválido." >&2; exit 1; }

read -r -s -p "Runtime API key (Tunnels Read + Use): " runtime_key
printf '\n'
[ "${#runtime_key}" -ge 20 ] || { unset runtime_key; echo "Runtime key curta demais." >&2; exit 1; }

mkdir -p "$CONFIG_DIR"
umask 077
printf '%s\\n' "$runtime_key" > "$SECRET_FILE"
unset runtime_key
chmod 600 "$SECRET_FILE" "$ENV_FILE"

# Profile refers to the environment variable; the secret is never written to YAML.
"$CLIENT" init \
  --sample sample_mcp_remote_no_auth \
  --profile "$PROFILE_NAME" \
  --profile-dir "$CONFIG_DIR/profiles" \
  --tunnel-id "$tunnel_id" \
  --mcp-server-url "$MCP_SERVER_URL" \
  --control-plane-api-key-ref env:CONTROL_PLANE_API_KEY \
  --health-listen-addr "$HEALTH_ADDR" \
  --force

echo
echo "Perfil criado em $CONFIG_DIR/profiles/$PROFILE_NAME.yaml"
echo "A chave foi gravada em arquivo privado (modo 600), fora do repositório."
echo "Antes de iniciar, confirme que o MCP Android responde em $MCP_SERVER_URL."
echo "Depois inicie: sv up jarvis-secure-mcp-tunnel"
