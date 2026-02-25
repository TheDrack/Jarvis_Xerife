# -*- coding: utf-8 -*-
import os
from datetime import datetime
from typing import Set, Dict, Any
from app.core.nexuscomponent import NexusComponent

class Consolidator(NexusComponent):
    def __init__(self):
        self.output_file = "CORE_LOGIC_CONSOLIDATED.txt"
        self.ignore_dirs: Set[str] = {
            ".git", "venv", "__pycache__", "tests", "build", "dist", "metabolism_logs"
        }
        self.ignore_files: Set[str] = {
            ".env", "credentials.json"
        }
        self.allowed_extensions: Set[str] = {
            ".py", ".json", ".yml", ".yaml", ".sh", ".sql"
        }

    def configure(self, config: dict):
        self.output_file = config.get("output_file", self.output_file)
        self.ignore_files.add(self.output_file)

    def execute(self, context: Dict[str, Any]) -> str:
        return self.consolidate()

    def consolidate(self) -> str:
        # Geração do Timestamp de sincronização
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        print(f"🔬 Consolidando projeto [Versão: {now}] → {self.output_file}")

        with open(self.output_file, "w", encoding="utf-8") as out:
            # CABEÇALHO DE CONTROLE DE VERSÃO (Para leitura da IA)
            out.write("=" * 80 + "\n")
            out.write(f"### JARVIS SYSTEM CONSOLIDATION ###\n")
            out.write(f"### LAST UPDATE: {now} ###\n")
            out.write(f"### ROOT: {os.getcwd()} ###\n")
            out.write("=" * 80 + "\n\n")

            for root, dirs, files in os.walk("."):
                dirs[:] = [d for d in dirs if d not in self.ignore_dirs]

                for file in files:
                    if not file.endswith(tuple(self.allowed_extensions)):
                        continue
                    if file in self.ignore_files or file == self.output_file:
                        continue

                    path = os.path.join(root, file)
                    rel = os.path.relpath(path, ".")

                    out.write("\n" + "-" * 40 + "\n")
                    out.write(f" FILE: {rel}\n")
                    out.write("-" * 40 + "\n\n")

                    try:
                        with open(path, "r", encoding="utf-8") as f:
                            out.write(f.read())
                    except Exception as e:
                        out.write(f"[ERRO] Falha ao ler arquivo {rel}: {e}\n")

                    out.write(f"\n--- FIM DO ARQUIVO: {rel} ---\n")

        print(f"✅ Consolidação concluída em {now}")
        return self.output_file
