# -*- coding: utf-8 -*-
import os
import logging
from typing import Optional, Dict, Any
from app.core.nexus import nexus, NexusComponent

logger = logging.getLogger(__name__)

class CrystallizerEngine(NexusComponent):
    """
    Motor de Cristalização.
    Responsável por transformar conceitos em ficheiros .py funcionais.
    """

    def __init__(self):
        super().__init__()
        # REGRA: Resolve o logger único para documentar a evolução
        self.logger = nexus.resolve("structured_logger")
        self.base_path = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    def execute(self, context: Optional[Dict[str, Any]] = None) -> Any:
        """
        Recebe um template e metadados para criar um novo componente no disco.
        """
        if not context or "code" not in context or "name" not in context:
            return {"success": False, "error": "Dados insuficientes para cristalização."}

        return self.crystallize(context["name"], context["code"], context.get("path", "domain/gears"))

    def crystallize(self, name: str, code: str, relative_path: str) -> Dict[str, Any]:
        """
        Escreve fisicamente o código no repositório e notifica o Nexus.
        """
        target_dir = os.path.join(self.base_path, "app", relative_path)
        os.makedirs(target_dir, exist_ok=True)
        
        file_path = os.path.join(target_dir, f"{name}.py")

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(code)

            self.logger.execute({
                "level": "info", 
                "message": f"💎 Nova gema cristalizada: {name} em {relative_path}"
            })

            # REGRA DE AUTO-EVOLUÇÃO:
            # Após criar o ficheiro, invalidamos o cache do Nexus para que o 
            # nexus.resolve encontre o novo componente no próximo pedido.
            nexus.invalidate_component(name)
            nexus.commit_memory()

            return {"success": True, "path": file_path}

        except Exception as e:
            error_msg = f"💥 Falha na cristalização de {name}: {str(e)}"
            self.logger.execute({"level": "error", "message": error_msg})
            return {"success": False, "error": error_msg}
