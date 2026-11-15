#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

# Jarvis Android installer: local read-only MCP server + official tunnel client.
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

log() { printf '[JARVIS-TUNNEL] %s\n' "$*"; }
die() { log "ERRO: $*" >&2; exit 1; }

MCP_APP_ROOT="$HOME/.local/opt/jarvis-android-mcp"
MCP_VENV="$MCP_APP_ROOT/venv"
MCP_CONFIG_DIR="$HOME/.config/jarvis/android-mcp"
MCP_ENV_FILE="$MCP_CONFIG_DIR/server.env"
MCP_SERVICE_NAME="jarvis-android-mcp"
MCP_SERVICE_ROOT="$HOME/.local/share/jarvis-runit/$MCP_SERVICE_NAME"
MCP_SERVICE_LINK="$PREFIX/var/service/$MCP_SERVICE_NAME"
MCP_LOCAL_HOST="127.0.0.1"
MCP_LOCAL_PORT="${MCP_LOCAL_PORT:-8765}"
if [ -f "$ENV_FILE" ]; then
  # Reuse the user's existing local tunnel target so both services agree.
  . "$ENV_FILE"
fi
MCP_LOCAL_HOST="${MCP_LOCAL_HOST:-127.0.0.1}"
MCP_LOCAL_PORT="${MCP_LOCAL_PORT:-8765}"
[ "$MCP_LOCAL_HOST" = "127.0.0.1" ] || die "O MCP Android só pode usar 127.0.0.1."
MCP_SERVER_URL="http://$MCP_LOCAL_HOST:$MCP_LOCAL_PORT/mcp"
HEALTH_ADDR="${HEALTH_ADDR:-127.0.0.1:8767}"

command -v pkg >/dev/null 2>&1 || die "Execute este instalador dentro do Termux."
[ "$MCP_LOCAL_PORT" -ge 1 ] 2>/dev/null && [ "$MCP_LOCAL_PORT" -le 65535 ] 2>/dev/null || die "MCP_LOCAL_PORT inválida."
pkg update -y
pkg install -y git golang clang make python python-pip termux-api

mkdir -p "$BIN_DIR" "$CONFIG_DIR" "$PROFILE_DIR" "$HOME/.local/state/jarvis-tunnel"
mkdir -p "$MCP_APP_ROOT" "$MCP_CONFIG_DIR" "$HOME/.local/state/jarvis-android-mcp/log"
chmod 700 "$CONFIG_DIR" "$PROFILE_DIR" "$HOME/.local/state/jarvis-tunnel" "$MCP_CONFIG_DIR" "$HOME/.local/state/jarvis-android-mcp"

log "Preparando ambiente Python isolado para o servidor MCP Android..."
# Termux owns its system pip package and pip 26.3 refuses self-installation.
# Keep pip outside the venv; use its --python option to install only the
# application dependencies into the isolated interpreter.
python -m venv --without-pip "$MCP_VENV"
python -m pip --python "$MCP_VENV/bin/python" install 'mcp>=1.30.0,<2' 'uvicorn>=0.24.0,<1'
"$MCP_VENV/bin/python" -c 'import mcp, uvicorn'
printf 'REPO_ROOT=%q\nMCP_HOST=127.0.0.1\nMCP_PORT=%q\n' "$REPO_ROOT" "$MCP_LOCAL_PORT" > "$MCP_ENV_FILE"
chmod 600 "$MCP_ENV_FILE"

# Keep service scripts in the user's home; runit only receives symlinks.
mkdir -p "$MCP_SERVICE_ROOT" "$(dirname "$MCP_SERVICE_LINK")"
install -m 700 "$REPO_ROOT/scripts/android/service/mcp-run" "$MCP_SERVICE_ROOT/run"
mkdir -p "$MCP_SERVICE_ROOT/log"
install -m 700 "$REPO_ROOT/scripts/android/service/mcp-log-run" "$MCP_SERVICE_ROOT/log/run"
if [ ! -e "$MCP_SERVICE_LINK" ]; then
  ln -s "$MCP_SERVICE_ROOT" "$MCP_SERVICE_LINK"
elif [ ! -L "$MCP_SERVICE_LINK" ]; then
  die "Já existe um caminho não-symlink em $MCP_SERVICE_LINK; não será sobrescrito."
fi

if [ ! -d "$SOURCE_ROOT/.git" ]; then
  mkdir -p "$(dirname "$SOURCE_ROOT")"
  git clone --depth 1 --branch "$TUNNEL_CLIENT_VERSION" \\
    https://github.com/openai/tunnel-client.git "$SOURCE_ROOT"
else
  current="$(git -C "$SOURCE_ROOT" describe --tags --exact-match 2>/dev/null || true)"
  if [ "$current" != "$TUNNEL_CLIENT_VERSION" ]; then
    git -C "$SOURCE_ROOT" fetch --depth 1 origin "refs/tags/$TUNNEL_CLIENT_VERSION:refs/tags/$TUNNEL_CLIENT_VERSION"
    git -C "$SOURCE_ROOT" checkout --detach "$TUNNEL_CLIENT_VERSION"
  fi
fi

log "Compilando tunnel-client oficial para Android/ARM64 (CGO habilitado para DNS Android)..."
(
  cd "$SOURCE_ROOT"
  module_path="$(go list -m -f '{{.Path}}')"
  git_sha="$(git rev-parse HEAD)"
  mkdir -p bin
  GOOS=android GOARCH=arm64 CGO_ENABLED=1 CC=clang \\
    go build -trimpath \\
      -ldflags "-X ${module_path}/pkg/version.GitSHA=${git_sha}" \\
      -o "$BIN_DIR/tunnel-client" ./cmd/client
)
chmod 700 "$BIN_DIR/tunnel-client"
"$BIN_DIR/tunnel-client" --version

mkdir -p "$SERVICE_ROOT" "$(dirname "$SERVICE_LINK")"
install -m 700 "$REPO_ROOT/scripts/android/service/run" "$SERVICE_ROOT/run"
mkdir -p "$SERVICE_ROOT/log"
install -m 700 "$REPO_ROOT/scripts/android/service/log-run" "$SERVICE_ROOT/log/run"
if [ ! -e "$SERVICE_LINK" ]; then
  ln -s "$SERVICE_ROOT" "$SERVICE_LINK"
elif [ ! -L "$SERVICE_LINK" ]; then
  die "Já existe um caminho não-symlink em $SERVICE_LINK; não será sobrescrito."
fi

log "Serviços runit registrados: $MCP_SERVICE_NAME e $SERVICE_NAME"
if command -v sv >/dev/null 2>&1; then
  if sv up "$MCP_SERVICE_LINK"; then
    log "Servidor MCP Android solicitado ao runit."
  else
    log "Aviso: runit não iniciou o MCP automaticamente; execute sv up $MCP_SERVICE_NAME."
  fi
fi

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

cat <<EOF

Instalação concluída.

Servidor MCP Android:
  http://$MCP_LOCAL_HOST:$MCP_LOCAL_PORT/mcp
  Health: http://$MCP_LOCAL_HOST:$MCP_LOCAL_PORT/healthz
  Serviço: sv status $MCP_SERVICE_NAME

Cliente Secure MCP Tunnel:
  bash "$REPO_ROOT/scripts/android/configure_secure_mcp_tunnel.sh"
  sv up $SERVICE_NAME

O MCP e o túnel usam loopback; nenhuma porta é exposta à rede Wi-Fi.
Termux:API também exige o aplicativo complementar Termux:API instalado da
mesma origem do Termux. Sem ele, as ferramentas de bateria/Wi-Fi informam
indisponibilidade sem impedir o servidor MCP de iniciar.

EOF
