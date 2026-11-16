#!/data/data/com.termux/files/usr/bin/bash
set -Eeuo pipefail

CONFIG_DIR="$HOME/.config/jarvis/accessibility"
TOKEN_FILE="$CONFIG_DIR/token"

mkdir -p "$CONFIG_DIR"
chmod 700 "$CONFIG_DIR"
umask 077

echo "Cole o segredo exibido em Jarvis Mobile > Acessibilidade > Parear Termux."
read -r -s -p "Segredo local: " token
printf '\n'
if [[ ${#token} -lt 40 || ${#token} -gt 256 ]]; then
  unset token
  echo "Segredo inválido; esperado entre 40 e 256 caracteres." >&2
  exit 1
fi
if [[ ! "$token" =~ ^[A-Za-z0-9_-]+$ ]]; then
  unset token
  echo "Formato inválido." >&2
  exit 1
fi

printf '%s' "$token" > "$TOKEN_FILE"
unset token
chmod 600 "$TOKEN_FILE"
echo "Pareamento local gravado em arquivo privado (modo 600)."
echo "Não envie esse segredo ao Control Plane nem o coloque no repositório."

SERVICE_DIR="${PREFIX:-/data/data/com.termux/files/usr}/var/service/jarvis-android-mcp"
if command -v sv >/dev/null 2>&1 && [[ -d "$SERVICE_DIR" ]]; then
  sv restart "$SERVICE_DIR"
  echo "Servidor MCP Android reiniciado."
else
  echo "Reinicie o serviço MCP Android para carregar as novas ferramentas."
fi
