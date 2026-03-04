# -*- coding: utf-8 -*-
"""
app.core.meta — Módulo de estado cognitivo modular do JARVIS.

Componentes:
  - PolicyStore:          armazena e serve políticas brutas por módulo.
  - JRVSCompiler:         compila snapshots .jrvs por módulo.
  - DecisionEngine:       toma decisões a partir dos snapshots .jrvs.
  - ExplorationController: descobre novas ferramentas e gerencia promoção.

Variáveis de ambiente relevantes:
  JRVS_RECOMPILE_THRESHOLD   (int, default 20)
  JRVS_DIR                   (str, default "data/jrvs")
  JRVS_COMPILER_VERSION      (str, default "1.0.0")
  JRVS_PROMOTE_THRESHOLD     (float, default 0.8)
  JRVS_COMPRESSION           (str, default "zlib")
"""
