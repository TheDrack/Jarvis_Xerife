# -*- coding: utf-8 -*-
"""Shim de compatibilidade — Overwatch Daemon.

A implementação canônica vive em
``app.adapters.infrastructure.overwatch_adapter.OverwatchDaemon`` e é a que
está registrada no Nexus (``overwatch_daemon`` em ``data/nexus_registry.json``).

Este módulo existia como uma segunda implementação paralela, com um
subconjunto de funcionalidades (sem monitor preditivo, sem ciclo de
compilação JRVS, sem travessia de inatividade) e sem ``_authorized_macs``.
Manter duas versões do mesmo daemon criava divergência silenciosa: o que era
corrigido num arquivo não chegava ao outro. Agora ele apenas reexporta a
versão única, preservando imports antigos.
"""

from app.adapters.infrastructure.overwatch_adapter import OverwatchDaemon  # noqa: F401

__all__ = ["OverwatchDaemon"]
