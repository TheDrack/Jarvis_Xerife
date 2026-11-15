#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Jarvis Android Secure MCP Tunnel installer.
# Builds the official OpenAI tunnel-client for Android/ARM64 on-device.
TUNNEL_CLIENT_VERSION="v0.0.20"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
PREFIX="${PREFIX:-/data/data/com.termux/files/usr}"
APP_ROOT="$HOME/.local/opt/jarvis-tunnel"
SOURCE_ROOT="$APP_ROOT/src/tunnel-client"
BIN_DIR="$APP_ROOT/bin"
CONFIG_DIR="$HOME/.config/jarvis/tunnel"
PROFILE_NAME="jarvis-android"
PROFILE_DIR="$CONFIG_DIR/profiles"
SECRET_FILE="$CONFIG_DIR/runtime-key"
ENV_FILE="$CONFIG_DIR/tunnel.env"
SERVICE_NAME="jarvis-secure-mcp-tunnel"
SERVICE_ROOT="$HOME/.local/share/jarvis-runit/$SERVICE_NAME"
SERVICE_LINK="$PREFIX/var/service/$SERVICE_NAME"
MCP_LOCAL_HOST="${MCP_LOCAL_HOST:-127.0.0.1}"
MCP_LOCAL_PORT="${MCP_LOCAL_PORT:-8765}"
MCP_SERVER_URL="http://$MCP_LOCAL_HOST:$MCP_LOCAL_PORT/mcp"
HEALTH_ADDR="127.0.0.1:8767"

log() { printf '[JARVIS-TUNNEL] %s\n' "$*"; }
die() { log "ERRO: $*" >&2; exit 1; }

command -v pkg >/dev/null 2>&1 || die "Execute este instalador dentro do Termux."
pkg update -y
pkg install -y git golang clang make python

mkdir -p "$BIN_DIR" "$CONFIG_DIR" "$PROFILE_DIR" "$HOME/.local/state/jarvis-tunnel"
chmod 700 "$CONFIG_DIR" "$PROFILE_DIR" "$HOME/.local/state/jarvis-tunnel"

if [ ! -d "$SOURCE_ROOT/.git" ]; then
  mkdir -p "$(dirname "$SOURCE_ROOT")"
  git clone --depth 1 --branch "$TUNNEL_CLIENT_VERSION" \
    https://github.com/openai/tunnel-client.git "$SOURCE_ROOT"
else
  current="$(git -C "$SOURCE_ROOT" describe --tags --exact-match 2>/dev/null || true)"
  if [ "$current" != "$TUNNEL_CLIENT_VERSION" ]; then
    git -C "$SOURCE_ROOT" fetch --depth 1 origin "refs/tags/$TUNNEL_CLIENT_VERSION:refs/tags/$TUNNEL_CLIENT_VERSION"
    git -C "$SOURCE_ROOT" checkout --detach "$TUNNEL_CLIENT_VERSION"
  fi
fi

log "Compilando tunnel-client oficial para Android/ARM64 (CGO habilitado para resolver DNS Android)..."
(
  cd "$SOURCE_ROOT"
  module_path="$(go list -m -f '{{.Path}}')"
  git_sha="$(git rev-parse HEAD)"
  mkdir -p bin
  GOOS=android GOARCH=arm64 CGO_ENABLED=1 CC=clang \
    go build -trimpath \
      -ldflags "-X ${module_path}/pkg/version.GitSHA=${git_sha}" \
      -o "$BIN_DIR/tunnel-client" ./cmd/client
)
chmod 700 "$BIN_DIR/tunnel-client"
"$BIN_DIR/tunnel-client" --version

# Keep service scripts in the user's home; runit only receives a symlink.
mkdir -p "$SERVICE_ROOT" "$(dirname "$SERVICE_LINK")"
install -m 700 "$REPO_ROOT/scripts/android/service/run" "$SERVICE_ROOT/run"
mkdir -p "$SERVICE_ROOT/log"
install -m 700 "$REPO_ROOT/scripts/android/service/log-run" "$SERVICE_ROOT/log/run"

if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
MCP_LOCAL_HOST=$MCP_LOCAL_HOST
MCP_LOCAL_PORT=$MCP_LOCAL_PORT
MCP_SERVER_URL=$MCP_SERVER_URL
HEALTH_ADDR=$HEALTH_ADDR
PROFILE_NAME=$PROFILE_NAME
PROFILE_DIR=$PROFILE_DIR
EOF
  chmod 600 "$ENV_FILE"
fi

if [ ! -e "$SERVICE_LINK" ]; then
  ln -s "$SERVICE_ROOT" "$SERVICE_LINK"
elif [ ! -L "$SERVICE_LINK" ]; then
  die "Já existe um caminho não-symlink em $SERVICE_LINK; não será sobrescrito."
fi
log "Serviço runit instalado em $SERVICE_LINK"

cat <<EOF

Instalação do cliente concluída.

Próximo passo: cadastrar o túnel Android:
  bash "$REPO_ROOT/scripts/android/configure_secure_mcp_tunnel.sh"

Endpoint MCP local esperado:
  $MCP_SERVER_URL

O MCP do Android precisa estar ativo nesse endpoint antes do túnel ficar saudável.
O serviço usa somente loopback; não abre porta MCP na rede Wi-Fi.

EOF
