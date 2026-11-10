#!/usr/bin/env bash
# Jarvis OS — provisionamento do harness em Ubuntu 24.04 LTS / Debian 12+.
#
# Escopo: pacotes, venv, dependências, arquivo de ambiente, units systemd de
# usuário e verificações. Este script NÃO particiona disco, NÃO instala
# bootloader e NÃO altera o Windows. Instalação física é um passo separado,
# executado por uma pessoa, após inventário verificado (ver linux/README.md).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/jarvis/jarvis.env"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
WITH_DEV=0
WITH_DESKTOP=0
WITH_BROWSER=0
WITH_TAILSCALE=0
WITH_MCP=0
HARDEN=0
START=0

usage() {
    cat <<'USAGE'
Uso: linux/provision-jarvis-os.sh [opções]

  --repo PATH        Raiz do repositório (padrão: diretório pai deste script)
  --with-dev         Instala requirements/dev.txt (pytest e afins)
  --with-desktop     Instala XFCE mínimo + LightDM (perfil jarvis-os)
  --with-browser     Baixa o Chromium do Playwright (requer sudo)
  --with-tailscale   Adiciona o repositório oficial do Tailscale (sem login)
  --with-mcp         Habilita a unit do MCP em loopback (experimental em Linux)
  --harden-network   Default deny no UFW + liberação apenas em tailscale0
  --start            Inicia as units habilitadas ao final
  -h, --help         Mostra esta ajuda

Sem --harden-network e sem --with-tailscale nada de rede/firewall é alterado.
Nenhuma opção toca discos, partições, GRUB ou o Windows.
USAGE
}

log()  { printf '\033[1;36m[jarvis-os]\033[0m %s\n' "$*"; }
warn() { printf '\033[1;33m[jarvis-os]\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[1;31m[jarvis-os]\033[0m %s\n' "$*" >&2; exit 1; }

while [ $# -gt 0 ]; do
    case "$1" in
        --repo) REPO_ROOT="${2:?--repo exige um caminho}"; shift 2 ;;
        --with-dev) WITH_DEV=1; shift ;;
        --with-desktop) WITH_DESKTOP=1; shift ;;
        --with-browser) WITH_BROWSER=1; shift ;;
        --with-tailscale) WITH_TAILSCALE=1; shift ;;
        --with-mcp) WITH_MCP=1; shift ;;
        --harden-network) HARDEN=1; shift ;;
        --start) START=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage; die "opção desconhecida: $1" ;;
    esac
done

[ "$(id -u)" -ne 0 ] || die "rode como usuário normal; o script usa sudo quando necessário"
[ -d "$REPO_ROOT" ] || die "repositório não encontrado: $REPO_ROOT"
[ -f "$REPO_ROOT/serve.py" ] || die "$REPO_ROOT não parece ser o Jarvis_Xerife"
command -v apt-get >/dev/null || die "somente Debian/Ubuntu são suportados por este script"
command -v systemctl >/dev/null || die "systemd é obrigatório"

. /etc/os-release
case "${ID:-}" in
    ubuntu|debian) log "distribuição: $PRETTY_NAME" ;;
    *) warn "distribuição '$ID' não testada; seguindo sob seu risco" ;;
esac
case "$(uname -m)" in
    x86_64|aarch64) log "arquitetura: $(uname -m)" ;;
    *) die "arquitetura não suportada: $(uname -m)" ;;
esac

PYTHON_BIN="$(command -v python3.12 || command -v python3 || true)"
[ -n "$PYTHON_BIN" ] || die "python3 não encontrado"
"$PYTHON_BIN" - <<'PY' || die "Python 3.10+ é obrigatório"
import sys
sys.exit(0 if sys.version_info >= (3, 10) else 1)
PY
log "python: $("$PYTHON_BIN" --version 2>&1)"

SUDO=""
if [ "$(id -u)" -ne 0 ]; then SUDO="sudo"; fi

log "instalando pacotes de sistema"
$SUDO apt-get update -qq
PACKAGES=(
    python3-venv python3-dev build-essential pkg-config
    git curl ca-certificates jq
    ffmpeg flac espeak-ng portaudio19-dev libasound2-dev
    tesseract-ocr tesseract-ocr-por
    adb xclip scrot xdg-utils
    fonts-dejavu-core
)
if [ "$WITH_DESKTOP" -eq 1 ]; then
    PACKAGES+=(xfce4 xfce4-terminal lightdm lightdm-gtk-greeter dbus-x11)
fi
$SUDO env DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${PACKAGES[@]}"
log "pacotes instalados"

log "criando venv em $REPO_ROOT/.venv"
if [ ! -x "$REPO_ROOT/.venv/bin/python" ]; then
    "$PYTHON_BIN" -m venv "$REPO_ROOT/.venv"
fi
VENV_PY="$REPO_ROOT/.venv/bin/python"
"$VENV_PY" -m pip install --quiet --upgrade pip wheel

log "instalando dependências do Jarvis"
"$VENV_PY" -m pip install --quiet -r "$REPO_ROOT/requirements/core.txt"
"$VENV_PY" -m pip install --quiet -r "$REPO_ROOT/requirements/host.txt"
"$VENV_PY" -m pip install --quiet -r "$REPO_ROOT/linux/requirements-linux.txt"
if [ "$WITH_DEV" -eq 1 ]; then
    "$VENV_PY" -m pip install --quiet -r "$REPO_ROOT/requirements/dev.txt"
fi
if [ "$WITH_BROWSER" -eq 1 ]; then
    log "baixando Chromium do Playwright"
    "$VENV_PY" -m playwright install --with-deps chromium
fi

umask 077
ENV_DIR="$(dirname "$ENV_FILE")"
mkdir -p "$ENV_DIR"
chmod 700 "$ENV_DIR"
if [ ! -f "$ENV_FILE" ]; then
    log "criando $ENV_FILE (0600) — preencha as chaves depois"
    cat > "$ENV_FILE" <<'ENVEOF'
# Jarvis — variáveis de ambiente locais. Nunca versione este arquivo.
# Chaves de provedores (deixe vazio para desabilitar):
# OPENAI_API_KEY=
# GROQ_API_KEY=
# GEMINI_API_KEY=
# CENSYS_API_TOKEN=
# SHODAN_API_KEY=
# WIGLE_USERNAME=
# WIGLE_API_TOKEN=
# IPINFO_TOKEN=

# Runtime
PYTHON_ENV=production
LANGUAGE=pt-BR
WAKE_WORD=xerife
API_HOST=127.0.0.1

# Bancos locais
JARVIS_DEVICES_DB=$HOME/.local/share/jarvis/jarvis.db
JARVIS_GEOINT_DB=$HOME/.local/share/jarvis/geoint.sqlite
JARVIS_GRAPH_DB=$HOME/.local/share/jarvis/jarvis_graph.sqlite

# MCP (loopback; publique via Tailscale Serve, nunca em 0.0.0.0)
JARVIS_DESKTOP_HTTP_PORT=8765
ENVEOF
    chmod 600 "$ENV_FILE"
else
    log "mantendo $ENV_FILE existente"
fi

# Normalize only the three runtime database paths, preserving all existing
# provider credentials and operator settings in an already-created env file.
runtime_env_tmp="${ENV_FILE}.tmp.$$"
trap 'rm -f "$runtime_env_tmp" "${runtime_env_tmp}.next"' EXIT
awk '!/^JARVIS_(DEVICES|GEOINT|GRAPH)_DB=/' "$ENV_FILE" > "$runtime_env_tmp"
printf 'JARVIS_DEVICES_DB="%s"\nJARVIS_GEOINT_DB="%s"\nJARVIS_GRAPH_DB="%s"\n' "$HOME/.local/share/jarvis/jarvis.db" "$HOME/.local/share/jarvis/geoint.sqlite" "$HOME/.local/share/jarvis/jarvis_graph.sqlite" >> "$runtime_env_tmp"
if [ "$WITH_MCP" -eq 1 ] && ! grep -qE '^JARVIS_DESKTOP_AUTH_TOKEN="?[^"]{32,}"?$' "$runtime_env_tmp"; then
    auth_token="$("$VENV_PY" -c 'import secrets; print(secrets.token_urlsafe(48))')"
    awk '!/^JARVIS_DESKTOP_AUTH_TOKEN=/' "$runtime_env_tmp" > "${runtime_env_tmp}.next"
    printf 'JARVIS_DESKTOP_AUTH_TOKEN="%s"\n' "$auth_token" >> "${runtime_env_tmp}.next"
    mv "${runtime_env_tmp}.next" "$runtime_env_tmp"
fi
chmod 600 "$runtime_env_tmp"
mv "$runtime_env_tmp" "$ENV_FILE"
chmod 600 "$ENV_FILE"
mkdir -p "$HOME/.local/share/jarvis"
chmod 700 "$HOME/.local/share/jarvis"

log "instalando units systemd de usuário em $UNIT_DIR"
mkdir -p "$UNIT_DIR"
install_unit() {
    local template="$1" target="$UNIT_DIR/$2"
    sed -e "s|@REPO_ROOT@|$REPO_ROOT|g" \
        -e "s|@ENV_FILE@|$ENV_FILE|g" \
        -e "s|@PYTHON@|$VENV_PY|g" "$template" > "$target"
    chmod 644 "$target"
    log "  $target"
}
install_unit "$REPO_ROOT/linux/systemd/jarvis-api.service" "jarvis-api.service"
if [ "$WITH_MCP" -eq 1 ]; then
    install_unit "$REPO_ROOT/linux/systemd/jarvis-mcp.service" "jarvis-mcp.service"
fi
systemctl --user daemon-reload
systemctl --user enable jarvis-api.service
if [ "$WITH_MCP" -eq 1 ]; then
    systemctl --user enable jarvis-mcp.service
fi

if command -v loginctl >/dev/null; then
    if ! loginctl show-user "$USER" -p Linger 2>/dev/null | grep -q 'Linger=yes'; then
        warn "habilite serviços sem sessão aberta com: sudo loginctl enable-linger $USER"
    fi
fi

if [ "$WITH_TAILSCALE" -eq 1 ]; then
    if ! command -v tailscale >/dev/null; then
        log "adicionando repositório oficial do Tailscale"
        curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg \
            | $SUDO tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
        curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list \
            | $SUDO tee /etc/apt/sources.list.d/tailscale.list >/dev/null
        $SUDO apt-get update -qq
        $SUDO apt-get install -y tailscale
    fi
    log "Tailscale instalado; autentique com: sudo tailscale up --ssh=false"
fi

if [ "$HARDEN" -eq 1 ]; then
    log "aplicando UFW (default deny; SSH e tailscale0 liberados)"
    $SUDO ufw --force default deny incoming
    $SUDO ufw --force default allow outgoing
    $SUDO ufw allow 22/tcp comment 'ssh'
    $SUDO ufw allow in on tailscale0 comment 'tailscale'
    $SUDO ufw --force enable
    $SUDO ufw status verbose
fi

if [ "$START" -eq 1 ]; then
    log "iniciando jarvis-api"
    systemctl --user restart jarvis-api.service
    if [ "$WITH_MCP" -eq 1 ]; then
        log "iniciando jarvis-mcp"
        systemctl --user restart jarvis-mcp.service
    fi
fi

cat <<SUMMARY

Provisionamento concluído.
  venv:        $VENV_PY
  ambiente:    $ENV_FILE (0600)
  units:       $UNIT_DIR/jarvis-api.service$([ "$WITH_MCP" -eq 1 ] && echo " + jarvis-mcp.service")
  dados:       $HOME/.local/share/jarvis

Próximo passo obrigatório:
  linux/verify-jarvis-os.sh --repo "$REPO_ROOT"$([ "$WITH_MCP" -eq 1 ] && echo " --services")

Nada de disco, partição, bootloader ou Windows foi alterado.
SUMMARY
