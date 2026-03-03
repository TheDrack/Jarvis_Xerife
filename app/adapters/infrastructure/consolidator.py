# -*- coding: utf-8 -*-
import os
import logging
from datetime import datetime
from app.core.nexuscomponent import NexusComponent

# Configuração de logging integrada ao Nexus
logger = logging.getLogger(__name__)

class Consolidator(NexusComponent):
    """
    Componente de Simbiose: Unifica o repositório com Mapa de Árvore e Metadados
    para otimização de contexto em LLMs.
    """
    def __init__(self):
        super().__init__()
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"

    def execute(self, context: dict) -> dict:
        """
        Executa a consolidação e retorna o contexto atualizado com o caminho do arquivo.
        """
        print(f"🔬 [NEXUS] Iniciando Consolidação Estruturada: {datetime.now()}")

        # Configurações de Filtro
        ignored_dirs = {'.git', '__pycache__', '.venv', 'dist', 'build', 'node_modules', 'venv', '.github'}
        relevant_extensions = (".py", ".yml", ".yaml", ".json", ".sql", ".dockerfile", "Dockerfile", ".env.example")

        try:
            # Garante caminho absoluto para evitar erros de localização em Cloud
            file_path = os.path.abspath(self.output_file)

            with open(file_path, "w", encoding="utf-8") as out:
                # 1. CABEÇALHO DE CONTEXTO PARA IA
                out.write("="*100 + "\n")
                out.write(f"PROJETO: JARVIS ASSISTANT - REPOSITÓRIO CONSOLIDADO\n")
                out.write(f"DATA DA EXTRAÇÃO: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n")
                out.write(f"PIPELINE ORIGEM: {context.get('metadata', {}).get('pipeline', 'N/A')}\n")
                out.write("OBJETIVO: Fornecer contexto completo de arquitetura e lógica para análise de IA.\n")
                out.write("="*100 + "\n\n")

                # 2. MAPA DA ÁRVORE DE DIRETÓRIOS
                out.write("ESTRUTURA DO PROJETO (TREE):\n")
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs]
                    level = root.replace('.', '').count(os.sep)
                    indent = ' ' * 4 * level
                    out.write(f"{indent}{os.path.basename(root)}/\n")
                    sub_indent = ' ' * 4 * (level + 1)
                    
                    # Ordenação para manter consistência no Gist
                    for f in sorted(files):
                        if f.endswith(relevant_extensions) and f != self.output_file:
                            out.write(f"{sub_indent}📄 {f}\n")

                out.write("\n" + "="*100 + "\n")
                out.write("CONTEÚDO DOS ARQUIVOS CONSOLIDADOS\n")
                out.write("="*100 + "\n")

                # 3. CONSOLIDAR CONTEÚDO
                for root, dirs, files in os.walk("."):
                    dirs[:] = [d for d in dirs if d not in ignored_dirs]
                    for file in sorted(files):
                        if file.endswith(relevant_extensions) and file != self.output_file:
                            path = os.path.join(root, file)
                            
                            out.write(f"\n\nFILE_PATH: {path}\n")
                            out.write(f"FILE_NAME: {file}\n")
                            out.write("-" * 50 + "\n")

                            try:
                                with open(path, "r", encoding="utf-8", errors="ignore") as f:
                                    content = f.read()
                                    out.write(content if content.strip() else "[ARQUIVO VAZIO]")
                            except Exception as file_error:
                                out.write(f"[ERRO AO LER ARQUIVO: {file_error}]")

                            out.write(f"\n\n{'#'*70}\n")

            print(f"✅ [NEXUS] Consolidação técnica finalizada: {file_path}")

            # ATUALIZAÇÃO DO CONTEXTO: Fundamental para que Telegram/Gist funcionem
            res_payload = {
                "status": "success",
                "file_path": file_path,
                "timestamp": datetime.now().isoformat()
            }
            
            context["result"] = res_payload
            context["artifacts"]["consolidator"] = res_payload

            return context

        except Exception as e:
            print(f"💥 [CONSOLIDATOR] Erro Crítico: {e}")
            # Em caso de erro, o pipeline decide se para ou segue via strict_mode no runner
            raise e
