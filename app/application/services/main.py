import asyncio
from app.core.nexus import nexus

async def jarvis_boot():
    print("[SYSTEM] Iniciando Protocolo de Simbiose...")
    
    # O Nexus carrega o que for preciso sob demanda
    orchestrator = nexus.resolve("central_orchestrator", hint_path="domain/orchestration")
    
    if orchestrator:
        result = orchestrator.execute("Verificar integridade do sistema e reportar.")
        print(f"[JARVIS]: {result}")

if __name__ == "__main__":
    asyncio.run(jarvis_boot())
