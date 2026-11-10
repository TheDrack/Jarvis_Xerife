#!/usr/bin/env bash
# Jarvis OS — verificação pós-provisionamento (VIV mínima em Linux).
#
# Read-only: não instala, não altera serviço, não faz rede de saída. Reporta
# cada checagem como PASS/FAIL e termina com código 1 se algo exigido falhar.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CHECK_SERVICES=0
RUN_TESTS=0
FAILED=0
WARNED=0

usage() {
    cat <<'USAGE'
Uso: linux/verify-jarvis-os.sh [opções]

  --repo PATH    Raiz do repositório (padrão: diretório pai deste script)
  --services     Exige jarvis-api (e jarvis-mcp, se instalada) ativas
  --tests        Roda o subconjunto determinístico de testes do grafo/MCP
  -h, --help     Mostra esta ajuda

Sem --tests nada é executado do pytest; a verificação funcional completa
pertence ao procedimento de VIV (docs/POS_INSTALACAO.md).
USAGE
}

while [ $# -gt 0 ]; do
    case "$1" in
        --repo) REPO_ROOT="${2:?--repo exige um caminho}"; shift 2 ;;
        --services) CHECK_SERVICES=1; shift ;;
        --tests) RUN_TESTS=1; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage; echo "opção desconhecida: $1" >&2; exit 2 ;;
    esac
done

pass() { printf 'PASS  %s\n' "$*"; }
fail() { printf 'FAIL  %s\n' "$*"; FAILED=$((FAILED + 1)); }
warn() { printf 'WARN  %s\n' "$*"; WARNED=$((WARNED + 1)); }

VENV_PY="$REPO_ROOT/.venv/bin/python"
ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/jarvis/jarvis.env"
UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"

if [ -x "$VENV_PY" ]; then pass "venv: $("$VENV_PY" --version 2>&1)"; else fail "venv ausente: $VENV_PY"; fi

if [ -x "$VENV_PY" ]; then
    if "$VENV_PY" - "$REPO_ROOT" <<'PY'
import importlib.util
import sys

root = sys.argv[1]
sys.path.insert(0, root)
required = ("fastapi", "uvicorn", "pydantic", "mcp")
optional = ("psutil", "pyautogui", "playwright", "speech_recognition")
missing = [name for name in required if importlib.util.find_spec(name) is None]
for name in optional:
    if importlib.util.find_spec(name) is None:
        print(f"optional-missing: {name}")
sys.exit(1 if missing else 0)
PY
    then pass "imports obrigatórios (fastapi, uvicorn, pydantic, mcp)"
    else fail "imports obrigatórios ausentes no venv"
    fi

    if "$VENV_PY" - "$REPO_ROOT" <<'PY'
import sys
root = sys.argv[1]
sys.path.insert(0, root)
try:
    import app.domain.graph.edges  # noqa: F401
    import app.adapters.edge.osint_mcp_tools  # noqa: F401
    import app.application.services.graph_store_setup  # noqa: F401
except Exception as exc:  # noqa: BLE001 - relatório de verificação
    print(f"{type(exc).__name__}: {exc}")
    sys.exit(1)
PY
    then pass "módulos do grafo OSINT importam em Linux"
    else fail "módulo do grafo/MCP não importa (ver acima)"
    fi
fi

if [ -f "$ENV_FILE" ]; then
    perms="$(stat -c '%a' "$ENV_FILE" 2>/dev/null || echo '?')"
    if [ "$perms" = "600" ]; then pass "ambiente 0600: $ENV_FILE"; else fail "permissões $perms em $ENV_FILE (esperado 600)"; fi
    if grep -qE '^(OPENAI_API_KEY|GROQ_API_KEY|GEMINI_API_KEY)=.+' "$ENV_FILE"; then
        pass "ao menos um provedor LLM configurado"
    else
        warn "nenhuma chave de provedor preenchida (harness sobe; LLM fica indisponível)"
    fi
else
    fail "arquivo de ambiente ausente: $ENV_FILE"
fi

if [ -f "$UNIT_DIR/jarvis-api.service" ]; then pass "unit jarvis-api instalada"; else fail "unit jarvis-api ausente"; fi

if [ "$CHECK_SERVICES" -eq 1 ]; then
    command -v systemctl >/dev/null || fail "systemctl indisponível"
    for unit in jarvis-api.service jarvis-mcp.service; do
        [ -f "$UNIT_DIR/$unit" ] || { warn "$unit não instalada (pulada)"; continue; }
        state="$(systemctl --user is-active "$unit" 2>/dev/null || true)"
        if [ "$state" = "active" ]; then pass "$unit active"; else fail "$unit $state"; fi
    done
    if command -v ss >/dev/null; then
        if ss -ltn 2>/dev/null | grep -qE '127\.0\.0\.1:8765\b'; then
            pass "MCP escutando em 127.0.0.1:8765"
        else
            warn "porta 8765 não está em loopback (normal se --with-mcp não foi usado)"
        fi
    fi
fi

if [ "$RUN_TESTS" -eq 1 ]; then
    if "$VENV_PY" -c 'import pytest' 2>/dev/null; then
        if (cd "$REPO_ROOT" && "$VENV_PY" -m pytest tests/domain/graph tests/application/test_graph_store_setup.py -q --no-cov -p no:cacheprovider); then
            pass "testes do grafo OSINT"
        else
            fail "testes do grafo OSINT"
        fi
    else
        warn "pytest ausente; rode o provisionamento com --with-dev"
    fi
fi

printf '\nResumo: %d falha(s), %d aviso(s)\n' "$FAILED" "$WARNED"
[ "$FAILED" -eq 0 ]
