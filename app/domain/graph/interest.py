"""Classificação de interesse de um nó ou aresta (Fase 2).

``Fuse`` é o único componente que atribui interesse:

- ``confirmed``: a evidência converge com o que o grafo já sabia.
- ``discrepancy``: a evidência contradiz o grafo (mesmo pivô, seletor diferente;
  mesma entidade em coordenadas distantes).
- ``novel``: relação ou entidade ainda não vista.
"""
from __future__ import annotations

from typing import Literal

Interest = Literal["confirmed", "discrepancy", "novel"]

INTEREST_VALUES: tuple[str, ...] = ("confirmed", "discrepancy", "novel")
