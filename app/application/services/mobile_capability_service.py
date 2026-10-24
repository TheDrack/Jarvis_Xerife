# -*- coding: utf-8 -*-
"""Registra as capacidades mobile de um dispositivo Android na tabela `capabilities`.

Usa o modelo existente (Device/Capability). Idempotente: não duplica capacidades.
"""

from __future__ import annotations

import json
from typing import Iterable

from sqlmodel import Session, select

from app.adapters.edge.mobile_mcp_tools import MOBILE_CAPABILITIES
from app.domain.models.device import Capability, Device

_DESCRIPTIONS = {
    "mobile.observe": "Captura de tela e hierarquia de UI de aparelho Android",
    "mobile.tap": "Toque em elemento identificado (exige confirmação quando sensível)",
    "mobile.type": "Digitação de texto ASCII (exige confirmação quando sensível)",
    "mobile.key": "Teclas permitidas (HOME, BACK, ENTER, DEL...)",
    "mobile.launch_app": "Abertura de app por nome de pacote",
}


def ensure_mobile_capabilities(
    session: Session, device: Device, names: Iterable[str] = MOBILE_CAPABILITIES
) -> list[str]:
    """Cria as capacidades ausentes para o dispositivo. Retorna os nomes criados."""
    if device.id is None:
        raise ValueError("dispositivo precisa estar persistido antes de receber capacidades")
    if device.type != "mobile":
        raise ValueError("capacidades mobile só se aplicam a dispositivos do tipo 'mobile'")
    existing = set(
        session.exec(select(Capability.name).where(Capability.device_id == device.id)).all()
    )
    created: list[str] = []
    for name in names:
        if name in existing:
            continue
        session.add(
            Capability(
                device_id=device.id,
                name=name,
                description=_DESCRIPTIONS.get(name, ""),
                meta_data=json.dumps({"platform": "android", "transport": "adb"}),
            )
        )
        created.append(name)
    session.commit()
    return created
