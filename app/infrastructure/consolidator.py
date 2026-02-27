# -*- coding: utf-8 -*-
import os
from datetime import datetime
from app.core.nexuscomponent import NexusComponent

class Consolidator(NexusComponent):
    """
    Componente que varre o projeto e unifica em um único arquivo TXT.
    """
    def execute(self, context: dict):
        output_file = "CORE_LOGIC_CONSOLIDATED.txt"
        print(f"🔬 [NEXUS] Iniciando Consolidação: {datetime.now()}")
        
        ignored_dirs = {'.git', '__pycache__', '.venv', 'dist', 'build', '.github'}
        
        try:
            with open(output_file, "w", encoding="utf-8") as out:
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs]
                    for file in files:
                        if file.endswith((".py", ".yml", ".json")) and file != output_file:
                            path = os.path.join(root, file)
                            out.write(f"\n\n{'='*50}\nFILE: {path}\n{'='*50}\n")
                            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                out.write(f.read())
            
            print(f"✅ [NEXUS] Arquivo gerado: {output_file}")
            return output_file # Retorna o path para o próximo componente
        except Exception as e:
            print(f"💥 [CONSOLIDATOR] Erro: {e}")
            return None
