# -*- coding: utf-8 -*-
import os
from datetime import datetime
from app.core.nexuscomponent import NexusComponent

class Consolidator(NexusComponent):
    """
    Componente de Simbiose: Unifica o repositório com Mapa de Árvore e Metadados
    para otimização de contexto em LLMs.
    """
    def execute(self, context: dict):
        output_file = "CORE_LOGIC_CONSOLIDATED.txt"
        print(f"🔬 [NEXUS] Iniciando Consolidação Estruturada: {datetime.now()}")

        # Configurações de Filtro
        ignored_dirs = {'__pycache__', '.venv', 'dist', 'build', 'node_modules', 'venv'}
        relevant_extensions = (".py", ".yml", ".yaml", ".json", ".sql", ".dockerfile", "Dockerfile", ".env.example")
        
        try:
            with open(output_file, "w", encoding="utf-8") as out:
                # 1. CABEÇALHO DE CONTEXTO PARA IA
                out.write("="*100 + "\n")
                out.write(f"PROJETO: JARVIS ASSISTANT - REPOSITÓRIO CONSOLIDADO\n")
                out.write(f"DATA DA EXTRAÇÃO: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                out.write("OBJETIVO: Fornecer contexto completo de arquitetura e lógica para análise de IA.\n")
                out.write("="*100 + "\n\n")

                # 2. MAPA DA ÁRVORE DE DIRETÓRIOS (Essencial para a IA entender a hierarquia)
                out.write("STRUTURA DO PROJETO (TREE):\n")
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs]
                    level = root.replace('.', '').count(os.sep)
                    indent = ' ' * 4 * level
                    out.write(f"{indent}{os.path.basename(root)}/\n")
                    sub_indent = ' ' * 4 * (level + 1)
                    for f in files:
                        if f.endswith(relevant_extensions):
                            out.write(f"{sub_indent}📄 {f}\n")
                
                out.write("\n" + "="*100 + "\n")
                out.write("CONTEÚDO DOS ARQUIVOS\n")
                out.write("="*100 + "\n")

                # 3. CONSOLIDAR CONTEÚDO
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs]
                    for file in sorted(files):
                        if file.endswith(relevant_extensions) and file != output_file:
                            path = os.path.join(root, file)
                            
                            out.write(f"\n\nFILE_PATH: {path}\n")
                            out.write(f"FILE_NAME: {file}\n")
                            out.write("-" * 50 + "\n")
                            
                            try:
                                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                    content = f.read()
                                    if content.strip():
                                        out.write(content)
                                    else:
                                        out.write("[ARQUIVO VAZIO]")
                            except Exception as file_error:
                                out.write(f"[ERRO AO LER ARQUIVO: {file_error}]")
                                
                            out.write(f"\n\n{'#'*70}\n")

            print(f"✅ [NEXUS] Consolidação técnica finalizada: {output_file}")
            return output_file
        except Exception as e:
            print(f"💥 [CONSOLIDATOR] Erro Crítico: {e}")
            return None
