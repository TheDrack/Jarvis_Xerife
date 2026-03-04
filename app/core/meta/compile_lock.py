# -*- coding: utf-8 -*-
"""
CompileLock — Travamento unificado de compilação JRVS.

Garante que apenas um processo de compilação (seja disparado pelo PolicyStore
ou pelo OverwatchDaemon) execute por vez.

Implementação via arquivo de lock com timestamp:
  - Arquivo criado com o timestamp UNIX de aquisição.
  - Locks mais antigos que JRVS_COMPILE_LOCK_TIMEOUT (default 120 s) são considerados
    obsoletos (stale) e podem ser substituídos automaticamente.

Variáveis de ambiente:
  JRVS_DIR                    str    Diretório base (default "data/jrvs").
  JRVS_COMPILE_LOCK_TIMEOUT   float  Segundos até um lock ser considerado stale (default 120).
"""

import logging
import os
import time
from pathlib import Path

logger = logging.getLogger(__name__)

_DEFAULT_LOCK_TIMEOUT = 120.0
_LOCK_FILENAME = ".compile.lock"


def _lock_path(jrvs_dir: str = "data/jrvs") -> Path:
    base = Path(os.getenv("JRVS_DIR", jrvs_dir))
    base.mkdir(parents=True, exist_ok=True)
    return base / _LOCK_FILENAME


def _lock_timeout() -> float:
    return float(os.getenv("JRVS_COMPILE_LOCK_TIMEOUT", str(_DEFAULT_LOCK_TIMEOUT)))


def acquire_compile_lock(jrvs_dir: str = "data/jrvs") -> bool:
    """Tenta adquirir o lock de compilação.

    Args:
        jrvs_dir: Diretório onde o arquivo de lock é armazenado.

    Returns:
        ``True`` se o lock foi adquirido com sucesso, ``False`` se já existe um
        lock ativo (não obsoleto).
    """
    path = _lock_path(jrvs_dir)
    now = time.time()
    timeout = _lock_timeout()

    if path.exists():
        try:
            ts = float(path.read_text(encoding="utf-8").strip())
            age = now - ts
            if age < timeout:
                logger.debug(
                    "[CompileLock] Lock ativo (%.1f s / timeout %.0f s). Compilação ignorada.",
                    age,
                    timeout,
                )
                return False
            logger.warning(
                "[CompileLock] Lock obsoleto detectado (%.1f s). Substituindo.", age
            )
        except (ValueError, OSError):
            logger.debug("[CompileLock] Lock corrompido/ilegível. Substituindo.")

    try:
        path.write_text(str(now), encoding="utf-8")
        logger.debug("[CompileLock] Lock adquirido (ts=%.3f).", now)
        return True
    except OSError as exc:
        logger.error("[CompileLock] Falha ao criar lock: %s", exc)
        return False


def release_compile_lock(jrvs_dir: str = "data/jrvs") -> None:
    """Libera o lock de compilação.

    Args:
        jrvs_dir: Diretório onde o arquivo de lock está armazenado.
    """
    path = _lock_path(jrvs_dir)
    try:
        path.unlink(missing_ok=True)
        logger.debug("[CompileLock] Lock liberado.")
    except OSError as exc:
        logger.warning("[CompileLock] Falha ao liberar lock: %s", exc)
