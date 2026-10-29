#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Verificação local do Respan Gateway integrado ao AIGateway.

O gateway é open-source, roda in-process e gasta as chaves de provider que o
projeto já tem (GROQ_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY, ...). Não precisa
de conta, créditos ou export de tracing do Respan.

Uso:
    # O que o gateway serviria com a configuração atual (gateway.toml ou env)
    python scripts/check_respan_gateway.py

    # Uma conclusão de verdade pelo caminho integrado (AIGateway -> gateway)
    python scripts/check_respan_gateway.py --prompt \"diga olá\"

    # Servidor local só em loopback, para clientes OpenAI-compatíveis
    python scripts/check_respan_gateway.py --serve --port 8099
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# Garante que o root do projeto esteja importável quando o script é executado
# diretamente (python scripts/check_respan_gateway.py).
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_REPO_ROOT / ".env")

from app.adapters.infrastructure.ai_gateway import AIGateway  # noqa: E402

logger = logging.getLogger("respan-gateway-check")


def _describe(gateway: AIGateway) -> None:
    providers = gateway.respan_gateway.providers()
    models = gateway.respan_gateway.models()
    print(f"modelo pedido pelo Jarvis: {gateway.respan_model}")
    print(f"providers: {[provider.get('name') for provider in providers]}")
    print(f"modelos servidos ({len(models)}):")
    for model in models[:10]:
        print(f"  - {model.get('id')} ({model.get('kind')}, dono: {model.get('owned_by')})")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Verifica o Respan Gateway in-process.")
    parser.add_argument("--prompt", help="Envia uma conclusão de teste pelo AIGateway.")
    parser.add_argument("--serve", action="store_true", help="Serve o gateway em loopback.")
    parser.add_argument("--port", type=int, default=8099, help="Porta do servidor local.")
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    gateway = AIGateway(enable_respan=True)
    if gateway.respan_gateway is None:
        print(
            "Respan Gateway indisponível nesta configuração.\n"
            "  - instale o pacote: pip install respan-gateway==0.3.0\n"
            "  - defina ao menos uma chave de provider (ex.: GROQ_API_KEY) no .env\n"
            "  - ou aponte RESPAN_GATEWAY_CONFIG para um gateway.toml existente"
        )
        return 1

    try:
        _describe(gateway)

        if args.prompt:
            result = asyncio.run(
                gateway.generate_completion([{"role": "user", "content": args.prompt}])
            )
            print(f"provider usado: {result['provider']} (modelo: {result['model']})")
            reply = result["response"].choices[0].message.content
            print(f"resposta: {reply}")

        if args.serve:
            print(f"servindo em http://127.0.0.1:{args.port} (Ctrl-C encerra)")
            print(f"clientes OpenAI-compatíveis usam http://127.0.0.1:{args.port}/v1")
            gateway.respan_gateway.serve_forever(port=args.port)
    finally:
        gateway.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
